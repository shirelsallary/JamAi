"""
[SEC-3] End-to-end: a valid JWT alone used to be enough to open
/ws/sessions/{id} for ANY session — any authenticated user who learned or
guessed a session_id could eavesdrop on a JAM they never joined.

Only the REJECTION path is exercised here as a live full-duplex WebSocket
round trip. A live "connects successfully and the connection stays open"
round trip was attempted too, but reliably hung the test process: once
authorized, the handler falls into `while True: await
websocket.receive_text()`, which holds this test's Depends(get_db) session
open against the suite's single shared in-memory aiosqlite connection
(StaticPool) for as long as the socket stays open — and the async `db`
fixture used to set up the test data is *also* still holding that same
connection open for the whole test function's lifetime. Two live sessions
against one physical connection, one of them open-ended, reliably
deadlocked rather than simply serializing. That is a pre-existing
test-harness limitation (any endpoint that holds a long-lived Depends(get_db)
session open across an internal `await` with no timeout would hit the same
thing under this suite's shared-connection setup), not a defect in the
SEC-3 change itself, whose only production-relevant addition is the
`is_session_participant` boolean gate above the pre-existing code path.
That gate is exhaustively covered instead by
tests/unit/test_websocket_session_auth.py, including the exact "host is a
participant of their own session" / "guest who joined is a participant"
cases the success path depends on — proving the gate returns True for a
legitimate participant, which is the only new behavior on that path;
everything after it (debouncer.schedule + the receive loop) is unchanged,
pre-existing code.
"""

from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.models.models import User

_CONTEXT = {"genre": "Pop", "mood": "Happy", "language": None, "time": "Afternoon"}


def _register(client: TestClient, email: str) -> None:
    r = client.post("/auth/register", json={"email": email, "password": "Secure123!"})
    assert r.status_code == 201


def _login(client: TestClient, email: str) -> str:
    r = client.post("/auth/login", json={"email": email, "password": "Secure123!"})
    assert r.status_code == 200
    return r.json()["access_token"]


async def _connect_spotify(db, email: str) -> None:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    user.platform, user.platform_token = "spotify", "fake-encrypted-token"
    await db.commit()


async def test_outsider_with_valid_jwt_is_rejected_from_a_session_they_never_joined(db):
    client = TestClient(app)
    _register(client, "ws_e2e_host@jam.com")
    await _connect_spotify(db, "ws_e2e_host@jam.com")
    host_token = _login(client, "ws_e2e_host@jam.com")

    r = client.post(
        "/sessions",
        json={"context_vector": _CONTEXT, "host_platform": "spotify"},
        headers={"Authorization": f"Bearer {host_token}"},
    )
    assert r.status_code == 201
    session_id = r.json()["id"]

    _register(client, "ws_e2e_outsider@jam.com")
    outsider_token = _login(client, "ws_e2e_outsider@jam.com")

    with client.websocket_connect(f"/ws/sessions/{session_id}?token={outsider_token}") as ws:
        try:
            ws.receive_text()
            raised = False
        except WebSocketDisconnect as exc:
            raised = True
            assert exc.code == 1008
        assert raised, "expected the server to close the connection for a non-participant"
