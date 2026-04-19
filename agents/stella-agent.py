#!/usr/bin/env python3
"""stella-agent — Agent orchestration, context management, identity continuity."""
import json, sys

def cmd_status():
    return {"agent": "stella", "status": "ok", "capabilities": ["agent-orchestration","context-management","conversation-strategy","identity-continuity","identity-modeling","judgment","personality-coherence","session-memory","terrain-awareness","trust-modeling"]}

def cmd_ping():
    return {"agent": "stella", "pong": True}

COMMANDS = {"status": cmd_status, "ping": cmd_ping}

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd in COMMANDS:
        print(json.dumps(COMMANDS[cmd]()))
    else:
        print(json.dumps({"agent": "stella", "error": f"unknown command: {cmd}"}))
        sys.exit(1)

if __name__ == "__main__":
    main()
