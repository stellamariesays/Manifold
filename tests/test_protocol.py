"""Tests for task execution protocol — validates TS/Python JSON compatibility."""

import json
import sys
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.protocol import (
    TaskRequest, TaskResult, TaskStatus,
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
    test_parse_message()
    print("\n🟢 All protocol tests passed")
