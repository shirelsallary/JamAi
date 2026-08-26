"""
[REL-2] Simple in-memory fixed-window rate limiter, keyed by client IP.

Matches this codebase's existing single-process, in-memory service style
(ConnectionManager, DebounceService, CacheService) rather than adding a new
dependency (e.g. slowapi) for what a few dozen lines already cover.

Known limitation, same class as the rest of this file's neighbors: in-memory
state means limits reset on restart and aren't shared across worker
processes — acceptable for this MVP's single-process deployment, same
tradeoff already accepted for ConnectionManager/DebounceService/CacheService.

Keyed by request.client.host — behind a reverse proxy (e.g. Render) without
trusted X-Forwarded-For handling this may collapse to the proxy's IP for all
callers; out of scope for this fix (no such trusted-proxy config exists yet
to key off instead).
"""

import time
from collections import defaultdict

from fastapi import HTTPException, Request, status


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)

    def _key(self, request: Request) -> str:
        return request.client.host if request.client else "unknown"

    async def __call__(self, request: Request) -> None:
        now = time.monotonic()
        key = self._key(request)
        window_start = now - self.window_seconds
        hits = [t for t in self._hits[key] if t > window_start]
        if len(hits) >= self.max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests, slow down",
            )
        hits.append(now)
        self._hits[key] = hits


# Stricter — auth endpoints are the classic brute-force/credential-stuffing
# target (register spam, login guessing).
auth_rate_limiter = RateLimiter(max_requests=10, window_seconds=60)

# More lenient — legitimate session actions (join, skip, play) during an
# active JAM can be bursty (a group of guests joining within seconds of a QR
# scan, rapid skips).
action_rate_limiter = RateLimiter(max_requests=30, window_seconds=60)
