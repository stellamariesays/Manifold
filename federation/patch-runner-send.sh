#!/bin/bash
# Add send-time logging to runner's sendResult
cd /opt/Manifold/federation
sed -i "s|ws.send(JSON.stringify({ type: 'task_result', result }));|console.log('[runner:send] id=' + result.id.substring(0,8) + ' body=' + (result.body ? JSON.stringify(result.body).substring(0,200) : 'MISSING') + ' keys=' + Object.keys(result).join(',')); ws.send(JSON.stringify({ type: 'task_result', result }));|" runner.cjs
echo "Patched runner.cjs"
grep -n "runner:send" runner.cjs
