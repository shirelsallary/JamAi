from datetime import datetime, timezone

from fastapi import APIRouter

from app.services.cache_service import cache

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/cache/stats")
async def cache_stats():
    now = datetime.now(timezone.utc)
    total_keys = len(cache._store)
    active_keys = sum(
        1 for v in cache._store.values() if now <= v["expires_at"]
    )
    breakdown = {
        "audio_features": sum(
            1 for k in cache._store if k.startswith("audio_features")
        ),
        "top_tracks": sum(
            1 for k in cache._store
            if k.startswith("top_tracks") or k.startswith("top_artists")
            or k.startswith("yt_top_tracks")
        ),
        "recommendations": sum(
            1 for k in cache._store
            if k.startswith("recommendations") or k.startswith("yt_recommendations")
        ),
    }
    return {
        "total_keys": total_keys,
        "active_keys": active_keys,
        "ttl_breakdown": breakdown,
    }
