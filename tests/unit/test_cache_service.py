from datetime import datetime, timezone, timedelta

from app.services.cache_service import CacheService


def test_set_and_get_returns_value():
    c = CacheService()
    c.set("key1", {"data": 1}, ttl_seconds=60)
    assert c.get("key1") == {"data": 1}


def test_zero_ttl_never_cached():
    c = CacheService()
    c.set("key3", "value", ttl_seconds=0)
    assert c.get("key3") is None


def test_expired_entry_returns_none():
    c = CacheService()
    c.set("key2", "value", ttl_seconds=60)
    # Manually backdate the expiry to simulate an expired entry
    c._store["key2"]["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert c.get("key2") is None
