"""YouTubeAdapter.get_mood_genre_playlists — Section 4 official mood/genre
source (ytmusicapi 1.12.1's get_mood_categories/get_mood_playlists), tried by
chain_public_playlist_search before its existing free-text search_playlists
fallback (see test_queue_dna_engine.py for the chaining tests).

Uses a real YouTubeAdapter/YTMusic instance (auth stubbed exactly like
test_youtube_browser_auth.py) with adapter.yt.get_mood_categories and
adapter.yt._send_request monkeypatched — no real network calls.
"""

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


def _valid_playlist_item(title: str, playlist_id: str, artists: str = "Artist A, Artist B") -> dict:
    """A real (trimmed) musicTwoRowItemRenderer playlist tile, shaped exactly
    like a live get_mood_playlists response item (verified 2026-07-21,
    ytmusicapi 1.12.1) — see YouTubeAdapter._parse_mood_playlists_defensive."""
    return {
        "musicTwoRowItemRenderer": {
            "title": {
                "runs": [
                    {
                        "text": title,
                        "navigationEndpoint": {"browseEndpoint": {"browseId": f"VL{playlist_id}"}},
                    }
                ]
            },
            "subtitle": {"runs": [{"text": artists}]},
            "thumbnailRenderer": {"musicThumbnailRenderer": {"thumbnail": {"thumbnails": []}}},
        }
    }


def _song_tile_missing_navigation_endpoint(title: str) -> dict:
    """A musicTwoRowItemRenderer that HAS the right renderer key but no
    navigationEndpoint under its title run — the real second failure mode
    found live on the "Pop" Genre category page (a top-songs carousel using
    song tiles, not playlist tiles). parse_playlist raises KeyError on this."""
    return {"musicTwoRowItemRenderer": {"title": {"runs": [{"text": title}]}}}


def _broken_song_list_item() -> dict:
    """The real first failure mode found live on "Hip-hop"/"Pop" Genre pages —
    an individual-song carousel item using musicResponsiveListItemRenderer
    instead of musicTwoRowItemRenderer entirely."""
    return {"musicResponsiveListItemRenderer": {"flexColumns": []}}


def _browse_response(*sections_of_items) -> dict:
    return {
        "contents": {
            "singleColumnBrowseResultsRenderer": {
                "tabs": [
                    {
                        "tabRenderer": {
                            "content": {
                                "sectionListRenderer": {
                                    "contents": [
                                        {"musicCarouselShelfRenderer": {"contents": list(items)}}
                                        for items in sections_of_items
                                    ]
                                }
                            }
                        }
                    }
                ]
            }
        }
    }


@pytest.fixture(autouse=True)
def _clear_mood_cache():
    """yt_mood_categories is a fixed, global (non-parameterized) cache key —
    without clearing it, whichever test runs first would poison every test
    after it for the rest of the pytest session."""
    cache.delete("yt_mood_categories")
    yield
    cache.delete("yt_mood_categories")


async def test_combines_genre_and_mood_categories_with_deterministic_genre_tagging(monkeypatch):
    adapter = _make_adapter(monkeypatch)

    monkeypatch.setattr(
        adapter.yt,
        "get_mood_categories",
        lambda: {
            "Genres": [{"title": "Pop", "params": "params-pop-t1"}],
            "Moods & moments": [{"title": "Energize", "params": "params-energize-t1"}],
        },
    )

    responses = {
        "params-pop-t1": _browse_response([_valid_playlist_item("Pop Hits", "popid1")]),
        "params-energize-t1": _browse_response([_valid_playlist_item("Workout Bangers", "energizeid1")]),
    }

    def fake_send_request(endpoint, body):
        return responses[body["params"]]

    monkeypatch.setattr(adapter.yt, "_send_request", fake_send_request)

    results = await adapter.get_mood_genre_playlists(mood="Energetic", genre="Pop")

    by_id = {r["playlist_id"]: r for r in results}
    assert set(by_id) == {"popid1", "energizeid1"}
    # Genre-category hit: deterministic genres from GENRE_EXPANSION_MAP["Pop"].
    assert by_id["popid1"]["source_genres"] == ["pop", "dance pop", "electropop"]
    assert by_id["popid1"]["name"] == "Pop Hits"
    # Mood-category hit: no certain genre to assign.
    assert by_id["energizeid1"]["source_genres"] is None
    assert by_id["energizeid1"]["name"] == "Workout Bangers"


async def test_skips_unparseable_carousel_items_instead_of_dropping_the_whole_category(monkeypatch):
    """The real bug found live: a genre category page (e.g. "Pop") leads with
    a broken top-songs carousel that crashes ytmusicapi's own
    get_mood_playlists with KeyError before it returns ANY playlist — even
    the valid ones in later carousels on the same page. Our own defensive
    parsing must skip only the bad items, not lose the good ones."""
    adapter = _make_adapter(monkeypatch)

    monkeypatch.setattr(
        adapter.yt,
        "get_mood_categories",
        lambda: {"Genres": [{"title": "Pop", "params": "params-pop-t2"}]},
    )

    broken_and_valid = _browse_response(
        [_broken_song_list_item(), _song_tile_missing_navigation_endpoint("Some Song")],
        [_valid_playlist_item("Pop Hotlist", "popid2"), _valid_playlist_item("Pump-Up Pop", "popid3")],
    )
    monkeypatch.setattr(adapter.yt, "_send_request", lambda endpoint, body: broken_and_valid)

    results = await adapter.get_mood_genre_playlists(mood=None, genre="Pop")

    assert {r["playlist_id"] for r in results} == {"popid2", "popid3"}
    assert all(r["source_genres"] == ["pop", "dance pop", "electropop"] for r in results)


async def test_returns_empty_when_category_lookup_raises(monkeypatch):
    adapter = _make_adapter(monkeypatch)

    def raise_error():
        raise RuntimeError("network down")

    monkeypatch.setattr(adapter.yt, "get_mood_categories", raise_error)

    results = await adapter.get_mood_genre_playlists(mood="Chill", genre="Jazz")

    assert results == []


async def test_returns_empty_when_neither_mood_nor_genre_maps_to_a_known_category(monkeypatch):
    adapter = _make_adapter(monkeypatch)
    monkeypatch.setattr(
        adapter.yt,
        "get_mood_categories",
        lambda: {"Genres": [{"title": "Pop", "params": "params-pop-t4"}]},
    )
    # Sentinel to prove _send_request is never even called for unmapped inputs.
    monkeypatch.setattr(
        adapter.yt, "_send_request", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("should not be called"))
    )

    results = await adapter.get_mood_genre_playlists(mood="Nonexistent Mood", genre="Nonexistent Genre")

    assert results == []


async def test_get_mood_categories_result_is_cached_across_calls(monkeypatch):
    adapter = _make_adapter(monkeypatch)
    call_count = 0

    def counting_get_mood_categories():
        nonlocal call_count
        call_count += 1
        return {"Genres": [{"title": "Pop", "params": "params-pop-t5"}]}

    monkeypatch.setattr(adapter.yt, "get_mood_categories", counting_get_mood_categories)
    monkeypatch.setattr(
        adapter.yt, "_send_request", lambda endpoint, body: _browse_response([_valid_playlist_item("Pop Hits", "popid5")])
    )

    await adapter.get_mood_genre_playlists(mood=None, genre="Pop")
    await adapter.get_mood_genre_playlists(mood=None, genre="Pop")

    assert call_count == 1
