"""Real Spotify playback control (spotify_playback.py) — resolving the
SESSION HOST's adapter (never the calling user's) is the caller's
responsibility (queue_optimizer.py, routers/queue.py); attempt_spotify_playback
itself never raises and never lets a playback failure block or corrupt the
DNA Agent's queue state."""

import json

from sqlalchemy import select

from app.routers.queue import get_queue
from app.services.spotify_playback import attempt_spotify_playback
from app.models.models import QueueTrack, SessionCandidateTrack, SessionParticipant, User
from app.services.auth_service import register_user
from app.services.queue_optimizer import _rerank
from app.services.session_service import create_session
from app.services.social_overlap import normalize_key
from tests.unit.fakes import FakeSpotifyAdapter


async def _connected_user(db, email, platform="spotify"):
    user = await register_user(db, email, "Secure123!")
    user.platform = platform
    user.platform_token = "tok"
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _seeded_session(db):
    host = await _connected_user(db, "playback_host@jam.com")
    session = await create_session(
        db, host, {"genre": "Pop", "mood": "Chill", "language": None, "time": None}, "spotify"
    )
    participant = (
        await db.execute(select(SessionParticipant).where(SessionParticipant.session_id == session.id))
    ).scalar_one()

    for i in range(3):
        db.add(SessionCandidateTrack(
            session_id=session.id, participant_id=participant.id, source_platform="spotify",
            track_id=f"c{i}", title=f"Candidate {i}", artist="Artist",
            duration_ms=200_000, valence=0.5, energy=0.5, genres=[],
            normalized_track_key=normalize_key(f"Candidate {i}", "Artist"),
            normalized_artist_key=normalize_key("", "Artist"),
            match_score=0.9 - i * 0.05, confidence="high",
            playlist_overlap_count=0, shared_artist_count=0,
        ))
    session.effective_threshold = 0.5
    db.add(QueueTrack(
        session_id=session.id, track_id="current", platform="spotify", title="Currently Playing",
        artist="Artist", duration_ms=200_000, weight_score=0.99, confidence="high",
        playlist_overlap_count=0, shared_artist_count=0, position=0, is_current=True,
    ))
    await db.commit()
    await db.refresh(session)
    return session, host


# ---------------------------------------------------------------------------
# attempt_spotify_playback — pure, takes an already-resolved adapter
# ---------------------------------------------------------------------------

async def test_attempt_spotify_playback_success(db):
    session, host = await _seeded_session(db)
    fake = FakeSpotifyAdapter(devices=[{"id": "dev1", "is_active": True}])

    result = await attempt_spotify_playback(fake, session, "track123")

    assert result == {"status": "playing"}
    assert ("start_playback", "track123", "dev1") in fake.calls


async def test_attempt_spotify_playback_no_active_device(db):
    session, host = await _seeded_session(db)
    fake = FakeSpotifyAdapter(devices=[{"id": "dev1", "is_active": False}])

    result = await attempt_spotify_playback(fake, session, "track123")

    assert result == {"status": "no_active_device"}
    assert not any(call[0] == "start_playback" for call in fake.calls)


async def test_attempt_spotify_playback_no_devices_at_all(db):
    session, host = await _seeded_session(db)
    fake = FakeSpotifyAdapter(devices=[])

    result = await attempt_spotify_playback(fake, session, "track123")

    assert result == {"status": "no_active_device"}


async def test_attempt_spotify_playback_host_not_connected(db):
    session, host = await _seeded_session(db)

    result = await attempt_spotify_playback(None, session, "track123")

    assert result == {"status": "error", "reason": "HOST_NOT_CONNECTED"}


async def test_attempt_spotify_playback_start_failure_is_reported_not_raised(db):
    session, host = await _seeded_session(db)
    fake = FakeSpotifyAdapter(
        devices=[{"id": "dev1", "is_active": True}],
        start_playback_raises=RuntimeError("Spotify 500"),
    )

    result = await attempt_spotify_playback(fake, session, "track123")

    assert result == {"status": "error", "reason": "PLAYBACK_START_FAILED"}


