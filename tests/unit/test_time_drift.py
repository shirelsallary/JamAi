"""Time-of-day drift re-ranking (app/services/time_drift.py).

Mirrors test_skip.py's conventions (same _seeded_session shape, same
"no external API calls" monkeypatch pattern) since drift reuses
rerank_from_candidates exactly as the skip path does.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

import app.adapters.platform_factory as platform_factory
from app.models.models import QueueTrack, SessionCandidateTrack, SessionParticipant
from app.services.auth_service import register_user
from app.services.session_service import create_session
from app.services.social_overlap import normalize_key
from app.services.time_drift import (
    DRIFT_STEP_HOURS,
    TIME_OF_DAY_SEQUENCE,
    _drift_one_session,
    _drift_sweep,
    compute_expected_time_of_day,
)

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# compute_expected_time_of_day — pure function, no DB
# ---------------------------------------------------------------------------

def test_no_drift_at_zero_elapsed_time():
    assert compute_expected_time_of_day({"time": "Evening"}, _NOW, _NOW) == "Evening"


def test_advances_one_step_after_one_step_duration():
    created_at = _NOW - timedelta(hours=DRIFT_STEP_HOURS + 0.1)
    assert compute_expected_time_of_day({"time": "Evening"}, created_at, _NOW) == "Night"


def test_stays_put_just_under_one_step_duration():
    created_at = _NOW - timedelta(hours=DRIFT_STEP_HOURS - 0.1)
    assert compute_expected_time_of_day({"time": "Evening"}, created_at, _NOW) == "Evening"


def test_advances_two_steps_after_two_step_durations():
    created_at = _NOW - timedelta(hours=2 * DRIFT_STEP_HOURS + 0.1)
    assert compute_expected_time_of_day({"time": "Evening"}, created_at, _NOW) == "Late Night"


def test_never_wraps_past_late_night():
    # Evening -> Night -> Late Night is only 2 steps; way more elapsed time
    # must still land on Late Night, never wrap back to Morning.
    created_at = _NOW - timedelta(hours=100 * DRIFT_STEP_HOURS)
    assert compute_expected_time_of_day({"time": "Evening"}, created_at, _NOW) == "Late Night"


def test_already_at_late_night_never_moves_regardless_of_elapsed_time():
    created_at = _NOW - timedelta(hours=50 * DRIFT_STEP_HOURS)
    assert compute_expected_time_of_day({"time": "Late Night"}, created_at, _NOW) == "Late Night"


def test_no_original_time_of_day_returns_none():
    created_at = _NOW - timedelta(hours=10 * DRIFT_STEP_HOURS)
    assert compute_expected_time_of_day({"time": None}, created_at, _NOW) is None
    assert compute_expected_time_of_day({}, created_at, _NOW) is None


def test_unrecognized_time_of_day_returns_none():
    created_at = _NOW - timedelta(hours=10 * DRIFT_STEP_HOURS)
    assert compute_expected_time_of_day({"time": "Brunch"}, created_at, _NOW) is None


def test_sequence_is_the_five_known_labels_in_order():
    assert TIME_OF_DAY_SEQUENCE == ["Morning", "Afternoon", "Evening", "Night", "Late Night"]


# ---------------------------------------------------------------------------
# DB-backed: _drift_one_session / _drift_sweep
# ---------------------------------------------------------------------------

async def _connected_user(db, email):
    user = await register_user(db, email, "Secure123!")
    user.platform = "spotify"
    user.platform_token = "tok"
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _seeded_session(db, *, time_of_day="Night", elapsed_hours=6.0, threshold=0.46):
    """Session whose original time_of_day pick was `time_of_day`, backdated
    so a drift sweep now sees `elapsed_hours` of runtime. Two candidates
    engineered so the first stays above `threshold` after the energy shift
    from Night->Late Night and the second doesn't — full (2/2) -> partial (1/2)."""
    host = await _connected_user(db, "drift_host@jam.com")
    session = await create_session(
        db, host, {"genre": None, "mood": "Chill", "language": None, "time": time_of_day},
        "spotify", target_duration_minutes=10,  # -> target_queue_size == 3
    )
    session.created_at = datetime.now(timezone.utc) - timedelta(hours=elapsed_hours)
    session.effective_threshold = threshold

    participant = (
        await db.execute(select(SessionParticipant).where(SessionParticipant.session_id == session.id))
    ).scalar_one()

    # Chill mood: valence 0.5, energy 0.25. Night adjustment -0.05 (target
    # energy 0.20 initially); Late Night adjustment -0.15 (target energy 0.10
    # after drift). No genre/language selected, so raw_score is audio-only.
    db.add(SessionCandidateTrack(
        session_id=session.id, participant_id=participant.id, source_platform="spotify",
        track_id="c0", title="Candidate 0", artist="Artist",
        duration_ms=200_000, valence=0.5, energy=0.20, genres=[],
        normalized_track_key=normalize_key("Candidate 0", "Artist"),
        normalized_artist_key=normalize_key("", "Artist"),
        match_score=0.5, confidence="high", playlist_overlap_count=0, shared_artist_count=0,
    ))
    db.add(SessionCandidateTrack(
        session_id=session.id, participant_id=participant.id, source_platform="spotify",
        track_id="c1", title="Candidate 1", artist="Artist",
        duration_ms=200_000, valence=0.5, energy=0.25, genres=[],
        normalized_track_key=normalize_key("Candidate 1", "Artist"),
        normalized_artist_key=normalize_key("", "Artist"),
        match_score=0.4823, confidence="high", playlist_overlap_count=0, shared_artist_count=0,
    ))
    db.add(QueueTrack(
        session_id=session.id, track_id="current", platform="spotify", title="Currently Playing",
        artist="Artist", duration_ms=200_000, weight_score=0.99, confidence="high",
        playlist_overlap_count=0, shared_artist_count=0, position=0, is_current=True,
    ))
    await db.commit()
    await db.refresh(session)
    return session


