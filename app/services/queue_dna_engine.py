"""
Queue DNA Agent — Sections 3, 4, 5, 6.

Pure(ish) engine logic, separate from app/services/queue_optimizer.py (which
owns the DB-session lifecycle and is the entry point routers call). Split this
way so the scoring/ranking logic here is unit-testable without spinning up a
FastAPI request or a real DB session for every test.
"""

import logging
from uuid import UUID

from sqlalchemy import select

from app.adapters.platform_factory import NoPlatformConnectedError, get_platform_adapter
from app.models.models import QueueTrack, Session, SessionCandidateTrack
from app.services.match_score import compute_match_score
from app.services.session_dna import load_or_build_session_dna
from app.services.social_overlap import (
    ScannedPlaylist,
    compute_social_overlap,
    normalize_key,
    social_sort_key,
)

logger = logging.getLogger(__name__)

THRESHOLD_LADDER = [0.80, 0.75, 0.70, 0.65, 0.60, 0.55, 0.50]
MAX_PUBLIC_SEARCH_QUERIES = 5
DEFAULT_QUEUE_SIZE = 25
AVG_TRACK_MINUTES = 3.5


def target_queue_size(session: Session) -> int:
    if session.target_duration_minutes:
        return max(1, round(session.target_duration_minutes / AVG_TRACK_MINUTES))
    return DEFAULT_QUEUE_SIZE


# ---------------------------------------------------------------------------
# Section 3 — candidate collection (saved playlists, not top-tracks)
# ---------------------------------------------------------------------------

async def _enrich_with_features_and_genres(adapter, tracks: list[dict]) -> dict[str, dict]:
    """Batch-fetch audio features + artist genres once for a set of tracks.
    Returns {track_id: {"valence":..,"energy":..,"genres":[...]}}."""
    track_ids = list({t["track_id"] for t in tracks if t.get("track_id")})
    artist_ids = list({t["artist_id"] for t in tracks if t.get("artist_id")})

    features_by_id: dict[str, dict] = {}
    if track_ids and hasattr(adapter, "get_audio_features"):
        try:
            for i in range(0, len(track_ids), 100):
                batch = track_ids[i : i + 100]
                for feat in await adapter.get_audio_features(batch):
                    features_by_id[feat["track_id"]] = feat
        except Exception:
            logger.exception("audio-feature batch fetch failed")

    genres_by_artist: dict[str, list[str]] = {}
    if artist_ids and hasattr(adapter, "get_artists_genres"):
        try:
            genres_by_artist = await adapter.get_artists_genres(artist_ids)
        except Exception:
            logger.exception("artist-genre batch fetch failed")

    enrichment: dict[str, dict] = {}
    for t in tracks:
        feat = features_by_id.get(t["track_id"], {})
        genres = genres_by_artist.get(t.get("artist_id"), []) if t.get("artist_id") else []
        # YouTube tracks have no artist_id (genres_by_artist is always {} for
        # them) — fall back to the playlist-name-inferred genres already
        # attached to the raw track dict by YouTubeAdapter.get_playlist_tracks.
        if not genres and t.get("genres"):
            genres = t["genres"]
        enrichment[t["track_id"]] = {
            "valence": feat.get("valence"),
            "energy": feat.get("energy"),
            "genres": genres,
        }
    return enrichment


async def scan_saved_playlists(
    user, selected_platform: str
) -> tuple[list[dict], list[ScannedPlaylist]]:
    """
    Section 3 — scans a single participant's SAVED PLAYLISTS (not top-tracks) on
    the platform THEY selected (may differ from session.host_platform, Section 0).

    Returns (candidate_tracks, scanned_playlists):
      candidate_tracks: deduped-by-track_id list of raw track dicts (no score yet).
      scanned_playlists: one ScannedPlaylist per playlist, for social-overlap use.
    """
    adapter = get_platform_adapter(user)  # raises NoPlatformConnectedError — let caller decide
    playlists = await adapter.get_user_playlists()

    raw_by_playlist: list[tuple[str, list[dict]]] = []
    for playlist in playlists:
        try:
            tracks = await adapter.get_playlist_tracks(playlist["playlist_id"])
        except Exception:
            logger.exception(
                "failed scanning playlist %s for user %s", playlist["playlist_id"], user.id
            )
            continue
        raw_by_playlist.append((playlist["playlist_id"], tracks))

    all_tracks = [t for _, tracks in raw_by_playlist for t in tracks]
    enrichment = await _enrich_with_features_and_genres(adapter, all_tracks)

    candidate_tracks: dict[str, dict] = {}
    scanned_playlists: list[ScannedPlaylist] = []
    for playlist_id, tracks in raw_by_playlist:
        scanned = ScannedPlaylist(playlist_id=playlist_id)
        for t in tracks:
            track_key = normalize_key(t["title"], t["artist"])
            artist_key = normalize_key("", t["artist"])
            scanned.normalized_track_keys.add(track_key)
            scanned.normalized_artist_keys.add(artist_key)

            if t["track_id"] in candidate_tracks:
                continue
            extra = enrichment.get(t["track_id"], {})
            candidate_tracks[t["track_id"]] = {
                "track_id": t["track_id"],
                "platform": selected_platform,
                "title": t["title"],
                "artist": t["artist"],
                "duration_ms": t["duration_ms"],
                "valence": extra.get("valence"),
                "energy": extra.get("energy"),
                "genres": extra.get("genres", []),
                "normalized_track_key": track_key,
                "normalized_artist_key": artist_key,
            }
        scanned_playlists.append(scanned)

    return list(candidate_tracks.values()), scanned_playlists