async def test_attempt_spotify_playback_device_check_failure_is_reported_not_raised(db):
    session, host = await _seeded_session(db)

    class ExplodingAdapter:
        async def get_available_devices(self):
            raise RuntimeError("Spotify 500")

    result = await attempt_spotify_playback(ExplodingAdapter(), session, "track123")

    assert result == {"status": "error", "reason": "DEVICE_CHECK_FAILED"}


async def test_attempt_spotify_playback_not_a_spotify_session(db):
    host = await _connected_user(db, "yt_host@jam.com", platform="youtube")
    session = await create_session(
        db, host, {"genre": "Pop", "mood": "Chill", "language": None, "time": None}, "youtube"
    )

    result = await attempt_spotify_playback(FakeSpotifyAdapter(), session, "track123")

    assert result == {"status": "error", "reason": "NOT_SPOTIFY_SESSION"}


# ---------------------------------------------------------------------------
# _rerank — resolves the HOST's adapter (never current_user's), and a
# playback failure of any kind must never block the DB re-rank broadcast.
# ---------------------------------------------------------------------------

async def test_rerank_resolves_host_adapter_not_caller(db, monkeypatch):
    """The guest who taps Skip must never have THEIR account commanded — only
    the session host's, regardless of who's calling."""
    session, host = await _seeded_session(db)
    result = await db.execute(select(QueueTrack).where(QueueTrack.session_id == session.id))
    current = next(t for t in result.scalars().all() if t.is_current)

    seen_users = []
    fake = FakeSpotifyAdapter(devices=[{"id": "dev1", "is_active": True}])

    def capture(user):
        seen_users.append(user.id)
        return fake

    monkeypatch.setattr("app.services.queue_optimizer.get_platform_adapter", capture)

    async def broadcast(session_id, message):
        pass

    await _rerank(str(session.id), db, broadcast, skipped_track_id=str(current.id))

    assert seen_users == [session.host_user_id]
    assert any(call[0] == "start_playback" for call in fake.calls)


async def test_rerank_skips_start_playback_when_current_track_unchanged(db, monkeypatch):
    """A rerank that does NOT change is_current (e.g. a guest joining while
    the existing top track's score still wins, or a bare reconnect) must not
    re-issue start_playback — Spotify's PUT /me/player/play has no
    position_ms, so re-issuing it for a track that's already correctly
    playing would audibly restart it from 0 for no reason."""
    session, host = await _seeded_session(db)

    fake = FakeSpotifyAdapter(devices=[{"id": "dev1", "is_active": True}])
    monkeypatch.setattr("app.services.queue_optimizer.get_platform_adapter", lambda user: fake)

    broadcasts = []
    async def broadcast(session_id, message):
        broadcasts.append(message)

    # skipped_track_id=None => skip-protection reinserts the same "current"
    # track from _seeded_session unchanged (no skip happened).
    await _rerank(str(session.id), db, broadcast, skipped_track_id=None)

    result = await db.execute(select(QueueTrack).where(QueueTrack.session_id == session.id))
    current_after = next(t for t in result.scalars().all() if t.is_current)
    assert current_after.track_id == "current"  # unchanged by this rerank

    assert not any(call[0] == "start_playback" for call in fake.calls)
    assert broadcasts[0]["playback_status"] is None


async def test_rerank_calls_start_playback_when_current_track_changes(db, monkeypatch):
    """A skip that promotes a genuinely new track to is_current must still
    re-issue start_playback — the unchanged-track fix above must not regress
    this, the actual mechanism by which a skip reaches the real device."""
    session, host = await _seeded_session(db)
    result = await db.execute(select(QueueTrack).where(QueueTrack.session_id == session.id))
    current = next(t for t in result.scalars().all() if t.is_current)

    fake = FakeSpotifyAdapter(devices=[{"id": "dev1", "is_active": True}])
    monkeypatch.setattr("app.services.queue_optimizer.get_platform_adapter", lambda user: fake)

    broadcasts = []
    async def broadcast(session_id, message):
        broadcasts.append(message)

    await _rerank(str(session.id), db, broadcast, skipped_track_id=str(current.id))

    result = await db.execute(select(QueueTrack).where(QueueTrack.session_id == session.id))
    current_after = next(t for t in result.scalars().all() if t.is_current)
    assert current_after.track_id != "current"  # a new track was promoted

    assert any(call[0] == "start_playback" for call in fake.calls)
    assert broadcasts[0]["playback_status"] == {"status": "playing"}


