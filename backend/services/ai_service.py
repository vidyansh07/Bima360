"""
AIService — all AI operations go through this class.
Never call Sarvam AI or Groq directly from routers or other services.

Primary:  Sarvam AI saarika-v2 (OpenAI-compatible endpoint)
Fallback: LLaMA 3.1 via Groq API
TTS:      Sarvam bulbul-v2
Vision:   Sarvam Vision / Groq Llama 3.2 Vision
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import uuid
from pathlib import Path
from typing import Optional

import httpx
from langchain.schema import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.redis_client import bot_session_key, rate_limit_key, risk_cache_key
from backend.models.models import AILog

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
RATE_LIMIT_MAX = 100
RATE_LIMIT_TTL = 3600   # 1 hour
RISK_CACHE_TTL = 86400  # 24 hours
BOT_SESSION_TTL = 1800  # 30 minutes

# Risk tier thresholds
RISK_TIERS = {
    "low": (0.0, 0.35, 1.0),
    "medium": (0.36, 0.65, 1.4),
    "high": (0.66, 1.0, 1.9),
}
BASE_PREMIUM = 200.0  # Rs/month for Rs 1,00,000 sum insured


def _load_prompt(filename: str) -> str:
    path = PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt file missing: {path}")
    return path.read_text(encoding="utf-8")


def _sarvam_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model="saarika-v2",
        openai_api_key=settings.SARVAM_API_KEY,
        base_url="https://api.sarvam.ai/v1",
        temperature=0.2,
        max_tokens=1024,
    )


def _groq_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model="llama-3.1-8b-instant",
        openai_api_key=settings.GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1",
        temperature=0.2,
        max_tokens=1024,
    )


def _strip_code_block(text: str) -> str:
    """Remove markdown ```json ... ``` wrappers from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # Drop first line (```json or ```) and last line if it's ```
        start = 1
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[start:end])
    return text.strip()


