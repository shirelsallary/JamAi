"""[SEC-4] /admin/cache/stats was reachable by anyone, no JWT at all."""

from httpx import AsyncClient


async def test_cache_stats_without_jwt_is_rejected(client: AsyncClient):
    r = await client.get("/admin/cache/stats")
    assert r.status_code == 401


async def test_cache_stats_with_valid_jwt_succeeds(client: AsyncClient, auth_headers: dict):
    r = await client.get("/admin/cache/stats", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert "total_keys" in body
    assert "active_keys" in body
    assert "ttl_breakdown" in body
