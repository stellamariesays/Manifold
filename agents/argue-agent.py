#!/usr/bin/env python3
"""argue-agent — Argumentation, debate strategy, jury modeling, token staking."""
import json, sys

def cmd_status():
    return {"agent": "argue", "status": "ok", "capabilities": ["argumentation","debate-strategy","jury-modeling","on-chain-interaction","rhetorical-structure","token-staking"]}

def cmd_ping():
    return {"agent": "argue", "pong": True}

COMMANDS = {"status": cmd_status, "ping": cmd_ping}

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd in COMMANDS:
        print(json.dumps(COMMANDS[cmd]()))
    else:
        print(json.dumps({"agent": "argue", "error": f"unknown command: {cmd}"}))
        sys.exit(1)

if __name__ == "__main__":
    main()
