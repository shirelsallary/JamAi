"""Test 2 — test_match_score_formula."""

from app.services.match_score import CONFIDENCE_HIGH, CONFIDENCE_LOW, compute_match_score
from app.services.session_dna import build_session_dna

_DNA = build_session_dna({"genre": "Pop", "mood": "Energetic", "language": "English", "time": "Morning"})
# target_valence=0.8, target_energy=0.85+0.05=0.9 (clamped to 1.0), target_genres=["pop","dance pop","electropop"]


def test_identical_track_scores_close_to_one():
    track = {
        "valence": _DNA["target_valence"],
        "energy": _DNA["target_energy"],
        "genres": _DNA["target_genres"],  # full genre_overlap = 1.0
        "title": "xqzplkm",  # gibberish — avoid a langdetect false-positive language_bonus
    }
    result = compute_match_score(track, _DNA)
    assert result["score"] >= 0.9  # 0.5*audio(1.0) + 0.4*genre(1.0)
    assert result["confidence"] == CONFIDENCE_HIGH


def test_fully_opposite_track_scores_close_to_zero():
    track = {
        "valence": 1 - _DNA["target_valence"],
        "energy": 1 - _DNA["target_energy"],
        "genres": ["death metal"],
        "title": "xqzplkm",
    }
    result = compute_match_score(track, _DNA)
    assert result["score"] < 0.2


def test_youtube_track_without_audio_features_gets_low_confidence():
    track = {"valence": None, "energy": None, "genres": ["pop"], "title": "YT Song"}
    result = compute_match_score(track, _DNA)
    assert result["confidence"] == CONFIDENCE_LOW


def test_spotify_track_with_audio_features_gets_high_confidence():
    track = {"valence": 0.5, "energy": 0.5, "genres": [], "title": "Some Song"}
    result = compute_match_score(track, _DNA)
    assert result["confidence"] == CONFIDENCE_HIGH


def test_score_never_exceeds_one_or_drops_below_zero():
    track = {"valence": 0.8, "energy": 0.9, "genres": ["pop", "dance pop", "electropop"], "title": "x"}
    result = compute_match_score(track, _DNA)
    assert 0.0 <= result["score"] <= 1.0
