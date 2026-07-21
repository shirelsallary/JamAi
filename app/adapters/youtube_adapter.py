import asyncio
import json
from functools import partial
from uuid import UUID

from ytmusicapi import YTMusic
from ytmusicapi.navigation import CAROUSEL_CONTENTS, GRID_ITEMS, MTRIR, SECTION_LIST, SINGLE_COLUMN_TAB, nav
from ytmusicapi.parsers.browsing import parse_playlist

from app.services.cache_service import cache, KNOWN_TRACK_IDS_TTL, MOOD_CATEGORIES_TTL, TOP_TRACKS_TTL, RECOMMENDATIONS_TTL
from app.services.mood_to_audio_features import (
    GENRE_EXPANSION_MAP,
    GENRE_TO_YT_CATEGORY,
    MOOD_TO_YT_CATEGORY,
    infer_genres_from_playlist_name,
)
from app.services.retry_handler import with_retry


def _parse_mood_playlists_defensive(response: dict) -> list[dict]:
    """Reimplements ytmusicapi's own YTMusic.get_mood_playlists() body, but
    skips un-parseable carousel items instead of letting the whole call raise.

    Verified live (2026-07-21, ytmusicapi 1.12.1): "Moods & moments" category
    pages (e.g. "Chill", "Energize") parse fine with the library's own
    get_mood_playlists(). "Genres" category pages (e.g. "Pop", "Hip-hop") do
    not — they lead with a "Top songs" carousel whose items aren't playlist
    tiles (musicResponsiveListItemRenderer instead of musicTwoRowItemRenderer,
    or a musicTwoRowItemRenderer song tile with no navigationEndpoint), which
    crashes parse_content_list/parse_playlist with a KeyError before any
    playlist from ANY section is returned — including the real playlist
    carousels further down the same page. Since we need Genres (not just
    Moods) for get_mood_genre_playlists below, skip bad items per-item rather
    than letting one bad carousel discard an entire category's results.
    """
    playlists: list[dict] = []
    for section in nav(response, SINGLE_COLUMN_TAB + SECTION_LIST):
        path: list = []
        if "gridRenderer" in section:
            path = GRID_ITEMS
        elif "musicCarouselShelfRenderer" in section:
            path = CAROUSEL_CONTENTS
        elif "musicImmersiveCarouselShelfRenderer" in section:
            path = ["musicImmersiveCarouselShelfRenderer", "contents"]
        if not path:
            continue
        for item in nav(section, path):
            if MTRIR not in item:
                continue
            try:
                playlists.append(parse_playlist(item[MTRIR]))
            except (KeyError, IndexError, TypeError):
                continue
    return playlists


def _build_browser_auth_json(raw_cookie: str) -> str:
    """Wrap a raw `document.cookie` string into the JSON headers dict
    ytmusicapi's YTMusic() expects for browser-based auth.

    ytmusicapi never needs the browser's own Authorization value: on every
    request it recomputes SAPISIDHASH itself (ytmusicapi.helpers.get_authorization)
    from the __Secure-3PAPISID cookie plus Origin. The "authorization" entry
    here only has to contain the substring "SAPISIDHASH" so
    determine_auth_type() classifies this as AuthType.BROWSER during
    YTMusic.__init__ — its actual value is discarded and replaced before the
    first real request.
    """
    return json.dumps({
        "cookie": raw_cookie,
        "authorization": "SAPISIDHASH_PLACEHOLDER",
        "origin": "https://music.youtube.com",
        "x-goog-authuser": "0",
    })


def _duration_to_ms(duration_str: str | None) -> int:
    """Convert 'mm:ss' or 'hh:mm:ss' string to milliseconds."""
    if not duration_str:
        return 0
    parts = duration_str.split(":")
    try:
        if len(parts) == 2:
            return (int(parts[0]) * 60 + int(parts[1])) * 1000
        if len(parts) == 3:
            return (int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])) * 1000
    except (ValueError, IndexError):
        pass
    return 0


