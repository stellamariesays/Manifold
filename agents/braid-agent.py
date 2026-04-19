#!/usr/bin/env python3
"""braid-agent — Solar flare prediction, lifecycle modeling, signal processing."""
import json, sys

def cmd_status():
    return {"agent": "braid", "status": "ok", "capabilities": ["active-region-classification","alfven-clock","alfven-wave-timing","lifecycle-deployment","lifecycle-modeling","machine-learning","signal-processing","solar-flare-prediction","space-weather"]}

def cmd_ping():
    return {"agent": "braid", "pong": True}

COMMANDS = {"status": cmd_status, "ping": cmd_ping}

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd in COMMANDS:
        print(json.dumps(COMMANDS[cmd]()))
    else:
        print(json.dumps({"agent": "braid", "error": f"unknown command: {cmd}"}))
        sys.exit(1)

if __name__ == "__main__":
    main()
