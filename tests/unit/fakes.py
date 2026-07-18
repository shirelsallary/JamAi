"""Fake Spotify/YouTube adapters for the Queue DNA Agent test suite — no real
network calls, mirror the real adapters' method surface closely enough that
queue_dna_engine.py code exercises the same code paths (e.g. FakeYouTubeAdapter
deliberately has no get_audio_features, matching the real YouTubeAdapter, so
the confidence="low" path is genuinely exercised rather than assumed)."""


class FakeSpotifyAdapter:
    def __init__(
        self,
        playlists: dict[str, list[dict]] | None = None,
        audio_features: dict[str, dict] | None = None,
        artist_genres: dict[str, list[str]] | None = None,
        search_results: list[dict] | None = None,
        search_playlists_results: list[dict] | None = None,
        # Playlists reachable ONLY via search_playlists -> get_playlist_tracks
        # (i.e. NOT returned by get_user_playlists) — models a genuine public
        # playlist that isn't one of this user's own saved playlists.
        public_playlist_tracks: dict[str, list[dict]] | None = None,
        # Real playback control (spotify_playback.py) — devices as returned by
        # GET /me/player/devices; empty by default (the common "no active
        # device" case).
        devices: list[dict] | None = None,
        start_playback_raises: Exception | None = None,
    ):
        self.platform = "spotify"
        self._playlists = playlists or {}
        self._public_playlists = public_playlist_tracks or {}
        self._audio_features = audio_features or {}
        self._artist_genres = artist_genres or {}
        self._search_results = search_results or []
        self._search_playlists_results = search_playlists_results or []
        self._devices = devices or []
        self._start_playback_raises = start_playback_raises
        self.calls: list[tuple] = []

    async def get_user_playlists(self, limit: int = 50):
        self.calls.append(("get_user_playlists",))
        return [{"playlist_id": pid, "name": pid} for pid in self._playlists]

    async def get_playlist_tracks(self, playlist_id: str, limit: int = 100):
        self.calls.append(("get_playlist_tracks", playlist_id))
        if playlist_id in self._playlists:
            return self._playlists[playlist_id]
        return self._public_playlists.get(playlist_id, [])

    async def get_audio_features(self, track_ids: list[str]):
        self.calls.append(("get_audio_features", tuple(track_ids)))
        return [self._audio_features[tid] for tid in track_ids if tid in self._audio_features]

    async def get_artists_genres(self, artist_ids: list[str]):
        self.calls.append(("get_artists_genres", tuple(artist_ids)))
        return {aid: self._artist_genres[aid] for aid in artist_ids if aid in self._artist_genres}

    async def search_tracks(self, query: str, limit: int = 3):
        self.calls.append(("search_tracks", query))
        return self._search_results

    async def search_playlists(self, query: str, limit: int = 5):
        self.calls.append(("search_playlists", query))
        return self._search_playlists_results

    async def get_available_devices(self):
        self.calls.append(("get_available_devices",))
        return self._devices

    async def start_playback(self, track_id: str, device_id: str | None = None):
        self.calls.append(("start_playback", track_id, device_id))
        if self._start_playback_raises is not None:
            raise self._start_playback_raises


class FakeYouTubeAdapter:
    """Deliberately has NO get_audio_features (matches the real YouTubeAdapter)."""

    def __init__(
        self,
        playlists: dict[str, list[dict]] | None = None,
        search_results: list[dict] | None = None,
        search_playlists_results: list[dict] | None = None,
    ):
        self.platform = "youtube"
        self._playlists = playlists or {}
        self._search_results = search_results or []
        self._search_playlists_results = search_playlists_results or []
        self.calls: list[tuple] = []

    async def get_user_playlists(self, limit: int = 50):
        self.calls.append(("get_user_playlists",))
        return [{"playlist_id": pid, "name": pid} for pid in self._playlists]

    async def get_playlist_tracks(self, playlist_id: str, limit: int = 100):
        self.calls.append(("get_playlist_tracks", playlist_id))
        return self._playlists.get(playlist_id, [])

    async def get_artists_genres(self, artist_ids: list[str]):
        self.calls.append(("get_artists_genres", tuple(artist_ids)))
        return {}

    async def search_tracks(self, query: str, limit: int = 20):
        self.calls.append(("search_tracks", query))
        return self._search_results

    async def search_playlists(self, query: str, limit: int = 5):
        self.calls.append(("search_playlists", query))
        return self._search_playlists_results


def make_track(track_id, title, artist, duration_ms=200_000, artist_id=None):
    return {
        "track_id": track_id,
        "title": title,
        "artist": artist,
        "duration_ms": duration_ms,
        "artist_id": artist_id,
    }
