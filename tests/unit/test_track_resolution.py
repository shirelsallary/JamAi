"""Tests 9b, 9c — Section 2.6 cross-platform resolution."""

import logging

from app.services.match_score import CONFIDENCE_HIGH, CONFIDENCE_LOW
from app.services.track_resolution import resolve_track_for_host_platform
from tests.unit.fakes import FakeSpotifyAdapter, make_track


def _youtube_candidate():
    return {
        "track_id": "yt123",
        "platform": "youtube",
        "title": "Blinding Lights",
        "artist": "The Weeknd",
        "duration_ms": 200_000,
        "valence": None,
        "energy": None,
        "genres": [],
        "match_score": 0.7,
        "confidence": CONFIDENCE_LOW,
        "playlist_overlap_count": 0,
        "shared_artist_count": 0,
    }


async def test_cross_platform_track_resolution_success():
    candidate = _youtube_candidate()
    host_adapter = FakeSpotifyAdapter(
        search_results=[make_track("sp999", "Blinding Lights", "The Weeknd")],
        audio_features={"sp999": {"track_id": "sp999", "valence": 0.6, "energy": 0.8}},
    )

    resolved = await resolve_track_for_host_platform(candidate, "spotify", host_adapter)

    assert resolved is not None
    assert resolved["track_id"] == "sp999"
    assert resolved["platform"] == "spotify"
    assert resolved["confidence"] == CONFIDENCE_HIGH
    assert resolved["valence"] == 0.6
    assert resolved["energy"] == 0.8


async def test_cross_platform_track_resolution_failure_excludes_track(caplog):
    candidate = _youtube_candidate()
    host_adapter = FakeSpotifyAdapter(
        search_results=[make_track("sp1", "Completely Different Song", "Someone Else")]
    )

    with caplog.at_level(logging.INFO, logger="app.services.track_resolution"):
        resolved = await resolve_track_for_host_platform(candidate, "spotify", host_adapter)

    assert resolved is None
    assert any("could not be resolved" in r.message for r in caplog.records)


async def test_resolution_skipped_when_already_on_host_platform():
    candidate = {**_youtube_candidate(), "platform": "spotify"}
    host_adapter = FakeSpotifyAdapter()

    resolved = await resolve_track_for_host_platform(candidate, "spotify", host_adapter)

    assert resolved == candidate
    assert host_adapter.calls == []  # no search performed — nothing to resolve
