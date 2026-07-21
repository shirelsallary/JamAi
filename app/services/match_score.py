"""Section 2 — computing a match score for a single track against a SessionDNA."""

import math

from langdetect import DetectorFactory, LangDetectException, detect

from app.services.mood_to_audio_features import LANGDETECT_TO_APP_LANGUAGE

# Deterministic detection — langdetect is otherwise seeded from wall-clock time,
# which would make scores non-reproducible for the same title across runs/tests.
DetectorFactory.seed = 0

# Named weight constants (SPEC.md Section 2) — tune here, nowhere else.
WEIGHT_AUDIO = 0.5
WEIGHT_GENRE = 0.4
LANGUAGE_BONUS = 0.1

# Low-confidence tracks (no valence/energy — always true for YouTube) have no
# real audio signal at all, so there is nothing for a separate "audio_score"
# term to independently measure — the old code filled it with a flat neutral
# 0.5 constant that gave every low-confidence track the same fixed +0.25
# regardless of actual fit (no differentiation between tracks, and it could
# never on its own push a score over THRESHOLD_LADDER's 0.50 floor). Instead,
# fold WEIGHT_AUDIO's weight-mass into the two signals a low-confidence track
# *can* actually provide: genre_overlap (now including playlist-name-inferred
# genres, see infer_genres_from_playlist_name) and the language bonus.
LOW_CONFIDENCE_WEIGHT_GENRE = WEIGHT_AUDIO + WEIGHT_GENRE  # 0.9
LOW_CONFIDENCE_WEIGHT_LANGUAGE = LANGUAGE_BONUS  # 0.1 — unchanged value, own constant for clarity

CONFIDENCE_HIGH = "high"
CONFIDENCE_LOW = "low"


def detect_track_language(title: str) -> str | None:
    """
    Best-effort language detection from the track title alone (per product
    decision — there is no language field on either platform's track object).

    Song titles are short strings, so langdetect is noisy here by nature;
    this is documented as a known-fuzzy signal, not a reliable identifier.
    Returns an app-facing language name (e.g. "English") or None if detection
    fails or the detected language isn't one of the app's 5 supported options.
    """
    if not title or not title.strip():
        return None
    try:
        code = detect(title)
    except LangDetectException:
        return None
    return LANGDETECT_TO_APP_LANGUAGE.get(code)


def compute_match_score(track_features: dict, dna: dict) -> dict:
    """
    track_features: {
        "valence": float|None, "energy": float|None,   # None for YouTube (no audio-features API)
        "genres": list[str],
        "title": str,
    }
    dna: SessionDNA dict (see session_dna.py)

    Returns {"score": float in [0,1], "confidence": "high"|"low"}.
    confidence is "low" whenever audio_score had to be approximated without
    real valence/energy data (YouTube tracks, per SPEC.md Section 2 "Note on YouTube").
    """
    valence = track_features.get("valence")
    energy = track_features.get("energy")

    target_genres = [g.lower() for g in dna.get("target_genres", [])]
    track_genres = [g.lower() for g in track_features.get("genres", [])]
    genre_overlap = (
        len(set(track_genres) & set(target_genres)) / max(1, len(target_genres))
        if target_genres
        else 0.0
    )

    detected_language = detect_track_language(track_features.get("title", ""))
    language_match = bool(
        dna.get("target_language") and detected_language == dna["target_language"]
    )

    if valence is not None and energy is not None:
        audio_distance = math.sqrt(
            (valence - dna["target_valence"]) ** 2 + (energy - dna["target_energy"]) ** 2
        ) / math.sqrt(2)
        audio_score = 1 - audio_distance
        confidence = CONFIDENCE_HIGH
        language_bonus = LANGUAGE_BONUS if language_match else 0.0
        raw_score = (WEIGHT_AUDIO * audio_score) + (WEIGHT_GENRE * genre_overlap) + language_bonus
    else:
        # No audio features available (YouTube) — see the constants' comment
        # above for why WEIGHT_AUDIO's weight is folded into genre_overlap
        # (now populated from playlist-name inference for YouTube, see
        # YouTubeAdapter.get_playlist_tracks) instead of a separate audio_score.
        confidence = CONFIDENCE_LOW
        language_bonus = LOW_CONFIDENCE_WEIGHT_LANGUAGE if language_match else 0.0
        raw_score = (LOW_CONFIDENCE_WEIGHT_GENRE * genre_overlap) + language_bonus

    final_score = min(1.0, max(0.0, raw_score))

    return {"score": round(final_score, 4), "confidence": confidence}
