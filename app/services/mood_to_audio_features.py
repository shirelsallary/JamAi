"""
Constant mappings used by the Queue DNA Agent (session_dna.py) to translate the
Guided Contextual Input screen's raw picks (genre/mood/language/time) into
target audio features.

Values for MOOD_AUDIO_MAP/TIME_ENERGY_ADJUSTMENT/GENRE_EXPANSION_MAP beyond the
handful given directly in SPEC.md were proposed by the implementer and
confirmed with the product owner before implementation (see conversation
history) — they are not sourced from an external music-psychology reference,
just directionally reasonable valence/energy placements.
"""

# genre -> related genre seeds used for genre_overlap matching (Section 2)
GENRE_EXPANSION_MAP: dict[str, list[str]] = {
    "Pop": ["pop", "dance pop", "electropop"],
    "Hip-Hop": ["hip-hop", "rap", "trap"],
    "Rock": ["rock", "alt rock", "indie rock"],
    "Jazz": ["jazz", "smooth jazz", "bebop"],
    "R&B": ["r&b", "soul", "neo soul"],
    "Latin": ["latin", "reggaeton", "latin pop"],
    "Electronic": ["electronic", "edm", "house"],
    "Classical": ["classical", "orchestral", "baroque"],
}

# Our genre/mood picks (Create JAM form) -> the real category titles YouTube
# Music's own "Moods & Genres" taxonomy exposes via ytmusicapi's
# get_mood_categories() (see YouTubeAdapter.get_mood_genre_playlists). Verified
# against a live, unauthenticated get_mood_categories() call on 2026-07-21
# against ytmusicapi 1.12.1 — these are the actual category titles returned,
# not guessed. Titles are matched case-insensitively downstream, so the exact
# case here is cosmetic.
#
# GENRE_TO_YT_CATEGORY maps to YouTube's "Genres" section. Most of our 8 picks
# have a direct or near-exact match; two aren't 1:1 by name:
#   R&B -> "R&B & soul" (YouTube merges R&B and soul into one category)
#   Electronic -> "Dance & electronic" (YouTube has no bare "Electronic" entry)
GENRE_TO_YT_CATEGORY: dict[str, str] = {
    "Pop": "Pop",
    "Hip-Hop": "Hip-hop",
    "Rock": "Rock",
    "Jazz": "Jazz",
    "R&B": "R&B & soul",
    "Latin": "Latin",
    "Electronic": "Dance & electronic",
    "Classical": "Classical",
}

# MOOD_TO_YT_CATEGORY maps to YouTube's "Moods & moments" section. None of
# YouTube's mood titles are literal genres, so tracks sourced via this path
# do NOT get a deterministic genres tag the way GENRE_TO_YT_CATEGORY hits do
# (see get_mood_genre_playlists) — "Energize" isn't a genre any more than
# "Energetic" is, so there's nothing certain to assign.
MOOD_TO_YT_CATEGORY: dict[str, str] = {
    "Energetic": "Energize",
    "Chill": "Chill",
    "Happy": "Feel good",
    "Sad": "Sad",
    "Romantic": "Romance",
    "Focus": "Focus",
}

# mood -> target valence/energy (Section 1)
MOOD_AUDIO_MAP: dict[str, dict[str, float]] = {
    "Energetic": {"valence": 0.8, "energy": 0.85},
    "Chill": {"valence": 0.5, "energy": 0.25},
    "Happy": {"valence": 0.9, "energy": 0.65},
    "Sad": {"valence": 0.15, "energy": 0.30},
    "Romantic": {"valence": 0.6, "energy": 0.35},
    "Focus": {"valence": 0.4, "energy": 0.30},
}

# neutral center used when mood/genre is missing or not in the maps above
NEUTRAL_MOOD = {"valence": 0.5, "energy": 0.5}