def _run_sync(func, *args, **kwargs):
    """Run a synchronous callable in a thread-pool executor."""
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, partial(func, *args, **kwargs))


class YouTubeAdapter:
    def __init__(self, user_id: UUID, auth_json: str):
        self.user_id = user_id
        self.yt = YTMusic(_build_browser_auth_json(auth_json))

    async def get_user_profile(self) -> dict:
        return {
            "id": str(self.user_id),
            "email": None,
            "display_name": None,
        }

    async def get_top_tracks(self, limit: int = 20) -> list:
        cache_key = f"yt_top_tracks:{self.user_id}:{limit}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        items = await with_retry(lambda: _run_sync(self.yt.get_library_songs, limit=limit))
        result = []
        for item in (items or []):
            artists = item.get("artists") or []
            result.append({
                "track_id": item.get("videoId", ""),
                "title": item.get("title", ""),
                "artist": artists[0]["name"] if artists else "",
                "duration_ms": _duration_to_ms(item.get("duration")),
            })
        cache.set(cache_key, result, TOP_TRACKS_TTL)
        return result

    async def get_top_artists(self, limit: int = 10) -> list:
        items = await with_retry(lambda: _run_sync(self.yt.get_library_artists, limit=limit))
        result = []
        for item in (items or [])[:limit]:
            result.append({
                "artist_id": item.get("browseId", ""),
                "name": item.get("artist", ""),
                "genres": [],
            })
        return result

    # ------------------------------------------------------------------
    # Section 3 / 2.6 — playlist scanning, search-based resolution
    # ------------------------------------------------------------------

    async def get_user_playlists(self, limit: int = 50) -> list:
        """ytmusicapi.get_library_playlists() — the user's own saved playlists."""
        cache_key = f"yt_user_playlists:{self.user_id}:{limit}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        items = await with_retry(lambda: _run_sync(self.yt.get_library_playlists, limit=limit))
        result = [
            {"playlist_id": item.get("playlistId", ""), "name": item.get("title", "")}
            for item in (items or [])
            if item.get("playlistId")
        ]
        cache.set(cache_key, result, TOP_TRACKS_TTL)
        return result

    async def get_playlist_tracks(self, playlist_id: str, limit: int = 100) -> list:
        """ytmusicapi.get_playlist(playlist_id) — the actual saved tracks."""
        cache_key = f"yt_playlist_tracks:{playlist_id}:{limit}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        data = await with_retry(
            lambda: _run_sync(self.yt.get_playlist, playlist_id, limit=limit)
        )
        # Best-effort only (see infer_genres_from_playlist_name) — the closest
        # thing to genre data YouTube tracks ever get, since get_artists_genres
        # below always returns {}.
        inferred_genres = infer_genres_from_playlist_name((data or {}).get("title", ""))
        result = []
        for item in (data or {}).get("tracks", []):
            if not item.get("videoId"):
                continue
            artists = item.get("artists") or []
            result.append({
                "track_id": item["videoId"],
                "title": item.get("title", ""),
                "artist": artists[0]["name"] if artists else "",
                "artist_id": None,  # ytmusicapi doesn't expose stable artist-genre data
                "duration_ms": _duration_to_ms(item.get("duration")),
                "genres": inferred_genres,
            })
        cache.set(cache_key, result, TOP_TRACKS_TTL)
        return result

    async def get_artists_genres(self, artist_ids: list[str]) -> dict[str, list[str]]:
        """No genre taxonomy available via ytmusicapi — always empty (Section 2's
        'no audio features' low-confidence path also covers the empty-genre case)."""
        return {}

    async def search_playlists(self, query: str, limit: int = 5) -> list:
        """ytmusicapi.search(filter='playlists') — Section 4 chain_public_playlist_search."""
        items = await with_retry(
            lambda: _run_sync(self.yt.search, query, filter="playlists", limit=limit)
        )
        return [
            {"playlist_id": item.get("browseId", ""), "name": item.get("title", "")}
            for item in (items or [])
            if item.get("browseId")
        ]

    async def _get_mood_categories_cached(self) -> dict:
        """get_mood_categories() — YouTube's full "Moods & Genres" taxonomy.
        Global (not per-user) cache key: this is public, account-independent
        data, and barely changes, hence the day-long TTL."""
        cache_key = "yt_mood_categories"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        result = await with_retry(lambda: _run_sync(self.yt.get_mood_categories))
        cache.set(cache_key, result or {}, MOOD_CATEGORIES_TTL)
        return result or {}

    async def _get_mood_playlists_cached(self, params: str) -> list[dict]:
        """get_mood_playlists(params) via _parse_mood_playlists_defensive (see
        its docstring for why we don't call ytmusicapi's own get_mood_playlists
        directly). Cached per-category at the same TTL as other playlist
        listings (get_user_playlists/get_playlist_tracks use TOP_TRACKS_TTL)."""
        cache_key = f"yt_mood_playlists:{params}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        response = await with_retry(
            lambda: _run_sync(
                self.yt._send_request,
                "browse",
                {"browseId": "FEmusic_moods_and_genres_category", "params": params},
            )
        )
        result = _parse_mood_playlists_defensive(response or {})
        cache.set(cache_key, result, TOP_TRACKS_TTL)
        return result

    async def get_mood_genre_playlists(self, mood: str | None, genre: str | None) -> list[dict]:
        """
        Section 4 official source — YouTube Music's own "Moods & Genres"
        taxonomy, tried by chain_public_playlist_search before its existing
        free-text search_playlists() fallback (not instead of it).

        Looks up the real YouTube category matching `genre` (GENRE_TO_YT_CATEGORY)
        and, separately, the one matching `mood` (MOOD_TO_YT_CATEGORY), fetching
        playlists from whichever map, deduped by playlist_id. Genre-category
        hits carry a deterministic "source_genres" (GENRE_EXPANSION_MAP's own
        expansion for that genre — the same list session_dna.py uses to build
        target_genres, so it's a guaranteed, not inferred, match). Mood-category
        hits carry source_genres=None — a YouTube mood like "Energize" isn't a
        genre, so there's nothing certain to assign; those tracks keep relying
        on infer_genres_from_playlist_name downstream, same as before this change.

        Returns [] (never raises) if the category lookup fails or neither
        mood nor genre maps to a known YouTube category — chain_public_playlist_search
        falls back to its existing search_playlists() path in that case.
        """
        try:
            categories = await self._get_mood_categories_cached()
        except Exception:
            return []

        title_to_params: dict[str, str] = {}
        for section_items in categories.values():
            for item in section_items:
                title = item.get("title")
                params = item.get("params")
                if title and params:
                    title_to_params[title.lower()] = params

        results: list[dict] = []
        seen_ids: set[str] = set()

        genre_category = GENRE_TO_YT_CATEGORY.get(genre or "")
        params = title_to_params.get(genre_category.lower()) if genre_category else None
        if params:
            try:
                playlists = await self._get_mood_playlists_cached(params)
            except Exception:
                playlists = []
            source_genres = GENRE_EXPANSION_MAP.get(genre, [genre.lower()]) if genre else None
            for pl in playlists:
                pid = pl.get("playlistId")
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    results.append(
                        {"playlist_id": pid, "name": pl.get("title", ""), "source_genres": source_genres}
                    )

        mood_category = MOOD_TO_YT_CATEGORY.get(mood or "")
        params = title_to_params.get(mood_category.lower()) if mood_category else None
        if params:
            try:
                playlists = await self._get_mood_playlists_cached(params)
            except Exception:
                playlists = []
            for pl in playlists:
                pid = pl.get("playlistId")
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    results.append({"playlist_id": pid, "name": pl.get("title", ""), "source_genres": None})

        return results

    async def get_known_track_ids_for_category(
        self, mood: str | None, genre: str | None, playlist_limit: int = 15
    ) -> set[str]:
        """
        Cross-reference source for Section 3's personal-library genre tagging
        (_enrich_with_features_and_genres): a set of videoIds known — with
        certainty — to belong to the genre/mood category get_mood_genre_playlists
        resolves to. If a personal-library track's videoId is in this set, its
        genre is certain (GENRE_EXPANSION_MAP[genre]), not a
        infer_genres_from_playlist_name guess.

        Only scans the first `playlist_limit` of get_mood_genre_playlists'
        results — a category can hold hundreds of playlists (live-verified:
        193 for "Pop", 462 for "Energize"), and scanning all of them with
        get_playlist_tracks every time would be far too expensive. 15 is a
        cost/coverage compromise: ~15 official playlists x ~50-100 tracks
        each already covers a few thousand distinct videoIds per category,
        while keeping the get_playlist_tracks call count bounded (each of
        those calls is itself already cached — TOP_TRACKS_TTL — so repeat
        lookups across categories that happen to share a playlist are free).

        The assembled set itself is cached whole for a day per (mood, genre,
        playlist_limit) — this cost is paid once per calendar day per
        category combination, not once per session/user, since neither
        get_mood_genre_playlists' result nor those playlists' contents
        change meaningfully within a day. Never raises — returns an empty
        set on any failure, same as get_mood_genre_playlists.
        """
        cache_key = f"yt_known_track_ids:{mood or ''}:{genre or ''}:{playlist_limit}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            playlists = await self.get_mood_genre_playlists(mood, genre)
        except Exception:
            return set()

        known_ids: set[str] = set()
        for playlist in playlists[:playlist_limit]:
            pid = playlist.get("playlist_id")
            if not pid:
                continue
            try:
                tracks = await self.get_playlist_tracks(pid)
            except Exception:
                continue
            known_ids.update(t["track_id"] for t in tracks if t.get("track_id"))

        cache.set(cache_key, known_ids, KNOWN_TRACK_IDS_TTL)
        return known_ids

    async def search_tracks(self, query: str, limit: int = 20) -> list:
        items = await with_retry(
            lambda: _run_sync(self.yt.search, query, filter="songs", limit=limit)
        )
        result = []
        for item in (items or []):
            artists = item.get("artists") or []
            result.append({
                "track_id": item.get("videoId", ""),
                "title": item.get("title", ""),
                "artist": artists[0]["name"] if artists else "",
                "duration_ms": _duration_to_ms(item.get("duration")),
            })
        return result

    async def get_recommendations(
        self,
        seed_genres: list[str],
        target_valence: float,
        target_energy: float,
        limit: int = 20,
    ) -> list:
        cache_key = f"yt_recommendations:{','.join(sorted(seed_genres))}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        sections = await with_retry(lambda: _run_sync(self.yt.get_home))
        tracks = []
        for section in (sections or []):
            for item in section.get("contents", []):
                if item.get("videoId"):
                    artists = item.get("artists") or []
                    tracks.append({
                        "track_id": item["videoId"],
                        "title": item.get("title", ""),
                        "artist": artists[0]["name"] if artists else "",
                        "duration_ms": _duration_to_ms(item.get("duration")),
                    })
                if len(tracks) >= limit:
                    break
            if len(tracks) >= limit:
                break
        result = tracks[:limit]
        cache.set(cache_key, result, RECOMMENDATIONS_TTL)
        return result

    async def get_current_playback(self) -> dict | None:
        # YouTube Music API doesn't expose playback state
        return None

    async def create_playlist(self, name: str, track_ids: list[str]) -> str:
        playlist_id = await with_retry(
            lambda: _run_sync(self.yt.create_playlist, name, "")
        )
        if track_ids:
            await with_retry(
                lambda: _run_sync(self.yt.add_playlist_items, playlist_id, track_ids)
            )
        return f"https://music.youtube.com/playlist?list={playlist_id}"

    async def health_check(self) -> bool:
        try:
            await with_retry(lambda: _run_sync(self.yt.get_home))
            return True
        except Exception:
            return False
