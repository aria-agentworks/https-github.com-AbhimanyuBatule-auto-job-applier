"""Tests for the AI engine."""

import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestRateLimiter:
    """Test the rate limiter."""

    @pytest.mark.asyncio
    async def test_acquire_within_limit(self):
        """Should acquire immediately when under the limit."""
        from src.ai.engine import RateLimiter
        rl = RateLimiter(max_per_minute=100, max_per_day=1000)
        await rl.acquire()  # Should not raise
        assert rl._day_count == 1

    @pytest.mark.asyncio
    async def test_daily_limit_raises(self):
        """Should raise when daily limit is reached."""
        from src.ai.engine import RateLimiter
        rl = RateLimiter(max_per_minute=100, max_per_day=2)
        await rl.acquire()
        await rl.acquire()
        with pytest.raises(RuntimeError, match="Daily AI rate limit"):
            await rl.acquire()


class TestAIEngineJSONParser:
    """Test the JSON response parser."""

    def _get_engine(self):
        with patch("src.ai.engine.config") as mock_cfg:
            mock_cfg.get = MagicMock(return_value="gemini")
            from src.ai.engine import AIEngine
            return AIEngine()

    def test_parse_clean_json(self):
        """Should parse clean JSON response."""
        engine = self._get_engine()
        result = engine._parse_json_response('{"match_score": 85}')
        assert result["match_score"] == 85

    def test_parse_json_with_markdown(self):
        """Should strip markdown code blocks."""
        engine = self._get_engine()
        result = engine._parse_json_response('```json\n{"match_score": 85}\n```')
        assert result["match_score"] == 85

    def test_parse_json_embedded_in_text(self):
        """Should extract JSON from surrounding text."""
        engine = self._get_engine()
        result = engine._parse_json_response('Here is the result: {"score": 42} Hope this helps!')
        assert result["score"] == 42

    def test_parse_invalid_json(self):
        """Should return error dict for completely invalid JSON."""
        engine = self._get_engine()
        result = engine._parse_json_response("This is not JSON at all")
        assert "error" in result


class TestAIEngineFallback:
    """Test the provider fallback chain."""

    @pytest.mark.asyncio
    async def test_primary_provider_success(self):
        """Should use primary provider when it succeeds."""
        with patch("src.ai.engine.config") as mock_cfg:
            mock_cfg.get = MagicMock(return_value="gemini")
            from src.ai.engine import AIEngine
            engine = AIEngine()
            engine._initialized = True
            engine._provider = "gemini"
            engine._model = MagicMock()

            with patch.object(engine, "_call_with_retry", new_callable=AsyncMock) as mock_retry:
                mock_retry.return_value = '{"result": "ok"}'
                result = await engine._call_ai("test prompt")
                assert result == '{"result": "ok"}'
                # Should only be called once (primary provider succeeds)
                assert mock_retry.call_count == 1

    @pytest.mark.asyncio
    async def test_fallback_on_primary_failure(self):
        """Should try fallback providers when primary fails."""
        with patch("src.ai.engine.config") as mock_cfg:
            mock_cfg.get = MagicMock(return_value="gemini")
            from src.ai.engine import AIEngine
            engine = AIEngine()
            engine._initialized = True
            engine._provider = "gemini"

            call_count = 0

            async def mock_call_with_retry(provider, prompt, system_prompt="", image_path=None):
                nonlocal call_count
                call_count += 1
                if provider == "gemini":
                    raise ConnectionError("Gemini down")
                elif provider == "groq":
                    raise ValueError("Groq not configured")
                elif provider == "ollama":
                    return "ollama response"

            with patch.object(engine, "_call_with_retry", side_effect=mock_call_with_retry):
                result = await engine._call_ai("test")
                assert result == "ollama response"
                assert call_count == 3  # Tried all 3 providers
