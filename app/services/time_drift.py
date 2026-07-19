"""
Time-of-day drift re-ranking.

SessionDNA's time_of_day component (mood_to_audio_features.py's
TIME_ENERGY_ADJUSTMENT) is otherwise fixed forever at whatever the host
manually picked on the Guided Contextual Input screen at session creation —
there is no clock-based classification anywhere in this app (context_vector's
"time" is a free host pick from a fixed 5-label list, never derived from the
wall clock). This module adds a periodic, elapsed-time-since-session-start
progression through that same label sequence, so a session that runs long
enough drifts its target_energy (and only target_energy — mood/genre/language
are untouched) the way a real listening session's vibe would.

The host's original pick stays authoritative as the starting point — it is
never immediately overridden to match the real clock, and the sequence only
ever steps forward, never wraps past "Late Night". Recoverable at any time
purely from already-persisted data (context_vector["time"] + sessions.created_at),
so no new column/state is needed — see compute_expected_time_of_day.

Re-ranking reuses queue_dna_engine.rerank_from_candidates (Section 6) exactly
as the skip path does — reads/writes only session_candidate_tracks and
queue_tracks, zero external API calls, and protects the currently-playing
track (position 0) the same way a non-skip re-rank always has.
"""

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.models import Session, SessionCandidateTrack
from app.services.connection_manager import manager
from app.services.match_score import compute_match_score
from app.services.mood_to_audio_features import MOOD_AUDIO_MAP, NEUTRAL_MOOD, TIME_ENERGY_ADJUSTMENT
from app.services.queue_dna_engine import rerank_from_candidates

logger = logging.getLogger(__name__)

# How often the background sweep checks active sessions for drift.
DRIFT_CHECK_INTERVAL_SECONDS = 600  # 10 minutes

# Ordered time-of-day progression — must match mood_to_audio_features.py's
# TIME_ENERGY_ADJUSTMENT keys. A session's time_of_day only ever moves right
# along this list; it stops at "Late Night" rather than wrapping to "Morning".
TIME_OF_DAY_SEQUENCE: list[str] = ["Morning", "Afternoon", "Evening", "Night", "Late Night"]

# Elapsed hours of session runtime before time_of_day advances one position.
# 24 hours split evenly across the 5 labels (24 / 5 = 4.8h/step) — proportional
# to how the labels partition a real day, even though a JAM session won't
# literally run 24 hours. This keeps ordinary multi-hour sessions from
# drifting at all (most JAMs are well under 4.8h) while still advancing one a
# genuinely long-running session, which is the actual point of this feature.
DRIFT_STEP_HOURS: float = 24 / 5


