import asyncio
import re

import httpx
from fastapi import HTTPException


def _parse_retry_after(detail) -> float:
    """Extract wait seconds from a 429 HTTPException detail."""
    if isinstance(detail, str):
        match = re.search(r"(\d+)", detail)
        if match:
            return float(match.group(1))
    elif isinstance(detail, dict):
        return float(detail.get("retry_after", 1))
    return 1.0


async def with_retry(func, max_attempts: int = 3, base_delay: float = 1.0):
    """
    Retry func() up to max_attempts times with exponential backoff.

    Retry schedule (base_delay=1.0):
      attempt 1 → fail → wait 2s
      attempt 2 → fail → wait 4s
      attempt 3 → fail → raise

    Special cases:
      429 HTTPException  → wait Retry-After seconds, then retry
      401 HTTPException  → raise immediately (never retry)
      other 4xx          → raise immediately (client errors are not transient)
      5xx / network err  → retry with exponential backoff
    """
    last_exc: BaseException | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return await func()

        except HTTPException as exc:
            if exc.status_code == 429:
                last_exc = exc
                if attempt < max_attempts:
                    await asyncio.sleep(_parse_retry_after(exc.detail))
                continue
            raise  # 401 or any other 4xx — never retry

        except httpx.HTTPStatusError as exc:
            if exc.response.status_code < 500:
                raise  # 4xx from httpx — client error, not transient
            last_exc = exc
            if attempt < max_attempts:
                await asyncio.sleep(base_delay * (2 ** attempt))

        except Exception as exc:
            # connection errors, timeouts, ytmusicapi failures, etc.
            last_exc = exc
            if attempt < max_attempts:
                await asyncio.sleep(base_delay * (2 ** attempt))

    raise last_exc  # type: ignore[misc]  # always set when we reach here
