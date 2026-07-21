"""infer_genres_from_playlist_name — the only genre-like signal available for
YouTube tracks (ytmusicapi exposes no real genre taxonomy at all)."""

from app.services.mood_to_audio_features import (
    GENRE_EXPANSION_MAP,
    infer_genres_from_playlist_name,
)


def test_direct_genre_keyword_match():
    result = infer_genres_from_playlist_name("Hip-Hop Bangers")
    assert set(result) == set(GENRE_EXPANSION_MAP["Hip-Hop"])


def test_genre_expansion_word_match_without_the_literal_genre_name():
    # "trap" is in GENRE_EXPANSION_MAP["Hip-Hop"] but not the genre name itself
    result = infer_genres_from_playlist_name("Trap Nation Mix")
    assert set(GENRE_EXPANSION_MAP["Hip-Hop"]).issubset(set(result))


def test_mood_keyword_match_english():
    result = infer_genres_from_playlist_name("Chill Vibes")
    assert "r&b" in result or "soul" in result or "jazz" in result


def test_mood_keyword_match_hebrew():
    result = infer_genres_from_playlist_name("שירים לאימון בוקר")
    # "אימון" (workout) maps to Energetic hints
    assert set(result) & {"pop", "dance pop", "edm", "hip-hop"}


def test_no_match_returns_empty_list():
    assert infer_genres_from_playlist_name("Liked Songs") == []


def test_empty_name_returns_empty_list():
    assert infer_genres_from_playlist_name("") == []
    assert infer_genres_from_playlist_name(None) == []


def test_result_is_deduped():
    result = infer_genres_from_playlist_name("Pop Party Pop Hits")
    assert len(result) == len(set(result))
