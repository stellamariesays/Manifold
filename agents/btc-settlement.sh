#!/bin/bash
# btc-settlement agent wrapper for Manifold runner
# Manages Bitcoin escrow contracts for the federation

CMD="${1:-status}"
shift 2>/dev/null || true

if [ -n "$1" ]; then
    python3 "$(dirname "$0")/btc-settlement-agent.py" "$CMD" "$@"
else
    python3 "$(dirname "$0")/btc-settlement-agent.py" "$CMD"
fi
