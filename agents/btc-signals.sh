#!/bin/bash
# btc-signals agent wrapper for Manifold runner
# Forwards commands to btc-signals-agent.py

CMD="${1:-status}"
shift 2>/dev/null || true

if [ -n "$1" ]; then
    python3 "$(dirname "$0")/btc-signals-agent.py" "$CMD" "$@"
else
    python3 "$(dirname "$0")/btc-signals-agent.py" "$CMD"
fi
