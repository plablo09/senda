from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from api.services.feedback_rate_limiter import RateLimitDecision, check_and_update


def _make_redis_mock(total_feedbacks: int = 0, attempts_since_feedback: int = 0):
    mock = AsyncMock()
    mock.hgetall = AsyncMock(
        return_value={
            b"total_feedbacks": str(total_feedbacks).encode(),
            b"attempts_since_feedback": str(attempts_since_feedback).encode(),
        }
    )
    mock.hset = AsyncMock()
    mock.hincrby = AsyncMock()
    mock.expire = AsyncMock()
    return mock


@pytest.mark.asyncio
async def test_first_error_always_gives_feedback():
    """total_feedbacks == 0 → give feedback immediately."""
    redis_mock = _make_redis_mock(total_feedbacks=0)
    with patch("api.services.feedback_rate_limiter._get_redis", return_value=redis_mock):
        decision = await check_and_update("session-1", "ejercicio-1")

    assert decision.should_give_feedback is True
    assert decision.silencio is False
    assert decision.limite is False
    redis_mock.hset.assert_called_once()
    redis_mock.expire.assert_called_once()


@pytest.mark.asyncio
async def test_silence_window_blocks_feedback():
    """After first feedback, attempts within silence_window are silenced (default window=2)."""
    # Simulate: 1 feedback given, 0 attempts since
    redis_mock = _make_redis_mock(total_feedbacks=1, attempts_since_feedback=0)
    with patch("api.services.feedback_rate_limiter._get_redis", return_value=redis_mock):
        decision = await check_and_update("session-1", "ejercicio-1")

    assert decision.should_give_feedback is False
    assert decision.silencio is True
    assert decision.limite is False
    # Key is hashed; verify the field and increment value without asserting on exact key
    from unittest.mock import ANY
    redis_mock.hincrby.assert_called_once_with(ANY, "attempts_since_feedback", 1)


@pytest.mark.asyncio
async def test_feedback_after_silence_window_exhausted():
    """After silence_window attempts (default=2) the next error gets feedback."""
    # Simulate: 1 feedback given, 2 attempts since (window exhausted)
    redis_mock = _make_redis_mock(total_feedbacks=1, attempts_since_feedback=2)
    with patch("api.services.feedback_rate_limiter._get_redis", return_value=redis_mock):
        decision = await check_and_update("session-1", "ejercicio-1")

    assert decision.should_give_feedback is True
    assert decision.silencio is False
    assert decision.limite is False
    redis_mock.hset.assert_called_once()
    redis_mock.expire.assert_called_once()


@pytest.mark.asyncio
async def test_hard_limit_blocks_all_feedback():
    """total_feedbacks >= max_responses (default=3) → return limite."""
    redis_mock = _make_redis_mock(total_feedbacks=3, attempts_since_feedback=5)
    with patch("api.services.feedback_rate_limiter._get_redis", return_value=redis_mock):
        decision = await check_and_update("session-1", "ejercicio-1")

    assert decision.should_give_feedback is False
    assert decision.silencio is True
    assert decision.limite is True
    redis_mock.hset.assert_not_called()
    redis_mock.hincrby.assert_not_called()


@pytest.mark.asyncio
async def test_redis_failure_fails_open():
    """If Redis is unavailable, fail open: give feedback, skip rate limiting."""
    redis_mock = AsyncMock()
    redis_mock.hgetall = AsyncMock(side_effect=ConnectionError("Redis down"))

    with patch("api.services.feedback_rate_limiter._get_redis", return_value=redis_mock):
        decision = await check_and_update("session-1", "ejercicio-1")

    assert decision.should_give_feedback is True
