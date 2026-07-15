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
