"""Tests for task retry and circuit breaker."""

import time

from manifold.resilience import (
    CircuitBreaker,
    CircuitState,
    CircuitOpenError,
    RetryPolicy,
    TaskResilience,
)


def test_circuit_breaker_closed():
    cb = CircuitBreaker(failure_threshold=3)
    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request()


def test_circuit_breaker_trips():
    cb = CircuitBreaker(failure_threshold=3)
    for _ in range(3):
        cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert not cb.allow_request()


def test_circuit_breaker_half_open():
    cb = CircuitBreaker(failure_threshold=2, reset_timeout=0.01)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    time.sleep(0.02)
    assert cb.allow_request()
    assert cb.state == CircuitState.HALF_OPEN


def test_circuit_breaker_success_resets():
    cb = CircuitBreaker(failure_threshold=2)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


def test_circuit_manual_trip_reset():
    cb = CircuitBreaker()
    cb.trip()
    assert cb.state == CircuitState.OPEN
    cb.reset()
    assert cb.state == CircuitState.CLOSED


def test_retry_policy_backoff():
    rp = RetryPolicy(backoff_base=1.0, max_backoff=10.0)
    b0 = rp.backoff(0)
    b1 = rp.backoff(1)
    b5 = rp.backoff(5)
    assert b0 >= 1.0 and b0 <= 1.5
    assert b1 >= 2.0 and b1 <= 3.0
    assert b5 >= 10.0 and b5 <= 15.0  # capped + jitter


def test_resilience_success():
    r = TaskResilience()
    result = r.execute(lambda: 42)
    assert result == 42


def test_resilience_retry_then_success():
    calls = {"n": 0}
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("not yet")
        return "ok"

    r = TaskResilience(retry_policy=RetryPolicy(max_retries=3, backoff_base=0.01))
    result = r.execute(flaky)
    assert result == "ok"
    assert calls["n"] == 3


def test_resilience_all_retries_fail():
    r = TaskResilience(
        retry_policy=RetryPolicy(max_retries=2, backoff_base=0.01),
        circuit_breaker=CircuitBreaker(failure_threshold=10),
    )
    try:
        r.execute(lambda: (_ for _ in ()).throw(ValueError("nope")))
    except ValueError as e:
        assert str(e) == "nope"


def test_resilience_circuit_open():
    cb = CircuitBreaker(failure_threshold=1)
    cb.trip()
    r = TaskResilience(circuit_breaker=cb)
    try:
        r.execute(lambda: 1)
    except CircuitOpenError:
        pass
    else:
        assert False, "Should have raised CircuitOpenError"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
