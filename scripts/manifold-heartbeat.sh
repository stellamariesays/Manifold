#!/bin/bash
# Heartbeat for Manifold mesh agents on sateliteA
# Sends PUT /agents/:name/heartbeat for each agent every cycle

REST_URL="http://localhost:8767"
ATLAS="/home/stella/openclaw-workspace/stella/data/manifold/stella-atlas.json"

if ! command -v jq &>/dev/null; then
    # Fallback: use python
    python3 -c "
import json, urllib.request, sys
try:
    with open('$ATLAS') as f:
        atlas = json.load(f)
    for agent in atlas.get('agents', []):
        name = agent['name']
        try:
            req = urllib.request.Request(
                f'$REST_URL/agents/{name}/heartbeat',
                data=b'{}',
                headers={'Content-Type': 'application/json'},
                method='PUT'
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                pass
        except Exception as e:
            print(f'heartbeat {name}: {e}', file=sys.stderr)
except Exception as e:
    print(f'atlas load failed: {e}', file=sys.stderr)
"
    exit 0
fi

for name in $(jq -r '.agents[].name' "$ATLAS" 2>/dev/null); do
    curl -sf -X PUT "$REST_URL/agents/$name/heartbeat" -H 'Content-Type: application/json' -d '{}' > /dev/null 2>&1 || true
done
