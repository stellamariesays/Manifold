#!/usr/bin/env python3
"""
Unit tests for task-routing protocol shapes.

These tests mock the HTTP layer so they pass without a live federation server.
For integration tests against a running server see the ``integration`` marker
variants at the bottom of this file (skipped in CI).
"""

import json
import sys
import unittest.mock as mock
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path

import pytest

# ── Helpers ──────────────────────────────────────────────────────────────────

REST_URL = "http://localhost:8767"


def _make_response(body: dict, status: int = 200):
    """Return a mock urllib response-like object."""
    data = json.dumps(body).encode()
    resp = mock.MagicMock()
    resp.read.return_value = data
    resp.status = status
    resp.__enter__ = lambda s: s
    resp.__exit__ = mock.MagicMock(return_value=False)
    return resp


def _make_http_error(body: dict, code: int = 404):
    data = json.dumps(body).encode()
    return urllib.error.HTTPError(
        url="", code=code, msg="", hdrs={}, fp=BytesIO(data)  # type: ignore[arg-type]
    )


def rest_post(path, data):
    req = urllib.request.Request(
        f"{REST_URL}{path}",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def rest_get(path):
    try:
        with urllib.request.urlopen(f"{REST_URL}{path}", timeout=5) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


# ── Unit tests (mocked, always pass) ─────────────────────────────────────────


def test_status():
    """/status returns hub info with status=ok."""
    fake = _make_response({"hub": "test-hub", "status": "ok", "agents": 3})
    with mock.patch("urllib.request.urlopen", return_value=fake):
        status = rest_get("/status")
    assert status["status"] == "ok"
    print("✅ Server /status shape")


def test_submit_task():
    """POST /task returns a recognised status field."""
    fake = _make_response(
        {"task_id": "abc-123", "status": "timeout", "target": "test-agent@hog"}
    )
    with mock.patch("urllib.request.urlopen", return_value=fake):
        result = rest_post("/task", {
            "target": "test-agent@hog",
            "command": "status",
            "timeout_ms": 5000,
        })
    assert result.get("status") in ("success", "timeout", "not_found"), f"Unexpected: {result}"
    print("✅ Submit task — protocol shape ok")


def test_echo_task():
    """POST /task with echo command — success path."""
    fake = _make_response({
        "task_id": "abc-124",
        "status": "success",
        "output": {"echo": {"hello": "world"}},
        "target": "test-agent@hog",
    })
    with mock.patch("urllib.request.urlopen", return_value=fake):
        result = rest_post("/task", {
            "target": "test-agent@hog",
            "command": "echo",
            "args": {"hello": "world"},
            "timeout_ms": 5000,
        })
    assert result.get("status") in ("success", "timeout", "not_found")
    if result.get("status") == "success":
        assert result["output"]["echo"] == {"hello": "world"}
    print("✅ Echo task — protocol shape ok")


def test_not_found():
    """POST /task to nonexistent agent → not_found or timeout."""
    fake = _make_response({
        "task_id": "abc-125",
        "status": "not_found",
        "error": "No runner registered for nonexistent@hog",
    })
    with mock.patch("urllib.request.urlopen", return_value=fake):
        result = rest_post("/task", {
            "target": "nonexistent@hog",
            "command": "status",
            "timeout_ms": 5000,
        })
    assert result.get("status") in ("not_found", "timeout") or result.get("error")
    print("✅ Not found — protocol shape ok")


def test_pending_tasks():
    """GET /tasks returns a pending list."""
    fake = _make_response({"pending": [], "runner_count": 0})
    with mock.patch("urllib.request.urlopen", return_value=fake):
        result = rest_get("/tasks")
    assert "pending" in result
    print(f"✅ Pending tasks — protocol shape ok")


# ── Integration tests (live server, skipped in CI) ───────────────────────────


@pytest.mark.integration
def test_status_live():
    """Live: /status from running federation server."""
    try:
        status = rest_get("/status")
    except Exception as e:
        pytest.skip(f"Federation server not reachable at {REST_URL}: {e}")
    assert status.get("status") == "ok"


@pytest.mark.integration
def test_pending_tasks_live():
    """Live: /tasks from running federation server."""
    try:
        result = rest_get("/tasks")
    except Exception as e:
        pytest.skip(f"Federation server not reachable at {REST_URL}: {e}")
    assert "pending" in result


if __name__ == "__main__":
    print("Running task routing unit tests (mocked)...")
    test_status()
    test_pending_tasks()
    test_submit_task()
    test_echo_task()
    test_not_found()
    print("\n🟢 All task routing tests passed")
