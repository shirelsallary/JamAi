"""sync_native_queue (spotify_playback.py) — injects the DNA Agent's picks
into Spotify's actual native queue via POST /me/player/queue. Never raises;
a single track's failure never stops the rest. See attempt_spotify_playback
for the sibling function that starts position 0 directly (the Web API has
no "insert at head", only append-to-end, so together these two calls are
the only way to make the DNA Agent's picks actually visible in the queue)."""

from app.models.models import Session
from app.services.spotify_playback import sync_native_queue
from tests.unit.fakes import FakeSpotifyAdapter, make_track


def _spotify_session() -> Session:
    return Session(host_platform="spotify")


async def test_sync_native_queue_adds_all_but_position_zero_in_order():
    fake = FakeSpotifyAdapter()
    queue = [
        make_track("current", "Now Playing", "Artist"),
        make_track("t1", "Track 1", "Artist"),
        make_track("t2", "Track 2", "Artist"),
    ]

    result = await sync_native_queue(fake, _spotify_session(), queue)

    add_calls = [c for c in fake.calls if c[0] == "add_to_queue"]
    assert add_calls == [
        ("add_to_queue", "spotify:track:t1"),
        ("add_to_queue", "spotify:track:t2"),
    ]
    assert result == {"added": 2, "failed": 0}


async def test_sync_native_queue_continues_after_a_single_track_failure():
    fake = FakeSpotifyAdapter(add_to_queue_raises=[Exception("boom"), None])
    queue = [
        make_track("current", "Now Playing", "Artist"),
        make_track("t1", "Track 1", "Artist"),
        make_track("t2", "Track 2", "Artist"),
    ]

    result = await sync_native_queue(fake, _spotify_session(), queue)

    add_calls = [c for c in fake.calls if c[0] == "add_to_queue"]
    # Both calls still happened, in order, despite the first raising.
    assert add_calls == [
        ("add_to_queue", "spotify:track:t1"),
        ("add_to_queue", "spotify:track:t2"),
    ]
    assert result == {"added": 1, "failed": 1}


async def test_sync_native_queue_no_op_when_host_not_on_spotify():
    fake = FakeSpotifyAdapter()
    queue = [
        make_track("current", "Now Playing", "Artist"),
        make_track("t1", "Track 1", "Artist"),
    ]

    result = await sync_native_queue(fake, Session(host_platform="youtube"), queue)

    assert not any(c[0] == "add_to_queue" for c in fake.calls)
    assert result == {"added": 0, "failed": 0}


async def test_sync_native_queue_no_op_when_adapter_is_none():
    queue = [
        make_track("current", "Now Playing", "Artist"),
        make_track("t1", "Track 1", "Artist"),
    ]

    result = await sync_native_queue(None, _spotify_session(), queue)

    assert result == {"added": 0, "failed": 0}
