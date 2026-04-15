#!/usr/bin/env python3
"""Test agent for validating the agent runner."""

import json
import sys

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "no command"}))
        sys.exit(1)

    command = sys.argv[1]
    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}

    if command == "echo":
        print(json.dumps({"echo": args}))
    elif command == "status":
        print(json.dumps({"status": "ok", "name": "test-agent", "uptime": 42}))
    elif command == "fail":
        print(json.dumps({"error": "intentional failure"}), file=sys.stderr)
        sys.exit(1)
    elif command == "slow":
        import time
        time.sleep(5)
        print(json.dumps({"status": "done", "slept": 5}))
    else:
        print(json.dumps({"error": f"unknown command: {command}"}))
        sys.exit(1)

if __name__ == "__main__":
    main()
