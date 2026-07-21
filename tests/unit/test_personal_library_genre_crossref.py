"""_enrich_with_features_and_genres — Section 3 personal-library certain-genre
cross-reference (YouTubeAdapter.get_known_track_ids_for_category), tried
BEFORE the infer_genres_from_playlist_name guess it otherwise falls back to.

Uses FakeYouTubeAdapter directly (no DB/User/get_platform_adapter needed —
_enrich_with_features_and_genres takes an adapter instance, not a user)."""

from app.services.queue_dna_engine import _enrich_with_features_and_genres
from tests.unit.fakes import FakeYouTubeAdapter, make_track


async def test_known_track_id_gets_certain_genre_without_guessing():
    # This track's own "genres" (as YouTubeAdapter.get_playlist_tracks would
    # have pre-attached via infer_genres_from_playlist_name) says "jazz" —
    # if the cross-reference works, the certain "Pop" tag must win instead.
    track = make_track("known1", "Some Song", "Some Artist")
    track["genres"] = ["jazz"]  # would-be guess, must be overridden

    adapter = FakeYouTubeAdapter(known_track_ids_results={"known1"})

    enrichment = await _enrich_with_features_and_genres(adapter, [track], mood="Energetic", genre="Pop")

    assert enrichment["known1"]["genres"] == ["pop", "dance pop", "electropop"]
    assert ("get_known_track_ids_for_category", "Energetic", "Pop", 15) in adapter.calls


async def test_unknown_track_id_falls_back_to_playlist_name_guess_unchanged():
    track = make_track("unknown1", "Some Song", "Some Artist")
    track["genres"] = ["jazz"]  # the only signal available — must survive untouched

    adapter = FakeYouTubeAdapter(known_track_ids_results={"some_other_known_id"})

    enrichment = await _enrich_with_features_and_genres(adapter, [track], mood="Energetic", genre="Pop")

    assert enrichment["unknown1"]["genres"] == ["jazz"]


async def test_no_genre_in_session_skips_cross_reference_entirely():
    """genre=None (session has no genre pick) — nothing certain to assign,
    so get_known_track_ids_for_category shouldn't even be called."""
    track = make_track("t1", "Some Song", "Some Artist")
    track["genres"] = ["jazz"]

    adapter = FakeYouTubeAdapter(known_track_ids_results={"t1"})

    enrichment = await _enrich_with_features_and_genres(adapter, [track], mood="Energetic", genre=None)

    assert enrichment["t1"]["genres"] == ["jazz"]  # unchanged guess
    assert not any(c[0] == "get_known_track_ids_for_category" for c in adapter.calls)


async def test_omitting_mood_and_genre_args_entirely_behaves_exactly_as_before():
    """Callers that don't pass mood/genre at all (defaults) must see zero
    behavior change — same as the no-genre case above, but via the default
    rather than an explicit None."""
    track = make_track("t1", "Some Song", "Some Artist")
    track["genres"] = ["jazz"]

    adapter = FakeYouTubeAdapter(known_track_ids_results={"t1"})

    enrichment = await _enrich_with_features_and_genres(adapter, [track])

    assert enrichment["t1"]["genres"] == ["jazz"]
    assert not any(c[0] == "get_known_track_ids_for_category" for c in adapter.calls)


async def test_cross_reference_lookup_failure_falls_back_to_guess_not_a_crash():
    track = make_track("t1", "Some Song", "Some Artist")
    track["genres"] = ["jazz"]

    adapter = FakeYouTubeAdapter(known_track_ids_raises=RuntimeError("ytmusicapi network error"))

    enrichment = await _enrich_with_features_and_genres(adapter, [track], mood="Energetic", genre="Pop")

    assert enrichment["t1"]["genres"] == ["jazz"]  # survives the failure via the existing guess path


async def test_unmapped_genre_falls_back_to_lowercased_literal_like_get_mood_genre_playlists_does():
    track = make_track("known1", "Some Song", "Some Artist")

    adapter = FakeYouTubeAdapter(known_track_ids_results={"known1"})

    enrichment = await _enrich_with_features_and_genres(
        adapter, [track], mood=None, genre="SomeUnmappedGenre"
    )

    assert enrichment["known1"]["genres"] == ["someunmappedgenre"]
