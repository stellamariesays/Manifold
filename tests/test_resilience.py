"""Tests for manifold.resilience."""

import asyncio
import time

import pytest

from manifold.resilience import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    RetryPolicy,
    TaskResilience,
)


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------

class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker()
        assert cb.state is CircuitState.CLOSED

    def test_allows_when_closed(self):
        assert CircuitBreaker().allow_request() is True

    def test_trips_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state is CircuitState.OPEN
        assert cb.allow_request() is False

    def test_resets_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, reset_timeout=0.0)
        cb.record_failure()
        assert cb.state is CircuitState.OPEN
        # timeout=0 means immediate transition to HALF_OPEN
        assert cb.allow_request() is True
        assert cb.state is CircuitState.HALF_OPEN

    def test_half_open_allows_one_probe(self):
        cb = CircuitBreaker(failure_threshold=1, reset_timeout=0.0)
        cb.record_failure()
        assert cb.allow_request() is True  # probe
        assert cb.allow_request() is False  # second request blocked

    def test_half_open_success_closes(self):
        cb = CircuitBreaker(failure_threshold=1, reset_timeout=0.0)
        cb.record_failure()
        cb.allow_request()  # enter HALF_OPEN
        cb.record_success()
        assert cb.state is CircuitState.CLOSED

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker(failure_threshold=1, reset_timeout=0.0)
        cb.record_failure()
        cb.allow_request()
        cb.record_failure()
        assert cb.state is CircuitState.OPEN


# ---------------------------------------------------------------------------
# RetryPolicy
# ---------------------------------------------------------------------------

class TestRetryPolicy:
    def test_backoff_within_range(self):
        policy = RetryPolicy(backoff_base=1.0, max_backoff=10.0)
        for i in range(5):
            b = policy.backoff(i)
            assert 0 <= b <= min(1.0 * (2 ** i), 10.0)


# ---------------------------------------------------------------------------
# TaskResilience
# ---------------------------------------------------------------------------

class TestTaskResilience:
    @pytest.mark.asyncio
    async def test_success_on_first_try(self):
        tr = TaskResilience()
        result = await tr.execute(lambda: 42)
        assert result == 42

    @pytest.mark.asyncio
    async def test_retries_on_retryable_error(self):
        calls = 0

        async def flaky():
            nonlocal calls
            calls += 1
            if calls < 3:
                raise ValueError("flaky")
            return "ok"

        policy = RetryPolicy(max_retries=3, backoff_base=0.0, retryable_errors=(ValueError,))
        tr = TaskResilience(retry_policy=policy)
        result = await tr.execute(flaky)
        assert result == "ok"
        assert calls == 3

    @pytest.mark.asyncio
    async def test_exhausts_retries_raises(self):
        async def always_fail():
            raise ValueError("nope")

        policy = RetryPolicy(max_retries=2, backoff_base=0.0, retryable_errors=(ValueError,))
        tr = TaskResilience(retry_policy=policy)
        with pytest.raises(ValueError, match="nope"):
            await tr.execute(always_fail)

    @pytest.mark.asyncio
    async def test_non_retryable_raises_immediately(self):
        calls = 0

        async def bad():
            nonlocal calls
            calls += 1
            raise TypeError("bad")

        policy = RetryPolicy(max_retries=3, retryable_errors=(ValueError,))
        tr = TaskResilience(retry_policy=policy)
        with pytest.raises(TypeError):
            await tr.execute(bad)
        assert calls == 1

    @pytest.mark.asyncio
    async def test_circuit_open_rejects(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()
        tr = TaskResilience(circuit_breaker=cb)
        with pytest.raises(CircuitOpenError):
            await tr.execute(lambda: 1)

    @pytest.mark.asyncio
    async def test_sync_callable(self):
        tr = TaskResilience()
        result = await tr.execute(lambda: "sync")
        assert result == "sync"

    @pytest.mark.asyncio
    async def test_exhausted_retries_trips_breaker(self):
        async def always_fail():
            raise ValueError("nope")

        cb = CircuitBreaker(failure_threshold=5)
        policy = RetryPolicy(max_retries=2, backoff_base=0.0, retryable_errors=(ValueError,))
        tr = TaskResilience(retry_policy=policy, circuit_breaker=cb)
        with pytest.raises(ValueError):
            await tr.execute(always_fail)
        assert cb.failure_count == 1
