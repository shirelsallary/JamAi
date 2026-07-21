"""YouTubeAdapter.get_known_track_ids_for_category — Section 3 personal-library
cross-reference source. get_mood_genre_playlists and get_playlist_tracks are
both tested elsewhere; these tests only cover aggregation, the playlist_limit
cap, caching, and failure handling."""

from uuid import uuid4

import pytest
import ytmusicapi.ytmusic as ytmusic_module

from app.adapters.youtube_adapter import YouTubeAdapter
from app.services.cache_service import cache


def _make_adapter(monkeypatch) -> YouTubeAdapter:
    monkeypatch.setattr(
        ytmusic_module,
        "get_visitor_id",
        lambda _request_func: {"X-Goog-Visitor-Id": "test-visitor-id"},
    )
    return YouTubeAdapter(uuid4(), "SID=abc; HSID=def; __Secure-3PAPISID=xyz123456")


@pytest.fixture(autouse=True)
def _clear_known_track_ids_cache():
    cache.clear_pattern("yt_known_track_ids:")
    yield
    cache.clear_pattern("yt_known_track_ids:")


async def test_aggregates_track_ids_from_only_the_first_playlist_limit_playlists(monkeypatch):
    adapter = _make_adapter(monkeypatch)
    playlists = [{"playlist_id": f"pl{i}", "name": f"pl{i}", "source_genres": ["pop"]} for i in range(3)]
    fetched: list[str] = []

    async def fake_get_mood_genre_playlists(mood, genre):
        return playlists

    async def fake_get_playlist_tracks(playlist_id, limit=100):
        fetched.append(playlist_id)
        return [{"track_id": f"{playlist_id}_t1"}, {"track_id": f"{playlist_id}_t2"}]

    monkeypatch.setattr(adapter, "get_mood_genre_playlists", fake_get_mood_genre_playlists)
    monkeypatch.setattr(adapter, "get_playlist_tracks", fake_get_playlist_tracks)

    result = await adapter.get_known_track_ids_for_category("Energetic", "Pop", playlist_limit=2)

    assert fetched == ["pl0", "pl1"]  # capped — pl2 never fetched
    assert result == {"pl0_t1", "pl0_t2", "pl1_t1", "pl1_t2"}


async def test_result_is_cached_across_calls(monkeypatch):
    adapter = _make_adapter(monkeypatch)
    call_count = 0

    async def fake_get_mood_genre_playlists(mood, genre):
        nonlocal call_count
        call_count += 1
        return [{"playlist_id": "pl0", "name": "pl0", "source_genres": ["pop"]}]

    async def fake_get_playlist_tracks(playlist_id, limit=100):
        return [{"track_id": "t1"}]

    monkeypatch.setattr(adapter, "get_mood_genre_playlists", fake_get_mood_genre_playlists)
    monkeypatch.setattr(adapter, "get_playlist_tracks", fake_get_playlist_tracks)

    first = await adapter.get_known_track_ids_for_category("Energetic", "Pop")
    second = await adapter.get_known_track_ids_for_category("Energetic", "Pop")

    assert first == second == {"t1"}
    assert call_count == 1  # second call served from cache


async def test_returns_empty_set_when_mood_genre_playlists_raises(monkeypatch):
    adapter = _make_adapter(monkeypatch)

    async def raiser(mood, genre):
        raise RuntimeError("ytmusicapi network error")

    monkeypatch.setattr(adapter, "get_mood_genre_playlists", raiser)

    result = await adapter.get_known_track_ids_for_category("Energetic", "Pop")

    assert result == set()


async def test_skips_individual_playlist_track_fetch_failures_without_losing_the_rest(monkeypatch):
    adapter = _make_adapter(monkeypatch)
    playlists = [{"playlist_id": "bad", "name": "bad"}, {"playlist_id": "good", "name": "good"}]

    async def fake_get_mood_genre_playlists(mood, genre):
        return playlists

    async def fake_get_playlist_tracks(playlist_id, limit=100):
        if playlist_id == "bad":
            raise RuntimeError("network error")
        return [{"track_id": "good_t1"}]

    monkeypatch.setattr(adapter, "get_mood_genre_playlists", fake_get_mood_genre_playlists)
    monkeypatch.setattr(adapter, "get_playlist_tracks", fake_get_playlist_tracks)

    result = await adapter.get_known_track_ids_for_category("Energetic", "Pop")

    assert result == {"good_t1"}
