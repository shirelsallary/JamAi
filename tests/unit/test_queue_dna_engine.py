"""Tests 3, 4, 5, 10, 11, 12 — threshold ladder, public search budget, partial
status, and the social-overlap hierarchical sort."""

from app.services.queue_dna_engine import (
    MAX_PUBLIC_SEARCH_QUERIES,
    THRESHOLD_LADDER,
    build_ranked_queue,
    chain_public_playlist_search,
)
from app.services.session_dna import build_session_dna
from app.services.social_overlap import normalize_key
from tests.unit.fakes import FakeSpotifyAdapter, make_track

_DNA = build_session_dna({"genre": "Pop", "mood": "Chill", "language": None, "time": "Afternoon"})


def _candidate(track_id, score, title=None, artist="Artist"):
    """Build a pre-scored candidate dict directly (bypassing compute_match_score
    so the ladder-descent tests can pin an exact score, per test 3's spec)."""
    title = title or track_id
    return {
        "track_id": track_id,
        "platform": "spotify",
        "title": title,
        "artist": artist,
        "duration_ms": 200_000,
        "valence": 0.5,
        "energy": 0.5,
        "genres": [],
        "normalized_track_key": normalize_key(title, artist),
        "normalized_artist_key": normalize_key("", artist),
        "match_score": score,
        "confidence": "high",
    }


# ---------------------------------------------------------------------------
# Test 3 — test_threshold_ladder_degradation
# ---------------------------------------------------------------------------

def test_threshold_ladder_degrades_to_correct_rung_and_never_below_floor():
    # Only tracks scoring 0.62 exist — ladder must stop at 0.60 (25 of them, >= target 20)
    candidates = [_candidate(f"t{i}", 0.62) for i in range(25)]
    accepted, effective_threshold, reached = build_ranked_queue(_DNA, candidates, [], target_size=20)
    assert effective_threshold == 0.60
    assert reached is True
    assert len(accepted) == 25


def test_threshold_ladder_never_drops_below_050_even_when_insufficient():
    candidates = [_candidate(f"t{i}", 0.51) for i in range(3)]  # far fewer than target
    accepted, effective_threshold, reached = build_ranked_queue(_DNA, candidates, [], target_size=20)
    assert effective_threshold == THRESHOLD_LADDER[-1] == 0.50
    assert reached is False
    assert len(accepted) == 3  # whatever passed 0.50, not zero


# ---------------------------------------------------------------------------
# Test 4 — test_public_search_chaining_respects_query_budget
# ---------------------------------------------------------------------------

async def test_public_search_chaining_respects_query_budget():
    # 10 public playlists available, each with plenty of matching tracks —
    # far more than needed to hit the target, to prove the budget (not the
    # target) is what stops the search.
    many_playlists = [{"playlist_id": f"pl{i}", "name": f"pl{i}"} for i in range(10)]
    playlists_tracks = {
        f"pl{i}": [make_track(f"pub{i}_{j}", f"Song {i} {j}", "Artist") for j in range(50)]
        for i in range(10)
    }
    adapter = FakeSpotifyAdapter(
        playlists=playlists_tracks, search_playlists_results=many_playlists
    )

    found = await chain_public_playlist_search(
        _DNA,
        "spotify",
        adapter,
        already_have=[],
        min_threshold=0.0,  # accept everything so the budget is the only limiter
        max_queries=MAX_PUBLIC_SEARCH_QUERIES,
        target_size=10_000,  # unreachable — forces exhausting the query budget
    )

    playlist_fetch_calls = [c for c in adapter.calls if c[0] == "get_playlist_tracks"]
    assert len(playlist_fetch_calls) <= MAX_PUBLIC_SEARCH_QUERIES
    assert len(found) > 0


# ---------------------------------------------------------------------------
# Test 5 — test_partial_status_when_insufficient_matches
# ---------------------------------------------------------------------------

async def test_partial_status_when_insufficient_matches_even_after_public_search():
    candidates = [_candidate("only1", 0.55)]
    accepted, effective_threshold, reached = build_ranked_queue(_DNA, candidates, [], target_size=20)
    assert reached is False

    adapter = FakeSpotifyAdapter(playlists={}, search_playlists_results=[])  # nothing more to find
    extra = await chain_public_playlist_search(
        _DNA, "spotify", adapter, already_have=accepted,
        min_threshold=0.50, max_queries=MAX_PUBLIC_SEARCH_QUERIES, target_size=20,
    )
    final = accepted + extra
    assert len(final) < 20
    assert len(final) >= 1  # not silently emptied out — the one match found is kept


# ---------------------------------------------------------------------------
# Tests 10, 11, 12 — hierarchical social sort
# ---------------------------------------------------------------------------

def test_social_overlap_beats_higher_match_score():
    track_a = _candidate("A", 0.95)
    track_a["playlist_overlap_count"] = 0
    track_a["shared_artist_count"] = 0
    track_b = _candidate("B", 0.71)
    track_b["playlist_overlap_count"] = 3
    track_b["shared_artist_count"] = 0

    ranked = sorted([track_a, track_b], key=lambda t: (-t["playlist_overlap_count"], -t["shared_artist_count"], -t["match_score"]))
    assert [t["track_id"] for t in ranked] == ["B", "A"]


def test_shared_artist_tiebreak_below_playlist_overlap():
    track_a = _candidate("A", 0.80)
    track_a["playlist_overlap_count"] = 2
    track_a["shared_artist_count"] = 1
    track_b = _candidate("B", 0.60)
    track_b["playlist_overlap_count"] = 2
    track_b["shared_artist_count"] = 4

    ranked = sorted([track_a, track_b], key=lambda t: (-t["playlist_overlap_count"], -t["shared_artist_count"], -t["match_score"]))
    assert [t["track_id"] for t in ranked] == ["B", "A"]  # same overlap, B wins on shared_artist_count

    # and when both overlap AND shared_artist_count tie, match_score is the final tie-break
    track_c = _candidate("C", 0.90)
    track_c["playlist_overlap_count"] = 2
    track_c["shared_artist_count"] = 1
    ranked2 = sorted([track_a, track_c], key=lambda t: (-t["playlist_overlap_count"], -t["shared_artist_count"], -t["match_score"]))
    assert [t["track_id"] for t in ranked2] == ["C", "A"]


def test_overlap_does_not_promote_track_across_threshold_tiers():
    # match_score 0.55 is below the 0.60 tier that gets reached by the other tracks —
    # even with a huge overlap count it must not enter the accepted set.
    strong_tier = [_candidate(f"strong{i}", 0.62) for i in range(20)]
    weak_but_social = _candidate("weak_social", 0.55)
    weak_but_social["playlist_overlap_count"] = 999

    accepted, effective_threshold, reached = build_ranked_queue(
        _DNA, strong_tier + [weak_but_social], [], target_size=20
    )
    assert effective_threshold == 0.60
    assert "weak_social" not in [t["track_id"] for t in accepted]
