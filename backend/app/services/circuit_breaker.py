import logging

import pybreaker

from app.config import settings
from app.services.provider_registry import get_registry

logger = logging.getLogger(__name__)


class LoggingListener(pybreaker.CircuitBreakerListener):
    def state_change(self, cb, old_state, new_state):
        logger.warning(
            f"Circuit breaker '{cb.name}': {old_state.name} → {new_state.name}"
        )


def _reset_timeout_for(provider: str) -> float:
    # Anthropic Sonnet/disease mode can take 55-90s — give it a longer reset window.
    return settings.cb_reset_timeout * (2 if provider == "anthropic" else 1)


def _make_breaker(provider: str) -> pybreaker.CircuitBreaker:
    return pybreaker.CircuitBreaker(
        fail_max=settings.cb_fail_max,
        reset_timeout=_reset_timeout_for(provider),
        name=provider,
        listeners=[LoggingListener()],
    )


# One breaker per known provider (registry-driven). Previously cerebras/openrouter
# shared the anthropic breaker; now each provider trips independently.
_BREAKERS: dict[str, pybreaker.CircuitBreaker] = {
    pid: _make_breaker(pid) for pid in get_registry().allowed_providers()
}

# Back-compat module-level aliases (imported directly by api/v1/query.py).
anthropic_breaker = _BREAKERS["anthropic"]
openai_breaker = _BREAKERS["openai"]


def get_breaker(provider: str) -> pybreaker.CircuitBreaker:
    return _BREAKERS.get(provider) or _BREAKERS["anthropic"]


def is_provider_available(provider: str) -> bool:
    return get_breaker(provider).current_state != "open"