class AIService:
    def __init__(self, db: AsyncSession, redis) -> None:
        self.db = db
        self.redis = redis

    # ── Rate limiting ────────────────────────────────────────

    async def _check_rate_limit(self, agent_id: str) -> None:
        """Raise ValueError if agent has exceeded 100 AI calls/hour."""
        key = rate_limit_key(agent_id)
        count = await self.redis.incr(key)
        if count == 1:
            await self.redis.expire(key, RATE_LIMIT_TTL)
        if count > RATE_LIMIT_MAX:
            raise ValueError(
                f"Rate limit exceeded: {RATE_LIMIT_MAX} AI calls/hour. "
                "Ek ghante baad dobara try karein."
            )

    # ── AI logging ───────────────────────────────────────────

    def _queue_ai_log(
        self,
        entity_type: str,
        entity_id: str,
        model_used: str,
        input_summary: str,
        output_summary: str,
        score: Optional[float] = None,
        tokens_used: Optional[int] = None,
    ) -> None:
        """Add to session for batch commit — caller must commit session."""
        log = AILog(
            entity_type=entity_type,
            entity_id=uuid.UUID(entity_id),
            model_used=model_used,
            input_summary=input_summary[:1000],
            output_summary=output_summary[:1000],
            score=score,
            tokens_used=tokens_used,
        )
        self.db.add(log)

    # ── LLM call with fallback ───────────────────────────────

    async def _call_llm(
        self,
        messages: list,
        agent_id: Optional[str] = None,
    ) -> tuple[str, str]:
        """
        Call LLM with Sarvam AI primary, Groq fallback.
        Returns (response_text, model_name_used).
        """
        if agent_id:
            await self._check_rate_limit(agent_id)

        try:
            llm = _sarvam_llm()
            response = await asyncio.to_thread(llm.invoke, messages)
            return response.content, "saarika-v2"
        except Exception as exc:
            logger.warning("Sarvam AI failed (%s), falling back to Groq", exc)

        try:
            llm = _groq_llm()
            response = await asyncio.to_thread(llm.invoke, messages)
            return response.content, "llama-3.1-8b-instant"
        except Exception as exc:
            logger.error("Groq fallback also failed: %s", exc)
            raise RuntimeError("All AI providers unavailable. Please try again.") from exc

    # ── Vision LLM call ──────────────────────────────────────

    async def _call_vision_llm(self, image_b64: str, prompt: str) -> tuple[str, str]:
        """Call a vision-capable model. Primary: Sarvam Vision, fallback: Groq Llama Vision."""
        vision_message = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    {"type": "text", "text": prompt},
                ],
            }
        ]

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    "https://api.sarvam.ai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.SARVAM_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={"model": "saarika-v2", "messages": vision_message, "max_tokens": 1024},
                )
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
                return content, "saarika-v2-vision"
        except Exception as exc:
            logger.warning("Sarvam Vision failed (%s), falling back to Groq Vision", exc)

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.2-11b-vision-preview",
                    "messages": vision_message,
                    "max_tokens": 1024,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return content, "llama-3.2-11b-vision"

    # ── Risk Scoring ─────────────────────────────────────────

    async def score_risk(
        self,
        user_data: dict,
        agent_id: Optional[str] = None,
    ) -> dict:
        """
        Score insurance risk for a user.
        Returns: risk_tier, score, premium_min, premium_max, reasoning (Hindi), factors.
        Identical inputs return cached result (TTL 24h).
        """
        cache_key = risk_cache_key(
            hashlib.sha256(
                json.dumps(user_data, sort_keys=True, default=str).encode()
            ).hexdigest()
        )

        cached = await self.redis.get(cache_key)
        if cached:
            result = json.loads(cached)
            self._queue_ai_log(
                entity_type="policy",
                entity_id=str(uuid.uuid4()),
                model_used="cache_hit",
                input_summary=json.dumps(user_data),
                output_summary=json.dumps(result),
                score=result.get("score"),
            )
            return result

        prompt = _load_prompt("risk_scoring.txt").format(
            age=user_data.get("age", ""),
            occupation=user_data.get("occupation", ""),
            district=user_data.get("district", ""),
            state=user_data.get("state", ""),
            pre_existing_conditions=", ".join(
                user_data.get("pre_existing_conditions", [])
            ) or "none",
        )

        raw, model_used = await self._call_llm(
            [HumanMessage(content=prompt)],
            agent_id=agent_id,
        )
        result = self._parse_risk_response(raw)

        await self.redis.setex(cache_key, RISK_CACHE_TTL, json.dumps(result))

        self._queue_ai_log(
            entity_type="policy",
            entity_id=str(uuid.uuid4()),
            model_used=model_used,
            input_summary=json.dumps(user_data),
            output_summary=json.dumps(result),
            score=result.get("score"),
        )
        return result

    def _parse_risk_response(self, raw: str) -> dict:
        """Parse LLM risk response. Falls back to medium tier on any error."""
        try:
            data = json.loads(_strip_code_block(raw))
            score = float(max(0.0, min(1.0, data.get("score", 0.5))))

            if score <= 0.35:
                tier, multiplier = "low", 1.0
            elif score <= 0.65:
                tier, multiplier = "medium", 1.4
            else:
                tier, multiplier = "high", 1.9

            return {
                "risk_tier": tier,
                "score": round(score, 4),
                "premium_min": round(BASE_PREMIUM * multiplier * 0.9, 2),
                "premium_max": round(BASE_PREMIUM * multiplier * 1.1, 2),
                "reasoning": data.get("reasoning", ""),
                "factors": data.get("factors", []),
            }
        except Exception as exc:
            logger.warning("Risk response parse failed: %s. Defaulting to medium.", exc)
            return {
                "risk_tier": "medium",
                "score": 0.5,
                "premium_min": round(BASE_PREMIUM * 1.4 * 0.9, 2),
                "premium_max": round(BASE_PREMIUM * 1.4 * 1.1, 2),
                "reasoning": "Iska manual review hoga — hamare agent aapko call karenge.",
                "factors": [],
            }

    # ── Hindi Chatbot ────────────────────────────────────────

    async def chat_with_user(
        self,
        user_id: str,
        message: str,
        language: str = "hi",
        is_voice: bool = False,
    ) -> dict:
        """
        Stateful Hindi/Hinglish chatbot.
        Conversation history stored in Redis (last 10 exchanges, TTL 30 min).
        """
        system_prompt = _load_prompt("chatbot_system.txt")
        session_key = bot_session_key(user_id)

        history_raw = await self.redis.get(session_key)
        history: list[dict] = json.loads(history_raw) if history_raw else []

        lc_messages: list = [SystemMessage(content=system_prompt)]
        for turn in history[-10:]:
            if turn["role"] == "user":
                lc_messages.append(HumanMessage(content=turn["content"]))
            else:
                lc_messages.append(AIMessage(content=turn["content"]))
        lc_messages.append(HumanMessage(content=message))

        raw, model_used = await self._call_llm(lc_messages)
        parsed = self._parse_chat_response(raw)

        # Update history (cap at 20 turns = 10 exchanges)
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": parsed["message"]})
        if len(history) > 20:
            history = history[-20:]
        await self.redis.setex(session_key, BOT_SESSION_TTL, json.dumps(history))

        result: dict = {
            "message": parsed["message"],
            "suggested_action": parsed.get("suggested_action"),
            "hand_off_to_agent": parsed.get("hand_off_to_agent", False),
        }
        if parsed.get("hand_off_to_agent") and parsed.get("agent_message"):
            result["agent_message"] = parsed["agent_message"]

        if is_voice and settings.SARVAM_API_KEY:
            audio_url = await self._text_to_speech(parsed["message"], language)
            if audio_url:
                result["audio_url"] = audio_url

        return result

    def _parse_chat_response(self, raw: str) -> dict:
        try:
            return json.loads(_strip_code_block(raw))
        except Exception:
            return {
                "message": raw.strip()[:500],
                "suggested_action": None,
                "hand_off_to_agent": False,
            }

    async def _text_to_speech(self, text: str, language: str = "hi") -> Optional[str]:
        """Call Sarvam bulbul-v2 TTS. Returns base64 audio string or None."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://api.sarvam.ai/text-to-speech",
                    headers={
                        "api-subscription-key": settings.SARVAM_API_KEY,
                        "Content-Type": "application/json",
                    },
                    json={
                        "inputs": [text[:500]],  # Sarvam TTS input limit
                        "target_language_code": "hi-IN" if language == "hi" else "en-IN",
                        "speaker": settings.SARVAM_TTS_MODEL,
                        "model": settings.SARVAM_TTS_MODEL,
                        "enable_preprocessing": True,
                    },
                )
                resp.raise_for_status()
                audios = resp.json().get("audios", [])
                return audios[0] if audios else None
        except Exception as exc:
            logger.warning("Sarvam TTS failed: %s", exc)
            return None

    # ── Document Verification ────────────────────────────────

    async def verify_claim_document(self, s3_key: str, doc_type: str) -> dict:
        """
        Verify a claim document image stored in S3.
        Downloads via presigned URL → sends to vision model → returns verification result.
        confidence < 0.7 → flags for human review, does NOT auto-reject.
        """
        import boto3  # lazy import — S3 operations only in this method

        s3 = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
        )

        presigned_url = await asyncio.to_thread(
            s3.generate_presigned_url,
            "get_object",
            Params={"Bucket": settings.AWS_S3_BUCKET, "Key": s3_key},
            ExpiresIn=300,
        )

        async with httpx.AsyncClient(timeout=60.0) as client:
            file_resp = await client.get(presigned_url)
            file_resp.raise_for_status()
            image_b64 = base64.b64encode(file_resp.content).decode("utf-8")

        prompt = _load_prompt("doc_verification.txt").format(doc_type=doc_type)
        raw, model_used = await self._call_vision_llm(image_b64, prompt)
        result = self._parse_doc_verification_response(raw)

        self._queue_ai_log(
            entity_type="claim",
            entity_id=str(uuid.uuid4()),
            model_used=model_used,
            input_summary=f"s3_key={s3_key}, doc_type={doc_type}",
            output_summary=json.dumps(result),
            score=result.get("confidence"),
        )
        return result

    def _parse_doc_verification_response(self, raw: str) -> dict:
        try:
            data = json.loads(_strip_code_block(raw))
            confidence = float(max(0.0, min(1.0, data.get("confidence", 0.5))))
            return {
                "is_authentic": data.get("is_authentic", confidence >= 0.7),
                "confidence": round(confidence, 4),
                "extracted_fields": data.get("extracted_fields", {}),
                "flags": data.get("flags", []),
                "notes": data.get("notes", ""),
                "needs_human_review": confidence < 0.7,
            }
        except Exception as exc:
            logger.warning("Doc verification parse failed: %s", exc)
            return {
                "is_authentic": False,
                "confidence": 0.0,
                "extracted_fields": {},
                "flags": ["parse_error"],
                "notes": "Automatic parsing failed — manual review required.",
                "needs_human_review": True,
            }
