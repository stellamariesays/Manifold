#!/usr/bin/env python3
"""btc-signals-agent — BTC breakout detection, technical analysis, signal composition."""
import json, sys

def cmd_status():
    return {"agent": "btc-signals", "status": "ok", "capabilities": ["alert-design","backtest-strategy","btc-breakout-detection","cross-asset-correlation","indicator-fusion","signal-composition","stingray-integration","technical-analysis","topology-routing","volatility-analysis","volume-analysis"]}

def cmd_ping():
    return {"agent": "btc-signals", "pong": True}

COMMANDS = {"status": cmd_status, "ping": cmd_ping}

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd in COMMANDS:
        print(json.dumps(COMMANDS[cmd]()))
    else:
        print(json.dumps({"agent": "btc-signals", "error": f"unknown command: {cmd}"}))
        sys.exit(1)

if __name__ == "__main__":
    main()
