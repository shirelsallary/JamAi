import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers import admin, auth, playlist, queue, sessions, spotify
from app.services.time_drift import start_drift_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Time-of-day drift re-ranking (app/services/time_drift.py) — a single
    # background loop for the whole process, matching ConnectionManager's own
    # single-process, in-memory design (see time_drift.py's multi-worker note).
    drift_task = asyncio.create_task(start_drift_scheduler())
    yield
    drift_task.cancel()


app = FastAPI(title="JAM AI", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(spotify.router, prefix="/auth", tags=["spotify"])
app.include_router(sessions.router, tags=["sessions"])
app.include_router(queue.router, tags=["queue"])
app.include_router(playlist.router, tags=["playlist"])
app.include_router(admin.router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail},
        )
    print(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "message": str(exc)},
    )


@app.get("/")
async def health_check():
    return {"status": "ok", "app": "JAM AI"}
