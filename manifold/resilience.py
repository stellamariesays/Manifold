"""Task retry and circuit breaker — resilient task execution."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED = "closed"      # normal operation
    OPEN = "open"          # blocking requests
    HALF_OPEN = "half_open"  # allowing one probe


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass


@dataclass
class RetryPolicy:
    max_retries: int = 3
    backoff_base: float = 0.5  # seconds
    max_backoff: float = 30.0
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,)

    def backoff(self, attempt: int) -> float:
        """Exponential backoff with jitter."""
        delay = min(self.backoff_base * (2 ** attempt), self.max_backoff)
        jitter = random.uniform(0, delay * 0.5)
        return delay + jitter


class CircuitBreaker:
    """Trips after N failures, resets after timeout, probes in HALF_OPEN."""

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: float = 60.0,
    ):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: float = 0.0

    def record_success(self) -> None:
        self.success_count += 1
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN

    def allow_request(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            elapsed = time.monotonic() - self.last_failure_time
            if elapsed >= self.reset_timeout:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        # HALF_OPEN — allow one probe
        return True

    def trip(self) -> None:
        """Manually trip the breaker."""
        self.state = CircuitState.OPEN
        self.last_failure_time = time.monotonic()

    def reset(self) -> None:
        """Manually reset the breaker."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0


class TaskResilience:
    """Wraps task execution with retry and circuit breaker."""

    def __init__(
        self,
        retry_policy: RetryPolicy | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ):
        self.retry_policy = retry_policy or RetryPolicy()
        self.circuit = circuit_breaker or CircuitBreaker()

    def execute(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Execute fn with retry and circuit breaker logic."""
        if not self.circuit.allow_request():
            raise CircuitOpenError("Circuit breaker is open")

        last_error: Exception | None = None
        for attempt in range(self.retry_policy.max_retries + 1):
            try:
                result = fn(*args, **kwargs)
                self.circuit.record_success()
                return result
            except self.retry_policy.retryable_exceptions as e:
                last_error = e
                self.circuit.record_failure()
                if not self.circuit.allow_request():
                    raise CircuitOpenError(
                        f"Circuit opened after failure: {e}"
                    ) from e
                if attempt < self.retry_policy.max_retries:
                    delay = self.retry_policy.backoff(attempt)
                    time.sleep(delay)

        raise last_error  # type: ignore
