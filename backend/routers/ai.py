"""
AI router — risk scoring and Hindi chatbot endpoints.
Thin router: validate input → call AIService → return response.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.dependencies import get_current_agent, get_current_user
from backend.core.redis_client import get_redis
from backend.core.responses import err, ok
from backend.schemas.schemas import ChatRequest, ChatResponse, RiskScoreRequest, RiskScoreResponse
from backend.services.ai_service import AIService

router = APIRouter(prefix="/ai", tags=["AI"])


def _ai_service(db: AsyncSession = Depends(get_db), redis=Depends(get_redis)) -> AIService:
    return AIService(db=db, redis=redis)


@router.post("/score-risk", response_model=dict)
async def score_risk(
    body: RiskScoreRequest,
    agent: dict = Depends(get_current_agent),
    ai: AIService = Depends(_ai_service),
):
    """Score insurance risk for a user profile. Cached 24h for identical inputs."""
    try:
        result = await ai.score_risk(
            user_data=body.model_dump(exclude={"user_id"}),
            agent_id=agent["sub"],
        )
        return ok(result)
    except ValueError as exc:
        return err(str(exc))


@router.post("/chat", response_model=dict)
async def chat(
    body: ChatRequest,
    ai: AIService = Depends(_ai_service),
):
    """
    Stateful Hindi/Hinglish chatbot. Open to authenticated users and agents.
    Session persisted in Redis for 30 minutes.
    """
    try:
        result = await ai.chat_with_user(
            user_id=body.user_id,
            message=body.message,
            language=body.language,
            is_voice=body.is_voice,
        )
        return ok(result)
    except RuntimeError as exc:
        return err(str(exc))


@router.get("/voice-response/{session_id}", response_model=dict)
async def voice_response(
    session_id: str,
    redis=Depends(get_redis),
):
    """Retrieve the latest TTS audio URL for a session (if available)."""
    key = f"voice_response:{session_id}"
    audio_url = await redis.get(key)
    if not audio_url:
        return err("No voice response found for this session")
    return ok({"audio_url": audio_url})
