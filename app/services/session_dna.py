"""Section 1 — Session DNA: build the target vector a JAM session's queue is scored against."""

from app.services.mood_to_audio_features import (
    GENRE_EXPANSION_MAP,
    MOOD_AUDIO_MAP,
    NEUTRAL_MOOD,
    TIME_ENERGY_ADJUSTMENT,
)


def build_session_dna(context_vector: dict) -> dict:
    """
    context_vector: {"genre": str|None, "mood": str|None, "language": str|None, "time": str|None}

    Unmapped mood/genre values (e.g. free-text) fall back to a neutral center /
    literal single-genre match rather than raising — context_vector has no
    server-side enum constraint, so this must never crash session creation.
    """
    genre = context_vector.get("genre")
    mood = context_vector.get("mood")
    language = context_vector.get("language")
    time_of_day = context_vector.get("time")

    mood_features = MOOD_AUDIO_MAP.get(mood, NEUTRAL_MOOD) if mood else NEUTRAL_MOOD
    target_valence = mood_features["valence"]

    time_adjustment = TIME_ENERGY_ADJUSTMENT.get(time_of_day, 0.0) if time_of_day else 0.0
    target_energy = max(0.0, min(1.0, mood_features["energy"] + time_adjustment))

    if genre:
        target_genres = GENRE_EXPANSION_MAP.get(genre, [genre.lower()])
    else:
        target_genres = []

    return {
        "target_valence": target_valence,
        "target_energy": target_energy,
        "target_genres": target_genres,
        "target_language": language,
        "time_of_day": time_of_day,
        # Not in SPEC.md's literal SessionDNA field list, but Section 4's
        # chain_public_playlist_search needs the raw genre/mood words to build
        # search keywords ("{genre} {mood} {language}") — target_genres alone
        # is already-expanded (e.g. ["hip-hop","rap","trap"]), not the original
        # single word. Added so that step is actually implementable. See report.
        "raw_genre": genre,
        "raw_mood": mood,
    }


def load_or_build_session_dna(session) -> dict:
    """Reuse the DNA stored at session-creation time; only build if somehow missing."""
    if session.session_dna:
        return session.session_dna
    return build_session_dna(session.context_vector or {})
