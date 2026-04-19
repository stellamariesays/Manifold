#!/usr/bin/env python3
"""deploy-agent — API deployment, manifest generation, multi-project orchestration."""
import json, sys

def cmd_status():
    return {"agent": "deploy", "status": "ok", "capabilities": ["api-deployment","artifact-detection","deployment-execution","failure-recovery","manifest-generation","multi-project-orchestration","prerequisite-validation","ssh-deployment","state-tracking","surge-deployment"]}

def cmd_ping():
    return {"agent": "deploy", "pong": True}

COMMANDS = {"status": cmd_status, "ping": cmd_ping}

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd in COMMANDS:
        print(json.dumps(COMMANDS[cmd]()))
    else:
        print(json.dumps({"agent": "deploy", "error": f"unknown command: {cmd}"}))
        sys.exit(1)

if __name__ == "__main__":
    main()
