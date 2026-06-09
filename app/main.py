from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="JAM AI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# TODO: include auth_router
# TODO: include sessions_router
# TODO: include queue_router
# TODO: include playlist_router


@app.get("/")
async def health_check():
    return {"status": "ok", "app": "JAM AI"}
