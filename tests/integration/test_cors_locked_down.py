"""
[SEC-2] The API has no browser-based client (Flutter/Android native talks to
it directly, sends no Origin header, and is never subject to CORS
enforcement) — approved by the project owner to lock CORS down entirely
rather than guess a domain whitelist. Previously `allow_origins=["*"]` +
`allow_credentials=True` made Starlette's CORSMiddleware reflect back
*any* request's Origin as an allowed, credentialed origin (the middleware's
documented behavior when credentials=True forbids literally sending "*").
"""

from httpx import AsyncClient


async def test_simple_request_from_arbitrary_origin_gets_no_cors_headers(
    client: AsyncClient,
):
    r = await client.get("/", headers={"Origin": "https://evil.example"})
    assert r.status_code == 200  # CORS never blocks the server-side response itself
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


async def test_preflight_from_arbitrary_origin_is_rejected(client: AsyncClient):
    r = await client.options(
        "/auth/login",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.status_code == 400
