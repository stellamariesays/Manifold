#!/usr/bin/env python3
"""wake-agent — Elixir process, fine-tuning, identity alignment, local model training."""
import json, sys

def cmd_status():
    return {"agent": "wake", "status": "ok", "capabilities": ["elixir-process","fine-tuning","identity-alignment","local-model","runpod-compute","training-data"]}

def cmd_ping():
    return {"agent": "wake", "pong": True}

COMMANDS = {"status": cmd_status, "ping": cmd_ping}

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd in COMMANDS:
        print(json.dumps(COMMANDS[cmd]()))
    else:
        print(json.dumps({"agent": "wake", "error": f"unknown command: {cmd}"}))
        sys.exit(1)

if __name__ == "__main__":
    main()