async def test_rerank_db_update_unaffected_by_spotify_host_resolution_failure(db):
    """Cross-cutting requirement: any failure in the real-playback attempt —
    including a broken/malformed stored token (decrypt failure, not just
    NoPlatformConnectedError) — must never block or corrupt the DB-only
    re-rank that already succeeded, nor suppress the queue_updated broadcast.

    Calls _rerank (db passed explicitly) rather than rerank_queue, which opens
    its own AsyncSessionLocal bound to the real production DB engine, not
    this test's in-memory one — see test_full_session_lifecycle.py's docstring
    for the same constraint on optimize_queue/_build_initial. The seeded
    host's platform_token is the placeholder "tok" (not real encrypted data),
    so get_platform_adapter's decrypt_token call fails for real here — this
    isn't mocked away, it's the actual failure path."""
    session, host = await _seeded_session(db)
    result = await db.execute(select(QueueTrack).where(QueueTrack.session_id == session.id))
    current = next(t for t in result.scalars().all() if t.is_current)

    broadcasts = []
    async def capture_broadcast(session_id, message):
        broadcasts.append(message)

    # Must not raise, despite the real decrypt failure inside adapter resolution.
    await _rerank(str(session.id), db, capture_broadcast, skipped_track_id=str(current.id))

    result = await db.execute(
        select(QueueTrack).where(QueueTrack.session_id == session.id).order_by(QueueTrack.position)
    )
    tracks = list(result.scalars().all())
    assert tracks[0].track_id != "current"  # DB re-rank still happened correctly
    assert tracks[0].is_current is True

    assert len(broadcasts) == 1
    assert broadcasts[0]["queue_build_status"] is not None
    assert broadcasts[0]["playback_status"]["status"] == "error"


async def test_rerank_survives_db_get_failure_during_host_user_lookup(db, monkeypatch):
    """Regression guard: host_user = await db.get(User, ...) must never
    escape _rerank uncaught. It briefly did after Fix 3 relocated the host
    adapter resolution out of the track_id_before-changed block — the
    db.get(User, ...) call ended up sitting before any try/except at all,
    so a failure there would propagate out of _rerank entirely and skip
    broadcast_fn for that skip, violating the exact invariant this
    function's own comments describe ("nothing here may ever prevent the
    queue_updated broadcast from firing"). Distinct from the sibling test
    above, which forces the failure inside get_platform_adapter (decrypt),
    not inside the host_user db.get() lookup itself."""
    session, host = await _seeded_session(db)
    result = await db.execute(select(QueueTrack).where(QueueTrack.session_id == session.id))
    current = next(t for t in result.scalars().all() if t.is_current)

    real_get = db.get

    async def flaky_get(model, ident, *args, **kwargs):
        if model is User:
            raise RuntimeError("DB connection dropped")
        return await real_get(model, ident, *args, **kwargs)

    monkeypatch.setattr(db, "get", flaky_get)

    broadcasts = []
    async def capture_broadcast(session_id, message):
        broadcasts.append(message)

    # Must not raise, despite the failure inside the host_user lookup.
    await _rerank(str(session.id), db, capture_broadcast, skipped_track_id=str(current.id))

    assert len(broadcasts) == 1
    assert broadcasts[0]["queue_build_status"] is not None

    playback_status = broadcasts[0]["playback_status"]
    assert playback_status is not None
    assert playback_status["status"] == "error"


async def test_get_queue_response_includes_host_platform(db):
    """The frontend has no other reliable way to learn host_platform (not in
    route params, not returned to guests at join time, no GET /sessions/{id}
    endpoint) — see QueueResponse."""
    session, host = await _seeded_session(db)

    response = await get_queue(session_id=str(session.id), current_user=host, db=db)
    payload = json.loads(response.body)

    assert payload["host_platform"] == "spotify"
