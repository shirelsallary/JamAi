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