# time_of_day -> energy adjustment, added to the mood's base energy (Section 1)
TIME_ENERGY_ADJUSTMENT: dict[str, float] = {
    "Morning": 0.05,
    "Afternoon": 0.0,
    "Evening": -0.05,
    "Night": -0.05,
    "Late Night": -0.15,
}

# app-facing language names <-> langdetect ISO 639-1 codes (used by match_score.py)
LANGDETECT_TO_APP_LANGUAGE: dict[str, str] = {
    "en": "English",
    "he": "Hebrew",
    "es": "Spanish",
    "ar": "Arabic",
    "fr": "French",
}

# mood keyword (English + Hebrew) -> canonical MOOD_AUDIO_MAP key. Used only by
# infer_genres_from_playlist_name below.
_MOOD_KEYWORD_SYNONYMS: dict[str, str] = {
    "energetic": "Energetic", "energy": "Energetic", "party": "Energetic",
    "hype": "Energetic", "workout": "Energetic", "gym": "Energetic",
    "pump up": "Energetic", "מסיבה": "Energetic", "אימון": "Energetic", "אנרגטי": "Energetic",
    "chill": "Chill", "relax": "Chill", "relaxing": "Chill", "calm": "Chill",
    "lofi": "Chill", "lo-fi": "Chill", "רגוע": "Chill", "צ'יל": "Chill",
    "happy": "Happy", "feel good": "Happy", "feelgood": "Happy", "good vibes": "Happy",
    "שמח": "Happy", "שמחים": "Happy",
    "sad": "Sad", "heartbreak": "Sad", "breakup": "Sad", "cry": "Sad",
    "עצוב": "Sad", "עצובים": "Sad",
    "romantic": "Romantic", "romance": "Romantic", "love": "Romantic",
    "date night": "Romantic", "רומנטי": "Romantic", "אהבה": "Romantic",
    "focus": "Focus", "study": "Focus", "studying": "Focus", "concentration": "Focus",
    "deep work": "Focus", "פוקוס": "Focus", "ריכוז": "Focus", "לימודים": "Focus",
}

# mood -> genre-ish tags it loosely correlates with — a rough approximation
# (moods aren't genres) used as a fallback signal only when the playlist name
# doesn't literally mention a genre word. Proposed by the implementer, same
# basis as MOOD_AUDIO_MAP/GENRE_EXPANSION_MAP above — not sourced externally.
_MOOD_GENRE_HINTS: dict[str, list[str]] = {
    "Energetic": ["pop", "dance pop", "edm", "hip-hop"],
    "Chill": ["jazz", "smooth jazz", "r&b", "soul", "acoustic"],
    "Happy": ["pop", "dance pop"],
    "Sad": ["r&b", "soul", "neo soul"],
    "Romantic": ["r&b", "soul", "latin", "latin pop"],
    "Focus": ["classical", "orchestral", "jazz", "smooth jazz"],
}


def infer_genres_from_playlist_name(name: str) -> list[str]:
    """Best-effort genre guess from a playlist's own name.

    YouTube Music exposes no real genre taxonomy at all — YouTubeAdapter's
    get_artists_genres always returns {} — so for YouTube tracks this is the
    only genre-like signal compute_match_score's low-confidence path ever has
    to work with. Deliberately simple case-insensitive substring matching, no
    NLP dependency; this is an approximation, not real metadata (the track's
    confidence stays "low" regardless — see match_score.py).

    Returns a deduped list, possibly empty if nothing matches. Never raises.
    """
    if not name:
        return []
    lowered = name.lower()

    inferred: list[str] = []

    for genre_key, expansion in GENRE_EXPANSION_MAP.items():
        if genre_key.lower() in lowered or any(word in lowered for word in expansion):
            inferred.extend(expansion)

    for keyword, mood_key in _MOOD_KEYWORD_SYNONYMS.items():
        if keyword in lowered:
            inferred.extend(_MOOD_GENRE_HINTS.get(mood_key, []))

    return list(dict.fromkeys(inferred))  # dedupe, preserve first-seen order
