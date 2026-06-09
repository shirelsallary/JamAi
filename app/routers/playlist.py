from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.routers.auth import get_current_user
from app.schemas.schemas import ExportResponse, PlaylistGenerateRequest, QueueTrackResponse
from app.services.playlist_service import export_session, generate_playlist

router = APIRouter()


@router.post("/playlist/generate")
async def generate(
    body: PlaylistGenerateRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tracks = await generate_playlist(body.session_id, body.duration_minutes, db)
    return {
        "tracks": [QueueTrackResponse.model_validate(t) for t in tracks],
        "total_tracks": len(tracks),
    }


@router.post("/sessions/{session_id}/export", response_model=ExportResponse)
async def export(
    session_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    playlist_url, track_count = await export_session(session_id, current_user, db)
    return ExportResponse(playlist_url=playlist_url, track_count=track_count)
