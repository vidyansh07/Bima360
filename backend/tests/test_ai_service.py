"""Tests for AIService — risk scoring, chat, document verification."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.ai_service import AIService


@pytest.fixture
def ai_service():
    return AIService()


@pytest.fixture
def sample_user_data():
    return {
        "age": 32,
        "occupation": "farmer",
        "annual_income": 120000,
        "district": "Nashik",
        "state": "Maharashtra",
        "pre_existing_conditions": [],
    }


# ── score_risk ────────────────────────────────────────────────────────────────

class TestScoreRisk:
    async def test_returns_cached_result(self, ai_service, mock_redis, sample_user_data):
        cached = json.dumps({"score": 72, "risk_level": "LOW", "recommended_products": ["P1"], "explanation": "ok"})
        mock_redis.get.return_value = cached.encode()

        result = await ai_service.score_risk(sample_user_data, "agent-001")

        assert result["score"] == 72
        mock_redis.get.assert_called_once()

    async def test_calls_llm_on_cache_miss(self, ai_service, mock_redis, sample_user_data):
        mock_redis.get.return_value = None
        llm_response = {"score": 55, "risk_level": "MEDIUM", "recommended_products": ["P2"], "explanation": "medium risk"}

        with patch.object(ai_service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = (json.dumps(llm_response), "sarvam-m")
            result = await ai_service.score_risk(sample_user_data, "agent-001")

        assert result["risk_level"] == "MEDIUM"
        mock_llm.assert_called_once()

    async def test_rate_limit_enforced(self, ai_service, mock_redis, sample_user_data):
        mock_redis.get.return_value = None
        mock_redis.incr.return_value = 101  # over limit

        with pytest.raises(Exception, match="Rate limit"):
            await ai_service.score_risk(sample_user_data, "agent-rate-limited")

    async def test_result_cached_after_llm(self, ai_service, mock_redis, sample_user_data):
        mock_redis.get.return_value = None
        mock_redis.incr.return_value = 1
        llm_response = {"score": 80, "risk_level": "LOW", "recommended_products": [], "explanation": "low risk"}

        with patch.object(ai_service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = (json.dumps(llm_response), "sarvam-m")
            await ai_service.score_risk(sample_user_data, "agent-001")

        mock_redis.set.assert_called()


# ── chat_with_user ────────────────────────────────────────────────────────────

class TestChatWithUser:
    async def test_chat_returns_message(self, ai_service, mock_redis):
        mock_redis.get.return_value = None  # no session history
        llm_out = json.dumps({
            "message": "नमस्ते! मैं आपकी कैसे मदद कर सकता हूँ?",
            "suggested_action": None,
            "hand_off_to_agent": False,
            "agent_message": None,
        })

        with patch.object(ai_service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = (llm_out, "sarvam-m")
            result = await ai_service.chat_with_user("user-001", "मुझे बीमा चाहिए", "hi", False)

        assert "message" in result
        assert result["hand_off_to_agent"] is False

    async def test_session_history_appended(self, ai_service, mock_redis):
        mock_redis.get.return_value = None
        llm_out = json.dumps({
            "message": "Help text",
            "suggested_action": None,
            "hand_off_to_agent": False,
            "agent_message": None,
        })

        with patch.object(ai_service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = (llm_out, "sarvam-m")
            await ai_service.chat_with_user("user-002", "hello", "en", False)

        mock_redis.set.assert_called()