def score_candidates(tracks: list[dict], dna: dict) -> list[dict]:
    scored = []
    for t in tracks:
        result = compute_match_score(t, dna)
        scored.append({**t, "match_score": result["score"], "confidence": result["confidence"]})
    return scored


def attach_social_overlap(track: dict, all_participants_saved_playlists: list[ScannedPlaylist]) -> dict:
    overlap, shared = compute_social_overlap(
        track["normalized_track_key"], track["normalized_artist_key"], all_participants_saved_playlists
    )
    return {**track, "playlist_overlap_count": overlap, "shared_artist_count": shared}


# ---------------------------------------------------------------------------
# Section 4 — descending threshold ladder + public search chaining
# ---------------------------------------------------------------------------

def _dedupe_by_normalized_key(tracks: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for t in tracks:
        seen.setdefault(t["normalized_track_key"], t)
    return list(seen.values())


async def chain_public_playlist_search(
    dna: dict,
    host_platform: str,
    host_adapter,
    already_have: list[dict],
    min_threshold: float,
    max_queries: int,
    target_size: int,
) -> list[dict]:
    """Section 4 — always searches host_platform only (never worth resolving a
    public-search hit found on a different platform)."""
    have_keys = {t["normalized_track_key"] for t in already_have}

    genre = dna.get("raw_genre") or ""
    mood = dna.get("raw_mood") or ""
    language = dna.get("target_language") or ""
    keyword_combos = [
        " ".join(p for p in [genre, mood, language] if p),
        " ".join(p for p in [genre, mood] if p),
        mood,
    ]
    keyword_combos = [k for k in dict.fromkeys(keyword_combos) if k.strip()]

    found: list[dict] = []
    queries_used = 0

    for keyword in keyword_combos:
        if queries_used >= max_queries or len(already_have) + len(found) >= target_size:
            break
        try:
            playlists = await host_adapter.search_playlists(
                keyword, limit=max(1, max_queries - queries_used)
            )
        except Exception:
            logger.exception("public playlist search failed for keyword '%s'", keyword)
            continue

        for playlist in playlists:
            if queries_used >= max_queries:
                break
            queries_used += 1
            try:
                tracks = await host_adapter.get_playlist_tracks(playlist["playlist_id"])
            except Exception:
                logger.exception("failed fetching public playlist %s", playlist["playlist_id"])
                continue

            enrichment = await _enrich_with_features_and_genres(host_adapter, tracks)
            for t in tracks:
                key = normalize_key(t["title"], t["artist"])
                if key in have_keys:
                    continue
                extra = enrichment.get(t["track_id"], {})
                candidate = {
                    "track_id": t["track_id"],
                    "platform": host_platform,
                    "title": t["title"],
                    "artist": t["artist"],
                    "duration_ms": t["duration_ms"],
                    "valence": extra.get("valence"),
                    "energy": extra.get("energy"),
                    "genres": extra.get("genres", []),
                    "normalized_track_key": key,
                    "normalized_artist_key": normalize_key("", t["artist"]),
                }
                result = compute_match_score(candidate, dna)
                if result["score"] >= min_threshold:
                    candidate["match_score"] = result["score"]
                    candidate["confidence"] = result["confidence"]
                    found.append(candidate)
                    have_keys.add(key)

            if len(already_have) + len(found) >= target_size:
                break

    return found


def build_ranked_queue(
    dna: dict,
    candidates: list[dict],
    all_scanned_playlists: list[ScannedPlaylist],
    target_size: int,
) -> tuple[list[dict], float, bool]:
    """
    Runs the threshold ladder (Section 4) + social overlap (2.5) over an
    already-scored candidate pool. Returns (accepted_with_overlap, effective_threshold, reached_target).

    Split out from build_initial_queue so the ladder-descent logic itself is
    directly unit-testable without mocking adapters/DB at all (tests 3, 10, 11, 12).
    """
    deduped = _dedupe_by_normalized_key(candidates)
    with_overlap = [attach_social_overlap(t, all_scanned_playlists) for t in deduped]

    accepted: list[dict] = []
    effective_threshold = THRESHOLD_LADDER[-1]
    reached = False
    for threshold in THRESHOLD_LADDER:
        accepted = [t for t in with_overlap if t["match_score"] >= threshold]
        effective_threshold = threshold
        if len(accepted) >= target_size:
            reached = True
            break

    accepted.sort(key=social_sort_key)
    return accepted, effective_threshold, reached


# ---------------------------------------------------------------------------
# Candidate-pool persistence (Section 5's "cache", used by Section 6 skip too)
# ---------------------------------------------------------------------------

async def persist_candidate_pool(db, session_id: UUID, participant_id: UUID, scored_tracks: list[dict]) -> None:
    if not scored_tracks:
        return
    existing = await db.execute(
        select(SessionCandidateTrack.track_id).where(
            SessionCandidateTrack.session_id == session_id,
            SessionCandidateTrack.participant_id == participant_id,
        )
    )
    already_present = {row[0] for row in existing.all()}

    for t in scored_tracks:
        if t["track_id"] in already_present:
            continue
        db.add(SessionCandidateTrack(
            session_id=session_id,
            participant_id=participant_id,
            source_platform=t["platform"],
            track_id=t["track_id"],
            title=t["title"],
            artist=t["artist"],
            duration_ms=max(1, t["duration_ms"]),
            valence=t.get("valence"),
            energy=t.get("energy"),
            genres=t.get("genres", []),
            normalized_track_key=t["normalized_track_key"],
            normalized_artist_key=t["normalized_artist_key"],
            match_score=t["match_score"],
            confidence=t["confidence"],
            playlist_overlap_count=t.get("playlist_overlap_count", 0),
            shared_artist_count=t.get("shared_artist_count", 0),
        ))
    await db.commit()


async def update_social_overlap_incremental(
    db, session_id: UUID, new_playlists: list[ScannedPlaylist]
) -> int:
    """Section 2.5/5 — targeted increment only, never a full recomputation.
    Returns the number of candidate rows touched (useful for tests)."""
    new_track_keys: set[str] = set()
    new_artist_keys: set[str] = set()
    for p in new_playlists:
        new_track_keys |= p.normalized_track_keys
        new_artist_keys |= p.normalized_artist_keys

    if not new_track_keys and not new_artist_keys:
        return 0

    result = await db.execute(
        select(SessionCandidateTrack).where(SessionCandidateTrack.session_id == session_id)
    )
    rows = list(result.scalars().all())

    touched = 0
    for row in rows:
        inc_track = row.normalized_track_key in new_track_keys
        inc_artist = row.normalized_artist_key in new_artist_keys
        if inc_track or inc_artist:
            row.playlist_overlap_count += 1 if inc_track else 0
            row.shared_artist_count += 1 if inc_artist else 0
            touched += 1
    await db.commit()
    return touched


# ---------------------------------------------------------------------------
# Skip protection helper (Section 6) — shared by rerank + merge
# ---------------------------------------------------------------------------

def _queue_track_to_pool_dict(t: QueueTrack) -> dict:
    return {
        "track_id": t.track_id,
        "platform": t.platform,
        "title": t.title,
        "artist": t.artist,
        "duration_ms": t.duration_ms,
        "match_score": float(t.weight_score),
        "confidence": t.confidence,
        "playlist_overlap_count": t.playlist_overlap_count,
        "shared_artist_count": t.shared_artist_count,
        "normalized_track_key": normalize_key(t.title, t.artist),
    }


async def rerank_from_candidates(db, session: Session, skipped_track_id: str | None = None) -> str:
    """
    Section 6 — re-rank using ONLY the stored candidate pool (session_candidate_tracks)
    and the existing queue_tracks rows. No adapter/HTTP calls whatsoever.

    If skipped_track_id is given, the track at position 0 marked is_current with
    that id is dropped entirely (it was skipped) and a new track is promoted to
    position 0. Otherwise the currently-playing track is protected — reinserted
    unchanged at position 0 (Section 6 "currently playing" protection).

    Returns the resulting queue_build_status.
    """
    result = await db.execute(
        select(QueueTrack).where(QueueTrack.session_id == session.id).order_by(QueueTrack.position)
    )
    existing = list(result.scalars().all())
    current = next((t for t in existing if t.is_current), None)

    protect_current = current is not None and str(current.id) != skipped_track_id

    threshold = (
        float(session.effective_threshold) if session.effective_threshold is not None else THRESHOLD_LADDER[-1]
    )
    cand_result = await db.execute(
        select(SessionCandidateTrack).where(
            SessionCandidateTrack.session_id == session.id,
            SessionCandidateTrack.match_score >= threshold,
        )
    )
    pool = [
        {
            "track_id": c.track_id,
            "platform": c.source_platform,
            "title": c.title,
            "artist": c.artist,
            "duration_ms": c.duration_ms,
            "match_score": float(c.match_score),
            "confidence": c.confidence,
            "playlist_overlap_count": c.playlist_overlap_count,
            "shared_artist_count": c.shared_artist_count,
            "normalized_track_key": c.normalized_track_key,
        }
        for c in cand_result.scalars().all()
    ]

    # All non-current queue_tracks rows are deleted and rebuilt fresh from the
    # pool below, so the only track that needs excluding from the pool is the
    # current one — either because it's about to be reinserted verbatim
    # (protect mode) or because it was just skipped and shouldn't immediately
    # reappear in the same re-rank.
    if current is not None:
        current_key = normalize_key(current.title, current.artist)
        pool = [t for t in pool if t["normalized_track_key"] != current_key]
    pool.sort(key=social_sort_key)

    for t in existing:
        await db.delete(t)
    await db.flush()

    size = target_queue_size(session)
    position = 0
    if protect_current:
        db.add(QueueTrack(
            session_id=session.id, track_id=current.track_id, platform=current.platform,
            title=current.title, artist=current.artist, duration_ms=current.duration_ms,
            weight_score=current.weight_score, confidence=current.confidence,
            playlist_overlap_count=current.playlist_overlap_count,
            shared_artist_count=current.shared_artist_count, position=0, is_current=True,
        ))
        position = 1

    remaining = max(0, size - position)
    for i, t in enumerate(pool[:remaining]):
        is_new_current = position == 0 and i == 0
        db.add(QueueTrack(
            session_id=session.id, track_id=t["track_id"], platform=t["platform"], title=t["title"],
            artist=t["artist"], duration_ms=max(1, t["duration_ms"]), weight_score=round(t["match_score"], 4),
            confidence=t["confidence"], playlist_overlap_count=t["playlist_overlap_count"],
            shared_artist_count=t["shared_artist_count"], position=position, is_current=is_new_current,
        ))
        position += 1

    total_in_queue = position
    if total_in_queue == 0:
        status = "empty"
    elif total_in_queue < size:
        status = "partial"
    else:
        status = "full"

    session.queue_build_status = status
    await db.commit()
    return status


# ---------------------------------------------------------------------------
# Section 5 — merging a new guest's accepted candidates into the live queue
# ---------------------------------------------------------------------------

async def merge_into_queue(db, session: Session) -> str:
    """Folds any newly-persisted candidate rows into the visible queue,
    protecting the currently-playing track. Thin wrapper over
    rerank_from_candidates with no skipped_track_id (= protect mode)."""
    return await rerank_from_candidates(db, session, skipped_track_id=None)


async def on_guest_joined(db, session: Session, new_participant, new_user) -> None:
    """
    Section 5 — does NOT rescan any existing participant. Only the new guest's
    own playlists are scanned; overlap on existing candidate rows is updated
    with a targeted increment (not recomputed from scratch).
    """
    dna = load_or_build_session_dna(session)
    try:
        new_tracks, new_playlists = await scan_saved_playlists(
            new_user, new_participant.selected_platform
        )
    except NoPlatformConnectedError:
        return

    new_scored = score_candidates(new_tracks, dna)

    await update_social_overlap_incremental(db, session.id, new_playlists)

    # KNOWN LIMITATION (deferred — see README "Known Limitations"): this only
    # checks the new guest's own tracks against the new guest's OWN playlists,
    # so a track this guest contributes gets zero overlap credit even if the
    # exact same song already sits in the host's (or an earlier guest's)
    # playlist. The reverse direction — existing candidate rows getting credit
    # from this guest's playlists — IS handled correctly above via
    # update_social_overlap_incremental. Fixing this symmetrically would need
    # either a schema addition (persisting playlist_id per candidate row so
    # earlier participants' playlist key-sets can be reconstructed) or an
    # accepted approximation (treating each participant's whole candidate set
    # as one merged pseudo-playlist). Not implemented — deferred by product
    # decision, not a schema/db change we're making right now.
    new_with_overlap = [attach_social_overlap(t, new_playlists) for t in new_scored]
    await persist_candidate_pool(db, session.id, new_participant.id, new_with_overlap)

    await merge_into_queue(db, session)
