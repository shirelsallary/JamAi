"""Test 1 — test_session_dna_construction."""

import pytest

from app.services.mood_to_audio_features import MOOD_AUDIO_MAP
from app.services.session_dna import build_session_dna


@pytest.mark.parametrize("mood", list(MOOD_AUDIO_MAP.keys()))
def test_session_dna_construction_covers_every_mood(mood):
    dna = build_session_dna({"genre": "Pop", "mood": mood, "language": "English", "time": "Morning"})
    expected = MOOD_AUDIO_MAP[mood]
    assert dna["target_valence"] == expected["valence"]
    # Morning adjustment is +0.05
    assert dna["target_energy"] == pytest.approx(min(1.0, expected["energy"] + 0.05))
    assert dna["target_language"] == "English"
    assert dna["time_of_day"] == "Morning"


@pytest.mark.parametrize(
    "time_of_day,adjustment",
    [("Morning", 0.05), ("Afternoon", 0.0), ("Evening", -0.05), ("Night", -0.05), ("Late Night", -0.15)],
)
def test_session_dna_time_adjustment(time_of_day, adjustment):
    dna = build_session_dna({"genre": "Pop", "mood": "Chill", "language": None, "time": time_of_day})
    base_energy = MOOD_AUDIO_MAP["Chill"]["energy"]
    assert dna["target_energy"] == pytest.approx(max(0.0, min(1.0, base_energy + adjustment)))


def test_session_dna_genre_expansion():
    dna = build_session_dna({"genre": "Hip-Hop", "mood": "Energetic", "language": None, "time": None})
    assert dna["target_genres"] == ["hip-hop", "rap", "trap"]


def test_session_dna_unmapped_mood_falls_back_to_neutral():
    dna = build_session_dna({"genre": "Pop", "mood": "Nostalgic", "language": None, "time": None})
    assert dna["target_valence"] == 0.5
    assert dna["target_energy"] == 0.5


def test_session_dna_unmapped_genre_falls_back_to_literal():
    dna = build_session_dna({"genre": "Reggae", "mood": None, "language": None, "time": None})
    assert dna["target_genres"] == ["reggae"]


def test_session_dna_energy_clamped_to_zero_one():
    dna = build_session_dna({"genre": None, "mood": "Chill", "language": None, "time": "Late Night"})
    assert 0.0 <= dna["target_energy"] <= 1.0
