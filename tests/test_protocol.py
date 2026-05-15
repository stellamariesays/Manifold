"""Tests for task execution protocol — validates TS/Python JSON compatibility."""

import json
import sys
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from manifold.protocol import (
    TaskRequest, TaskResult, TaskStatus, ErrorCode,
    TaskRequestMessage, TaskResultMessage, parse_message,
)


def test_task_request_roundtrip():
    """TaskRequest → dict → TaskRequest preserves all fields."""
    req = TaskRequest(
        target="cron-monitor@hog",
        command="watch",
        args={"verbose": True},
        timeout_ms=60000,
        origin="hog",
        caller="eddie@hog",
    )
    d = req.to_dict()
    req2 = TaskRequest.from_dict(d)
    assert req2.target == "cron-monitor@hog"
    assert req2.command == "watch"
    assert req2.args == {"verbose": True}
    assert req2.timeout_ms == 60000
    assert req2.id == req.id
    print("✅ TaskRequest roundtrip")


def test_task_result_roundtrip():
    """TaskResult → dict → TaskResult preserves all fields."""
    result = TaskResult(
        id="test-123",
        status=TaskStatus.SUCCESS,
        output={"total": 17, "issues": 0},
        executed_by="cron-monitor@hog",
        execution_ms=234,
    )
    d = result.to_dict()
    assert d["status"] == "success"  # serialized as string
    result2 = TaskResult.from_dict(d)
    assert result2.status == TaskStatus.SUCCESS
    assert result2.ok is True
    assert result2.output["total"] == 17
    print("✅ TaskResult roundtrip")


def test_error_result():
    """TaskResult with error status."""
    result = TaskResult(
        id="test-456",
        status=TaskStatus.TIMEOUT,
        error="Agent did not respond within 30000ms",
    )
    d = result.to_dict()
    assert d["status"] == "timeout"
    result2 = TaskResult.from_dict(d)
    assert result2.ok is False
    assert result2.status == TaskStatus.TIMEOUT
    print("✅ TaskResult error roundtrip")


def test_wire_message():
    """TaskRequestMessage serializes to correct wire format."""
    req = TaskRequest(
        target="data-detect@hog",
        command="scan",
        origin="hog",
        caller="eddie@hog",
    )
    msg = TaskRequestMessage(task=req)
    d = msg.to_dict()
    assert d["type"] == "task_request"
    assert d["task"]["target"] == "data-detect@hog"
    assert d["task"]["command"] == "scan"

    # Parse back
    msg2 = parse_message(d)
    assert isinstance(msg2, TaskRequestMessage)
    assert msg2.task.target == "data-detect@hog"
    print("✅ Wire message roundtrip")


def test_json_typescript_compatible():
    """
    Verify the JSON output matches what TypeScript expects.
    TS types: { id: string, target: string, command: string, ... }
    """
    req = TaskRequest(
        target="cron-monitor@hog",
        command="watch",
        origin="hog",
        caller="eddie@hog",
    )
    d = req.to_dict()

    # Required fields that TS expects
    required = ["id", "target", "command", "origin", "caller", "created_at", "timeout_ms"]
    for field in required:
        assert field in d, f"Missing field: {field}"

    # No None values for required fields
    assert d["id"] is not None
    assert d["target"] != ""
    assert d["command"] != ""
    assert d["origin"] != ""
    assert d["caller"] != ""

    # JSON serializable
    json_str = json.dumps(d)
    parsed = json.loads(json_str)
    assert parsed == d
    print("✅ JSON TypeScript compatible")


def test_error_codes_enum():
    """All defined error codes have string values."""
    assert ErrorCode.TIMEOUT.value == "timeout"
    assert ErrorCode.CAPABILITY_NOT_FOUND.value == "capability-not-found"
    assert ErrorCode.TRUST_THRESHOLD_NOT_MET.value == "trust-threshold-not-met"
    assert ErrorCode.STAKE_FORFEITED.value == "stake-forfeited"
    assert ErrorCode.AGENT_UNREACHABLE.value == "agent-unreachable"
    assert ErrorCode.RATE_LIMITED.value == "rate-limited"
    assert ErrorCode.INTERNAL_ERROR.value == "internal-error"
    assert ErrorCode.INVALID_REQUEST.value == "invalid-request"
    assert ErrorCode.CAPACITY_EXCEEDED.value == "capacity-exceeded"
    print("✅ ErrorCode enum values")


def test_error_code_from_status():
    """ErrorCode.from_status maps TaskStatus to default ErrorCode."""
    assert ErrorCode.from_status(TaskStatus.TIMEOUT) == ErrorCode.TIMEOUT
    assert ErrorCode.from_status(TaskStatus.NOT_FOUND) == ErrorCode.CAPABILITY_NOT_FOUND
    assert ErrorCode.from_status(TaskStatus.REJECTED) == ErrorCode.TRUST_THRESHOLD_NOT_MET
    assert ErrorCode.from_status(TaskStatus.SUCCESS) is None
    print("✅ ErrorCode.from_status mapping")


def test_task_result_with_error_code():
    """TaskResult with error_code roundtrips correctly."""
    result = TaskResult(
        id="err-001",
        status=TaskStatus.TIMEOUT,
        error="Agent did not respond within 30000ms",
        error_code=ErrorCode.TIMEOUT,
    )
    d = result.to_dict()
    assert d["error_code"] == "timeout"
    result2 = TaskResult.from_dict(d)
    assert result2.error_code == ErrorCode.TIMEOUT
    assert result2.ok is False
    print("✅ TaskResult error_code roundtrip")


