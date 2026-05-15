"""Task retry and circuit breaker — resilient task execution."""

from __future__ import annotations

import asyncio
import enum
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence, Type

logger = logging.getLogger(__name__)


class CircuitState(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Trip after *failure_threshold* failures; reset after *reset_timeout* seconds."""

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: float = 30.0,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.state: CircuitState = CircuitState.CLOSED
        self.failure_count: int = 0
        self.last_failure_time: float = 0.0
        self._half_open_in_flight: bool = False

    def allow_request(self) -> bool:
        if self.state is CircuitState.CLOSED:
            return True
        if self.state is CircuitState.OPEN:
            if time.monotonic() - self.last_failure_time >= self.reset_timeout:
                self.state = CircuitState.HALF_OPEN
                self._half_open_in_flight = False
                # fall through to HALF_OPEN check
            else:
                return False
        # HALF_OPEN: allow exactly one probe
        if not self._half_open_in_flight:
            self._half_open_in_flight = True
            return True
        return False

    def record_success(self) -> None:
        self.failure_count = 0
        self.state = CircuitState.CLOSED
        self._half_open_in_flight = False

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        if self.state is CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            self._half_open_in_flight = False
        elif self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self._half_open_in_flight = False


@dataclass
class RetryPolicy:
    max_retries: int = 3
    backoff_base: float = 1.0
    max_backoff: float = 60.0
    retryable_errors: Sequence[Type[Exception]] = field(
        default_factory=lambda: (Exception,)
    )

    def backoff(self, attempt: int) -> float:
        """Exponential backoff with full jitter."""
        ceiling = min(self.backoff_base * (2 ** attempt), self.max_backoff)
        return random.uniform(0, ceiling)


class CircuitOpenError(Exception):
    """Raised when the circuit breaker rejects a request."""


class TaskResilience:
    """Wraps task execution with retry + circuit breaker logic."""

    def __init__(
        self,
        retry_policy: RetryPolicy | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self.retry_policy = retry_policy or RetryPolicy()
        self.circuit_breaker = circuit_breaker or CircuitBreaker()

    async def execute(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        if not self.circuit_breaker.allow_request():
            raise CircuitOpenError("circuit breaker is open")

        last_exc: Exception | None = None
        for attempt in range(self.retry_policy.max_retries + 1):
            try:
                result = fn(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    result = await result
                self.circuit_breaker.record_success()
                return result
            except BaseException as exc:
                if not isinstance(exc, tuple(self.retry_policy.retryable_errors)):
                    raise
                last_exc = exc
                if attempt < self.retry_policy.max_retries:
                    delay = self.retry_policy.backoff(attempt)
                    logger.debug("attempt %d failed, retrying in %.2fs: %s", attempt + 1, delay, exc)
                    await asyncio.sleep(delay)

        # all retries exhausted
        self.circuit_breaker.record_failure()
        raise last_exc  # type: ignore[misc]
