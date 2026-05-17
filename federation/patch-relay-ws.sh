#!/bin/bash
# Patch websocket-handler.js to add raw wire logging
cd /opt/Manifold/federation/dist/server

# Line 19 is `if (msgType === 'task_result') {` in handleClientMessage
# Insert debug log after line 19 (inside the if block)
sed -i '19a\            console.log("[ws-handler:client:raw] has_result_key=" + !!msg.result + " body_in_msg=" + !!msg.body + " body_in_result=" + !!msg.result?.body + " keys=" + Object.keys(msg).join(","));' websocket-handler.js

echo "Patched websocket-handler.js"
grep -n "ws-handler:client:raw" websocket-handler.js
