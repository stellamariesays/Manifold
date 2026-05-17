#!/bin/bash
# Add raw message logging to websocket-handler.ts (handleClientMessage task_result)
cd /opt/Manifold/federation/src/server
sed -i '53a\      console.log("[ws-handler:client:RAW-MSG] raw_json=" + JSON.stringify(msg).substring(0, 500))' websocket-handler.ts
echo "Patched websocket-handler.ts"
grep -n "RAW-MSG" websocket-handler.ts
