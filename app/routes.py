from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str


@router.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="healthy", version="1.0.0")


@router.get("/sessions")
async def list_sessions():
    """List active sessions (for debugging)"""
    from app.socket_manager import sessions
    return {
        'sessions': [
            {
                'session_id': sid,
                'players': len(s.players),
                'state': s.state
            } for sid, s in sessions.items()
        ]
    }