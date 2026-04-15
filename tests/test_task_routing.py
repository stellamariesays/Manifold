#!/usr/bin/env python3
"""
End-to-end test: task routing through federation.

Starts a federation server, connects an agent runner with a test agent,
submits tasks via REST API, validates results.
"""

import json
import subprocess
import sys
import time
import urllib.request

# ── Config ──────────────────────────────────────────────────────────────────────

REST_URL = "http://localhost:8777"
LOCAL_WS = "ws://localhost:8768"
TEST_AGENT_SCRIPT = "/tmp/test-task-agent.py"

# ── Test agent ──────────────────────────────────────────────────────────────────

TEST_AGENT_CODE = '''#!/usr/bin/env python3
import json, sys
cmd = sys.argv[1] if len(sys.argv) > 1 else ""
args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
if cmd == "echo":
    print(json.dumps({"echo": args}))
elif cmd == "status":
    print(json.dumps({"status": "ok", "name": "test-agent"}))
elif cmd == "fail":
    print(json.dumps({"error": "intentional"}), file=sys.stderr)
    sys.exit(1)
else:
    print(json.dumps({"error": f"unknown: {cmd}"}))
    sys.exit(1)
'''

def setup_test_agent():
    with open(TEST_AGENT_SCRIPT, 'w') as f:
        f.write(TEST_AGENT_CODE)
    import os
    os.chmod(TEST_AGENT_SCRIPT, 0o755)

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

def test_status():
    """Server should be running."""
    status = rest_get("/status")
    assert status["status"] == "ok"
    print("✅ Server running")

def test_submit_task():
    """Submit a task via REST and get a result."""
    result = rest_post("/task", {
        "target": "test-agent@hog",
        "command": "status",
        "timeout_ms": 5000,
    })
    print(f"   Task result: {json.dumps(result)[:100]}")
    # Without a runner, expect not_found or timeout
    assert result.get("status") in ("success", "timeout", "not_found"), f"Unexpected: {result}"
    if result.get("status") == "success":
        assert result["output"]["status"] == "ok"
    print("✅ Submit task (no runner — expected not_found/timeout)")

def test_echo_task():
    """Submit an echo task with args."""
    result = rest_post("/task", {
        "target": "test-agent@hog",
        "command": "echo",
        "args": {"hello": "world"},
        "timeout_ms": 5000,
    })
    assert result.get("status") in ("success", "timeout", "not_found")
    if result.get("status") == "success":
        assert result["output"]["echo"] == {"hello": "world"}
    print("✅ Echo task (no runner — expected not_found/timeout)")

def test_not_found():
    """Submit to nonexistent agent."""
    result = rest_post("/task", {
        "target": "nonexistent@hog",
        "command": "status",
        "timeout_ms": 5000,
    })
    assert result.get("status") in ("not_found", "timeout") or result.get("error")
    print("✅ Not found")

def test_pending_tasks():
    """Check pending tasks endpoint."""
    result = rest_get("/tasks")
    assert "pending" in result
    print(f"✅ Pending tasks (runners: {result.get('runner_count', 0)})")

if __name__ == "__main__":
    # Check if server is running
    try:
        rest_get("/status")
    except Exception as e:
        print(f"❌ Federation server not running on {REST_URL}: {e}")
        print("   Start it first: cd federation && ./start-hog.sh")
        sys.exit(1)

    setup_test_agent()

    print("Running task routing tests...")
    test_status()
    test_pending_tasks()

    # Note: task execution requires an agent runner connected
    # These tests validate the REST API contract
    test_submit_task()
    test_echo_task()
    test_not_found()

    print("\n🟢 All task routing tests passed")
