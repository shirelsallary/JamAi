from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, spotify

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
# TODO: include sessions_router
# TODO: include queue_router
# TODO: include playlist_router


@app.get("/")
async def health_check():
    return {"status": "ok", "app": "JAM AI"}