async def test_drift_updates_time_of_day_and_target_energy(db):
    session = await _seeded_session(db)
    assert session.session_dna["time_of_day"] == "Night"

    drifted = await _drift_one_session(db, session)

    assert drifted is True
    assert session.session_dna["time_of_day"] == "Late Night"
    assert session.session_dna["target_energy"] == 0.10
    # Mood/genre/language untouched by drift.
    assert session.session_dna["target_valence"] == 0.5
    assert session.session_dna["target_genres"] == []
    assert session.session_dna["target_language"] is None


async def test_drift_no_op_when_time_of_day_unchanged(db):
    # elapsed_hours=1 is nowhere near DRIFT_STEP_HOURS (4.8h) -> no advance.
    session = await _seeded_session(db, elapsed_hours=1.0)
    drifted = await _drift_one_session(db, session)
    assert drifted is False
    assert session.session_dna["time_of_day"] == "Night"


async def test_drift_never_calls_external_api(db, monkeypatch):
    session = await _seeded_session(db)

    def boom(*args, **kwargs):
        raise AssertionError("get_platform_adapter must never be called during a drift re-rank")

    monkeypatch.setattr(platform_factory, "get_platform_adapter", boom)

    # Should not raise.
    await _drift_one_session(db, session)


async def test_drift_protects_currently_playing_track(db):
    session = await _seeded_session(db)

    await _drift_one_session(db, session)

    result = await db.execute(
        select(QueueTrack).where(QueueTrack.session_id == session.id).order_by(QueueTrack.position)
    )
    tracks = list(result.scalars().all())
    assert tracks[0].is_current is True
    assert tracks[0].track_id == "current"


async def test_drift_can_flip_queue_build_status_full_to_partial(db):
    session = await _seeded_session(db)

    # Pre-drift: both candidates clear threshold=0.46 against target_energy=0.20 -> full.
    from app.services.queue_dna_engine import rerank_from_candidates
    await rerank_from_candidates(db, session)
    assert session.queue_build_status == "full"

    # Drift shifts target_energy to 0.10: c0 (energy .20) still clears 0.46,
    # c1 (energy .25) drops below it -> only 1 of 2 -> partial.
    await _drift_one_session(db, session)
    assert session.queue_build_status == "partial"


async def test_drift_sweep_skips_sessions_with_no_connected_participants(db):
    session = await _seeded_session(db)
    broadcasts = []

    async def record_broadcast(session_id, message):
        broadcasts.append((session_id, message))

    await _drift_sweep(db, connected_session_ids=set(), broadcast_fn=record_broadcast)

    await db.refresh(session)
    assert session.session_dna["time_of_day"] == "Night"  # untouched
    assert broadcasts == []


async def test_drift_sweep_processes_connected_sessions_and_broadcasts(db):
    session = await _seeded_session(db)
    broadcasts = []

    async def record_broadcast(session_id, message):
        broadcasts.append((session_id, message))

    await _drift_sweep(db, connected_session_ids={str(session.id)}, broadcast_fn=record_broadcast)

    await db.refresh(session)
    assert session.session_dna["time_of_day"] == "Late Night"
    assert len(broadcasts) == 1
    sid, message = broadcasts[0]
    assert sid == str(session.id)
    assert message["event"] == "queue_updated"
    assert message["session_id"] == str(session.id)
