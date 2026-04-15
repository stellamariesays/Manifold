"""Tests for the agent runner — validates task execution pipeline."""

import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
TEST_AGENT = str(REPO_ROOT / "tests" / "test-agent.py")


def run_agent(command: str, args: dict | None = None) -> tuple[int, str, str]:
    """Run the test agent script and return (exit_code, stdout, stderr)."""
    cmd = [sys.executable, TEST_AGENT, command]
    if args:
        cmd.append(json.dumps(args))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def test_echo():
    code, out, err = run_agent("echo", {"hello": "world"})
    assert code == 0
    data = json.loads(out)
    assert data["echo"] == {"hello": "world"}
    print("✅ test-agent echo")


def test_status():
    code, out, err = run_agent("status")
    assert code == 0
    data = json.loads(out)
    assert data["status"] == "ok"
    assert data["name"] == "test-agent"
    print("✅ test-agent status")


def test_fail():
    code, out, err = run_agent("fail")
    assert code != 0
    assert "intentional failure" in err
    print("✅ test-agent fail")


def test_unknown_command():
    code, out, err = run_agent("nonexistent")
    assert code != 0
    print("✅ test-agent unknown command")


def test_no_command():
    code, out, err = run_agent.__wrapped__(None) if hasattr(run_agent, '__wrapped__') else (1, "", "")
    # Direct test
    result = subprocess.run(
        [sys.executable, TEST_AGENT],
        capture_output=True, text=True, timeout=10
    )
    assert result.returncode != 0
    print("✅ test-agent no command")


def test_python_runner_imports():
    """Verify the Python agent runner module imports cleanly."""
    runner_path = REPO_ROOT / "federation" / "src" / "runtime" / "agent-runner.py"
    # Just check it parses
    compile(runner_path.read_text(), str(runner_path), "exec")
    print("✅ agent-runner.py compiles")


def test_config_valid():
    """Verify runner config is valid JSON with required fields."""
    config_path = REPO_ROOT / "federation" / "runner-config.hog.json"
    config = json.loads(config_path.read_text())
    assert "hub" in config
    assert "agents" in config
    assert len(config["agents"]) > 0
    for agent in config["agents"]:
        assert "name" in agent
        assert "script" in agent
    print(f"✅ runner config valid ({len(config['agents'])} agents)")


if __name__ == "__main__":
    test_echo()
    test_status()
    test_fail()
    test_unknown_command()
    test_no_command()
    test_python_runner_imports()
    test_config_valid()
    print("\n🟢 All runner tests passed")
