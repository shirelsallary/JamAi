"""
Section 2.6 — cross-platform resolution: turning a candidate track discovered
via one participant's platform into something playable on session.host_platform.

Fuzzy matching uses stdlib difflib.SequenceMatcher (no new dependency) — less
robust to word-reordering/typos than a dedicated fuzzy-matching library, but
deterministic and dependency-free.
"""

import difflib
import logging

from app.services.match_score import CONFIDENCE_HIGH
from app.services.social_overlap import normalize_key

logger = logging.getLogger(__name__)

RESOLUTION_MATCH_THRESHOLD = 0.85


def _similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def pick_best_fuzzy_match(
    results: list[dict], candidate_track: dict, threshold: float = RESOLUTION_MATCH_THRESHOLD
) -> dict | None:
    target_key = normalize_key(candidate_track["title"], candidate_track["artist"])

    best_result: dict | None = None
    best_ratio = 0.0
    for result in results:
        result_key = normalize_key(result.get("title", ""), result.get("artist", ""))
        ratio = _similarity(target_key, result_key)
        if ratio > best_ratio:
            best_ratio = ratio
            best_result = result

    if best_result is None or best_ratio < threshold:
        return None
    return best_result


async def resolve_track_for_host_platform(
    candidate_track: dict, host_platform: str, host_adapter
) -> dict | None:
    if candidate_track["platform"] == host_platform:
        return candidate_track

    query = f"{candidate_track['title']} {candidate_track['artist']}"
    results = await host_adapter.search_tracks(query, limit=3)
    best = pick_best_fuzzy_match(results, candidate_track, threshold=RESOLUTION_MATCH_THRESHOLD)

    if best is None:
        logger.info(
            "track '%s' by %s could not be resolved on %s — excluded from queue",
            candidate_track["title"],
            candidate_track["artist"],
            host_platform,
        )
        return None

    resolved = {
        **candidate_track,
        "track_id": best["track_id"],
        "platform": host_platform,
        "title": best.get("title", candidate_track["title"]),
        "artist": best.get("artist", candidate_track["artist"]),
        "duration_ms": best.get("duration_ms", candidate_track["duration_ms"]),
    }

    # Spec: "optionally recompute match_score with the more accurate data" —
    # not implemented here (this function has no access to SessionDNA per the
    # spec's own signature); only the confidence upgrade is applied. See report.
    if host_platform == "spotify" and candidate_track.get("confidence") != CONFIDENCE_HIGH:
        try:
            features = await host_adapter.get_audio_features([best["track_id"]])
            if features:
                resolved["valence"] = features[0].get("valence")
                resolved["energy"] = features[0].get("energy")
                resolved["confidence"] = CONFIDENCE_HIGH
        except Exception:
            logger.exception(
                "audio-feature upgrade failed for resolved track %s", best["track_id"]
            )

    return resolved
