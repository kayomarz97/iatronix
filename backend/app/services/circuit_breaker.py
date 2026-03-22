import logging

import pybreaker

from app.config import settings

logger = logging.getLogger(__name__)


class LoggingListener(pybreaker.CircuitBreakerListener):
    def state_change(self, cb, old_state, new_state):
        logger.warning(
            f"Circuit breaker '{cb.name}': {old_state.name} → {new_state.name}"
        )


anthropic_breaker = pybreaker.CircuitBreaker(
    fail_max=settings.cb_fail_max,
    reset_timeout=settings.cb_reset_timeout,
    name="anthropic",
    listeners=[LoggingListener()],
)

openrouter_breaker = pybreaker.CircuitBreaker(
    fail_max=settings.cb_fail_max,
    reset_timeout=settings.cb_reset_timeout,
    name="openrouter",
    listeners=[LoggingListener()],
)


def get_breaker(provider: str) -> pybreaker.CircuitBreaker:
    if provider == "anthropic":
        return anthropic_breaker
    return openrouter_breaker


def is_provider_available(provider: str) -> bool:
    breaker = get_breaker(provider)
    return breaker.current_state != "open"
