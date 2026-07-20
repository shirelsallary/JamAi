"""
Real Spotify playback control — checks for an active device and attempts to
start playback of a track, entirely defensively.

Takes an already-resolved adapter rather than resolving one itself: every
caller (queue_optimizer.py's _build_initial/_rerank, routers/queue.py's
/play endpoint) already needs its own get_platform_adapter reference —
that's what existing tests monkeypatch (per-module) to avoid real network/
decrypt calls, and a second independent import here would silently bypass
that. Resolving the SESSION HOST's adapter (never the calling user's — any
participant can trigger a skip, but only the host's Spotify account is ever
commanded) is the caller's responsibility.

`attempt_spotify_playback` never raises — a failure here must never affect
queue state or become an unhandled 500. Every failure mode returns a
specific, distinguishable status so the frontend can show something other
than a generic error.
"""

import logging

from app.adapters.spotify_adapter import NoActiveDeviceError
from app.models.models import Session

logger = logging.getLogger(__name__)


async def attempt_spotify_playback(adapter, session: Session, track_id: str) -> dict:
    """Returns one of:
    - {"status": "playing"}
    - {"status": "no_active_device"} — the expected, common case; not an error
    - {"status": "error", "reason": "<code>"} — anything else

    `adapter` is None when the host has no usable Spotify connection.
    """
    if session.host_platform != "spotify":
        return {"status": "error", "reason": "NOT_SPOTIFY_SESSION"}

    if adapter is None:
        return {"status": "error", "reason": "HOST_NOT_CONNECTED"}

    try:
        devices = await adapter.get_available_devices()
    except Exception:
        logger.exception("get_available_devices failed for session %s", session.id)
        return {"status": "error", "reason": "DEVICE_CHECK_FAILED"}

    active = next((d for d in devices if d.get("is_active")), None)
    if active is None:
        return {"status": "no_active_device"}

    try:
        await adapter.start_playback(track_id, device_id=active.get("id"))
    except Exception:
        logger.exception("start_playback failed for session %s", session.id)
        return {"status": "error", "reason": "PLAYBACK_START_FAILED"}

    return {"status": "playing"}


async def sync_native_queue(adapter, session: Session, queue_tracks: list) -> dict:
    """
    Injects the DNA Agent's picks into Spotify's actual native queue —
    without this, queue_tracks in our own DB is correct but a user looking
    at the Spotify app's own Queue view sees nothing beyond whatever
    attempt_spotify_playback just started. The Web API has no "insert at
    head" — only POST /me/player/queue, which appends to the end — so a
    "head of queue" effect only exists because callers already start
    position 0 directly via start_playback and then call this for the rest.

    queue_tracks: the DB-ordered queue (position 0 = whatever's already
    playing/being started — never re-added here). Accepts either plain
    dicts (`resolved`, keyed by "track_id", as _build_initial already has in
    hand) or QueueTrack ORM rows ordered by position (as queried by _rerank/
    the /play endpoint) — both are just "the same ordered queue" in whatever
    shape the caller already had without an extra DB round-trip.

    Adds tracks strictly in order, one at a time (not concurrently) — Spotify
    appends to its queue in call order, so concurrent calls could arrive out
    of order. Never raises: a single track's failure is logged and skipped,
    never stops the rest, and never propagates out to affect DB state —
    matching attempt_spotify_playback's best-effort contract.

    Returns {"added": <count>, "failed": <count>}.
    """
    if session.host_platform != "spotify":
        return {"added": 0, "failed": 0}

    if adapter is None:
        return {"added": 0, "failed": 0}

    added = 0
    failed = 0
    for track in queue_tracks[1:]:
        track_id = track["track_id"] if isinstance(track, dict) else track.track_id
        try:
            await adapter.add_to_queue(f"spotify:track:{track_id}")
            added += 1
        except NoActiveDeviceError:
            failed += 1
        except Exception:
            logger.exception(
                "add_to_queue failed for track %s in session %s", track_id, session.id
            )
            failed += 1

    return {"added": added, "failed": failed}
