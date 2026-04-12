import logging

import pybreaker

from app.config import settings

logger = logging.getLogger(__name__)


class LoggingListener(pybreaker.CircuitBreakerListener):
    def state_change(self, cb, old_state, new_state):
        logger.warning(
            f"Circuit breaker '{cb.name}': {old_state.name} → {new_state.name}"
        )


_PROVIDER_RESET_TIMEOUTS = {
    "anthropic": settings.cb_reset_timeout * 2,  # Sonnet/disease mode can take 55-90s
    "openai": settings.cb_reset_timeout,
}

anthropic_breaker = pybreaker.CircuitBreaker(
    fail_max=settings.cb_fail_max,
    reset_timeout=_PROVIDER_RESET_TIMEOUTS["anthropic"],
    name="anthropic",
    listeners=[LoggingListener()],
)

openai_breaker = pybreaker.CircuitBreaker(
    fail_max=settings.cb_fail_max,
    reset_timeout=_PROVIDER_RESET_TIMEOUTS["openai"],
    name="openai",
    listeners=[LoggingListener()],
)


def get_breaker(provider: str) -> pybreaker.CircuitBreaker:
    if provider == "openai":
        return openai_breaker
    return anthropic_breaker


def is_provider_available(provider: str) -> bool:
    breaker = get_breaker(provider)
    return breaker.current_state != "open"
