"""
Section 2.5 — social prioritization: playlist overlap and shared artists.

Comparison is deliberately NOT track_id/artist_id based — since Section 0
allows participants to be on different platforms, the same song has two
unrelated ID spaces. Instead we compare on a normalized (title, artist) text
key. This is a fuzzy-text match, not a guaranteed-unique identifier: rare
false positives/negatives are possible (e.g. two different remixes that
happen to share an almost-identical title/artist string collapse into the
same key; a legitimately identical song with wildly different title
formatting on the two platforms may fail to match).
"""

import re
from dataclasses import dataclass, field

_NOISE_SUFFIXES = [
    r"\(feat\.?.*?\)",
    r"\[feat\.?.*?\]",
    r"feat\.?.*$",
    r"\(official video\)",
    r"\(official music video\)",
    r"\(official audio\)",
    r"\(remastered.*?\)",
    r"remastered.*$",
    r"\(live.*?\)",
    r"\(lyrics?.*?\)",
]
_PUNCT_RE = re.compile(r"[^\w\s]")
_WHITESPACE_RE = re.compile(r"\s+")


def strip_noise_suffixes(text: str) -> str:
    for pattern in _NOISE_SUFFIXES:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    text = _PUNCT_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text


def normalize_key(title: str, artist: str) -> str:
    t = strip_noise_suffixes(title.lower().strip())
    a = strip_noise_suffixes(artist.lower().strip())
    return f"{t}::{a}"


@dataclass
class ScannedPlaylist:
    """One playlist scanned from one participant — ephemeral, built during a
    scan and consumed immediately to compute overlap counts. Not persisted;
    only the resulting integer counts are stored (session_candidate_tracks)."""

    playlist_id: str
    normalized_track_keys: set[str] = field(default_factory=set)
    normalized_artist_keys: set[str] = field(default_factory=set)


def compute_social_overlap(
    track_key: str, artist_key: str, all_participants_saved_playlists: list[ScannedPlaylist]
) -> tuple[int, int]:
    playlist_overlap_count = len(
        {
            p.playlist_id
            for p in all_participants_saved_playlists
            if track_key in p.normalized_track_keys
        }
    )
    shared_artist_count = len(
        {
            p.playlist_id
            for p in all_participants_saved_playlists
            if artist_key in p.normalized_artist_keys
        }
    )
    return playlist_overlap_count, shared_artist_count


def social_sort_key(track) -> tuple:
    """Hierarchical sort — overlap first, artist second, match_score last (tie-break only)."""
    return (
        -track["playlist_overlap_count"],
        -track["shared_artist_count"],
        -track["match_score"],
    )
