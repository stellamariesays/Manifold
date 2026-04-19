#!/usr/bin/env python3
"""solar-sites-agent — D3 visualization, realtime dashboard, web deployment."""
import json, sys

def cmd_status():
    return {"agent": "solar-sites", "status": "ok", "capabilities": ["d3-visualization","javascript-frontend","realtime-dashboard","solar-data-display","surge-deployment","web-deployment"]}

def cmd_ping():
    return {"agent": "solar-sites", "pong": True}

COMMANDS = {"status": cmd_status, "ping": cmd_ping}

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd in COMMANDS:
        print(json.dumps(COMMANDS[cmd]()))
    else:
        print(json.dumps({"agent": "solar-sites", "error": f"unknown command: {cmd}"}))
        sys.exit(1)

if __name__ == "__main__":
    main()
