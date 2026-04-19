#!/usr/bin/env python3
"""manifold-agent — Agent topology, atlas building, cognitive mesh, geodesic routing."""
import json, sys

def cmd_status():
    return {"agent": "manifold", "status": "ok", "capabilities": ["agent-topology","atlas-building","cognitive-mesh","geodesic-routing","seam-detection","sophia-score","transition-maps"]}

def cmd_ping():
    return {"agent": "manifold", "pong": True}

COMMANDS = {"status": cmd_status, "ping": cmd_ping}

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd in COMMANDS:
        print(json.dumps(COMMANDS[cmd]()))
    else:
        print(json.dumps({"agent": "manifold", "error": f"unknown command: {cmd}"}))
        sys.exit(1)

if __name__ == "__main__":
    main()