def compute_expected_time_of_day(
    context_vector: dict, created_at: datetime, now: datetime
) -> str | None:
    """
    Pure function — the time_of_day label a session *should* currently show,
    derived only from its original host pick and elapsed wall-clock time.
    Deterministic and idempotent: calling this twice with the same inputs
    (or after a missed/delayed sweep tick) always gives the same answer, so no
    "how many steps already applied" bookkeeping is needed anywhere.

    Returns None if the session never had a recognized time_of_day pick to
    begin with (context_vector["time"] missing, None, or free text outside
    the 5-label set) — nothing to drift in that case.
    """
    original = context_vector.get("time") if context_vector else None
    if original not in TIME_OF_DAY_SEQUENCE:
        return None

    original_index = TIME_OF_DAY_SEQUENCE.index(original)
    # sessions.created_at is DateTime(timezone=True) and always written as UTC
    # (see session_service.create_session), but can round-trip back naive
    # under the SQLite test DB — same defensive normalization as
    # oauth_state_service.py's expires_at check.
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    elapsed_hours = max(0.0, (now - created_at).total_seconds() / 3600)
    steps = int(elapsed_hours // DRIFT_STEP_HOURS)
    expected_index = min(original_index + steps, len(TIME_OF_DAY_SEQUENCE) - 1)
    return TIME_OF_DAY_SEQUENCE[expected_index]


async def _drift_one_session(db, session: Session) -> bool:
    """
    Recomputes session.session_dna's time_of_day/target_energy in place if
    elapsed time means it should have advanced, rescoring the cached
    candidate pool against the updated target and re-ranking from it.

    Returns True if the session actually drifted (DB was written, caller
    should broadcast); False if nothing changed (nothing to do).

    No external API calls anywhere in this path: reads/writes only
    sessions.session_dna, session_candidate_tracks, and queue_tracks (via
    rerank_from_candidates, which already guarantees this — see its own
    docstring and test_skip.py's test_skip_never_calls_external_api).
    """
    now = datetime.now(timezone.utc)
    expected = compute_expected_time_of_day(session.context_vector or {}, session.created_at, now)
    if expected is None:
        return False

    current_dna = session.session_dna or {}
    if current_dna.get("time_of_day") == expected:
        return False

    # Only target_energy is time-dependent (mood_to_audio_features.py) —
    # target_valence/target_genres/target_language/raw_genre/raw_mood are
    # carried through unchanged, exactly as the design requires.
    mood = current_dna.get("raw_mood")
    mood_features = MOOD_AUDIO_MAP.get(mood, NEUTRAL_MOOD) if mood else NEUTRAL_MOOD
    time_adjustment = TIME_ENERGY_ADJUSTMENT.get(expected, 0.0)
    new_target_energy = max(0.0, min(1.0, mood_features["energy"] + time_adjustment))

    updated_dna = {**current_dna, "time_of_day": expected, "target_energy": new_target_energy}
    # Reassign (not mutate) the dict so SQLAlchemy's change-tracking on the
    # JSONB column reliably picks it up.
    session.session_dna = updated_dna

    cand_result = await db.execute(
        select(SessionCandidateTrack).where(SessionCandidateTrack.session_id == session.id)
    )
    for row in cand_result.scalars().all():
        track_features = {
            "valence": float(row.valence) if row.valence is not None else None,
            "energy": float(row.energy) if row.energy is not None else None,
            "genres": row.genres,
            "title": row.title,
        }
        result = compute_match_score(track_features, updated_dna)
        row.match_score = result["score"]
        row.confidence = result["confidence"]

    # Reselects/reorders from the now-freshly-scored pool; protects the
    # currently-playing track (position 0) by default since no track is being
    # skipped here — same guarantee the skip path relies on. Commits.
    await rerank_from_candidates(db, session)
    return True


async def _drift_sweep(db, connected_session_ids: set[str], broadcast_fn) -> None:
    """Core sweep logic against an explicit db session — testable directly,
    same split as queue_optimizer.py's _rerank/rerank_queue."""
    if not connected_session_ids:
        return

    result = await db.execute(
        select(Session.id).where(
            Session.status == "active",
            Session.id.in_([UUID(sid) for sid in connected_session_ids]),
        )
    )
    session_ids = [row[0] for row in result.all()]

    for session_id in session_ids:
        try:
            session = await db.get(Session, session_id)
            if session is None or session.status != "active":
                continue
            drifted = await _drift_one_session(db, session)
            if drifted:
                await broadcast_fn(str(session.id), {
                    "event": "queue_updated",
                    "session_id": str(session.id),
                    "queue_build_status": session.queue_build_status,
                })
        except Exception:
            # One session's failure must not take down the rest of the sweep
            # — same isolation guarantee as optimize_queue/rerank_queue.
            logger.exception("time-of-day drift failed for session %s", session_id)


async def run_drift_sweep(broadcast_fn) -> None:
    """Production entry point for one sweep tick. Manages its own DB session,
    same pattern as optimize_queue/rerank_queue."""
    connected_session_ids = manager.connected_session_ids()
    if not connected_session_ids:
        return
    async with AsyncSessionLocal() as db:
        await _drift_sweep(db, connected_session_ids, broadcast_fn)


async def start_drift_scheduler() -> None:
    """Runs forever until cancelled (app shutdown) — started from main.py's
    lifespan handler. Bare-asyncio periodic loop, consistent with this
    codebase's existing time-based coordination (debounce_service.py) rather
    than a new scheduler dependency."""
    while True:
        try:
            await asyncio.sleep(DRIFT_CHECK_INTERVAL_SECONDS)
            await run_drift_sweep(manager.broadcast)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("time-of-day drift sweep crashed")
