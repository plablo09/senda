from __future__ import annotations

from dataclasses import dataclass

import redis.asyncio as aioredis

from api.config import settings


@dataclass
class RateLimitDecision:
    should_give_feedback: bool
    silencio: bool = False
    limite: bool = False


async def check_and_update(session_id: str, ejercicio_id: str) -> RateLimitDecision:
    """
    Evaluate the graduated intervention state for (session_id, ejercicio_id).

    Decision logic:
    1. total_feedbacks == 0          → give feedback (first error, always help)
    2. total_feedbacks >= max        → return limite (hard cap reached)
    3. attempts_since_feedback < window → increment attempts, return silencio
    4. attempts_since_feedback >= window → give feedback, reset attempts
    """
    key = f"feedback:{session_id}:{ejercicio_id}"
    redis_client = aioredis.from_url(settings.redis_url)
    try:
        raw = await redis_client.hgetall(key)
        total_feedbacks = int(raw.get(b"total_feedbacks", 0))
        attempts_since_feedback = int(raw.get(b"attempts_since_feedback", 0))

        max_responses = settings.feedback_max_responses
        silence_window = settings.feedback_silence_window

        if total_feedbacks == 0:
            # First error ever — always give feedback
            await redis_client.hset(key, mapping={"total_feedbacks": 1, "attempts_since_feedback": 0})
            return RateLimitDecision(should_give_feedback=True)

        if total_feedbacks >= max_responses:
            return RateLimitDecision(should_give_feedback=False, silencio=True, limite=True)

        if attempts_since_feedback < silence_window:
            await redis_client.hincrby(key, "attempts_since_feedback", 1)
            return RateLimitDecision(should_give_feedback=False, silencio=True)

        # Silence window exhausted — give next feedback
        await redis_client.hset(
            key,
            mapping={
                "total_feedbacks": total_feedbacks + 1,
                "attempts_since_feedback": 0,
            },
        )
        return RateLimitDecision(should_give_feedback=True)

    except Exception:
        # Redis unavailable — fail open: give feedback, skip rate limiting
        return RateLimitDecision(should_give_feedback=True)
    finally:
        await redis_client.aclose()
