from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers import auth, playlist, queue, sessions, spotify

app = FastAPI(title="JAM AI", version="1.0.0")

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