def test_task_result_no_error_code():
    """TaskResult without error_code serializes to None."""
    result = TaskResult(id="ok-001", status=TaskStatus.SUCCESS, output={"done": True})
    d = result.to_dict()
    assert d["error_code"] is None
    result2 = TaskResult.from_dict(d)
    assert result2.error_code is None
    print("✅ TaskResult no error_code roundtrip")


def test_error_code_all_statuses():
    """Each error code can be used with a matching TaskStatus."""
    cases = [
        (TaskStatus.TIMEOUT, ErrorCode.TIMEOUT),
        (TaskStatus.ERROR, ErrorCode.INTERNAL_ERROR),
        (TaskStatus.NOT_FOUND, ErrorCode.CAPABILITY_NOT_FOUND),
        (TaskStatus.REJECTED, ErrorCode.RATE_LIMITED),
    ]
    for status, code in cases:
        result = TaskResult(id="x", status=status, error_code=code)
        d = result.to_dict()
        r2 = TaskResult.from_dict(d)
        assert r2.error_code == code
    print("✅ Error codes with various statuses")


def test_parse_message():
    """parse_message handles all types."""
    req_msg = {"type": "task_request", "task": {"target": "x@y", "command": "test"}}
    parsed = parse_message(req_msg)
    assert isinstance(parsed, TaskRequestMessage)

    res_msg = {"type": "task_result", "result": {"id": "123", "status": "success"}}
    parsed = parse_message(res_msg)
    assert isinstance(parsed, TaskResultMessage)

    unknown = {"type": "unknown", "data": "whatever"}
    parsed = parse_message(unknown)
    assert isinstance(parsed, dict)
    print("✅ parse_message")


if __name__ == "__main__":
    test_task_request_roundtrip()
    test_task_result_roundtrip()
    test_error_result()
    test_wire_message()
    test_json_typescript_compatible()
    test_error_codes_enum()
    test_error_code_from_status()
    test_task_result_with_error_code()
    test_task_result_no_error_code()
    test_error_code_all_statuses()
    test_parse_message()
    print("\n🟢 All protocol tests passed")


# ── Multi-turn threading tests ─────────────────────────────────────────────────

def test_task_request_with_thread():
    """TaskRequest with thread_id and in_reply_to serializes/deserializes correctly."""
    from manifold.protocol import TaskRequest
    req = TaskRequest(
        target="agent@hub",
        command="followup",
        thread_id="thread-abc",
        in_reply_to="task-123",
    )
    d = req.to_dict()
    assert d["thread_id"] == "thread-abc"
    assert d["in_reply_to"] == "task-123"
    req2 = TaskRequest.from_dict(d)
    assert req2.thread_id == "thread-abc"
    assert req2.in_reply_to == "task-123"
    print("✅ TaskRequest threading fields")


def test_task_request_without_thread():
    """TaskRequest without threading fields defaults to None."""
    from manifold.protocol import TaskRequest
    req = TaskRequest(target="agent@hub", command="ping")
    assert req.thread_id is None
    assert req.in_reply_to is None
    print("✅ TaskRequest no-thread defaults")


def test_task_result_with_thread():
    """TaskResult echoes thread_id from request."""
    from manifold.protocol import TaskResult
    res = TaskResult(id="task-456", thread_id="thread-abc", in_reply_to="task-123")
    d = res.to_dict()
    assert d["thread_id"] == "thread-abc"
    assert d["in_reply_to"] == "task-123"
    res2 = TaskResult.from_dict(d)
    assert res2.thread_id == "thread-abc"
    print("✅ TaskResult threading fields")


def test_thread_dataclass():
    """Thread groups task IDs and serializes."""
    from manifold.protocol import Thread
    t = Thread(thread_id="t-1", task_ids=["a", "b"])
    t.add("c")
    t.add("a")  # duplicate, ignored
    assert t.length == 3
    assert t.task_ids == ["a", "b", "c"]
    d = t.to_dict()
    t2 = Thread.from_dict(d)
    assert t2.thread_id == "t-1"
    assert t2.task_ids == ["a", "b", "c"]
    print("✅ Thread dataclass")


def test_conversation_thread():
    """Simulate a multi-turn conversation."""
    from manifold.protocol import TaskRequest, TaskResult, Thread, TaskStatus
    thread = Thread(thread_id="conv-1")
    # Turn 1
    r1 = TaskRequest(target="analyst@hub", command="analyze", thread_id=thread.thread_id)
    thread.add(r1.id)
    res1 = TaskResult(id=r1.id, status=TaskStatus.SUCCESS, thread_id=thread.thread_id)
    # Turn 2 — follow-up
    r2 = TaskRequest(target="analyst@hub", command="deeper", thread_id=thread.thread_id, in_reply_to=r1.id)
    thread.add(r2.id)
    res2 = TaskResult(id=r2.id, status=TaskStatus.SUCCESS, thread_id=thread.thread_id, in_reply_to=r2.id)
    assert thread.length == 2
    assert r2.in_reply_to == r1.id
    print("✅ Multi-turn conversation")


if __name__ == "__main__":
    # ... existing calls stay, add new ones
    pass
