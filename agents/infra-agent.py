#!/usr/bin/env python3
"""infra-agent — System administration, deployment, security hardening."""
import json, sys

def cmd_status():
    return {"agent": "infra", "status": "ok", "capabilities": ["cron-management","deployment","git-workflow","security-hardening","ssh-management","system-administration"]}

def cmd_ping():
    return {"agent": "infra", "pong": True}

COMMANDS = {"status": cmd_status, "ping": cmd_ping}

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd in COMMANDS:
        print(json.dumps(COMMANDS[cmd]()))
    else:
        print(json.dumps({"agent": "infra", "error": f"unknown command: {cmd}"}))
        sys.exit(1)

if __name__ == "__main__":
    main()
