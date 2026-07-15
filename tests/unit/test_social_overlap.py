"""Test 9d — social overlap uses the normalized (title, artist) key, not track_id,
so a Spotify copy and a YouTube copy of the same song still count as an overlap."""

from app.services.social_overlap import ScannedPlaylist, compute_social_overlap, normalize_key


def test_social_overlap_uses_normalized_key_across_platforms():
    spotify_playlist = ScannedPlaylist(
        playlist_id="spotify:pl1",
        normalized_track_keys={normalize_key("Song A", "X")},
        normalized_artist_keys={normalize_key("", "X")},
    )
    youtube_playlist = ScannedPlaylist(
        playlist_id="youtube:pl1",
        normalized_track_keys={normalize_key("Song A", "X")},  # same song, different track_id space
        normalized_artist_keys={normalize_key("", "X")},
    )

    track_key = normalize_key("Song A", "X")
    artist_key = normalize_key("", "X")
    overlap, shared = compute_social_overlap(track_key, artist_key, [spotify_playlist, youtube_playlist])

    assert overlap == 2
    assert shared == 2


def test_normalize_key_strips_noise_suffixes():
    a = normalize_key("Song A (feat. Someone)", "X")
    b = normalize_key("Song A", "X")
    assert a == b


def test_normalize_key_case_and_punctuation_insensitive():
    a = normalize_key("Song, A!", "The X")
    b = normalize_key("song a", "the x")
    assert a == b
