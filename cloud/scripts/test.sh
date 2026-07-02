#!/bin/bash
set -e
cd /home/stella/openclaw-workspace/stella/projects/manifold-cloud

node dist/index.js &
SERVER_PID=$!
sleep 2

echo "=== /health ==="
curl -sf http://localhost:3000/health | python3 -m json.tool
echo

echo "=== /v1/register ==="
REG=$(curl -sf -X POST http://localhost:3000/v1/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@manifold.cloud","tier":"free"}')
echo "$REG" | python3 -m json.tool
echo

APIKEY=$(echo "$REG" | python3 -c "import json,sys; print(json.load(sys.stdin)['data']['apiKey'])")
echo "Got API key: ${APIKEY:0:20}..."
echo

echo "=== /v1/usage ==="
curl -sf http://localhost:3000/v1/usage \
  -H "Authorization: Bearer $APIKEY" | python3 -m json.tool
echo

echo "=== /v1/models ==="
curl -sf http://localhost:3000/v1/models \
  -H "Authorization: Bearer $APIKEY" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'{len(d[\"data\"][\"models\"])} models available')"
echo

echo "=== /v1/route ==="
curl -sf -X POST http://localhost:3000/v1/route \
  -H "Authorization: Bearer $APIKEY" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"write code","capabilities":["code","fast"],"preferCheapest":true}' | python3 -m json.tool
echo

echo "=== auth failure ==="
curl -sf http://localhost:3000/v1/usage \
  -H "Authorization: Bearer mk_live_invalid" 2>&1 || echo "(expected 401)"
echo

echo "=== /v1/hubs ==="
curl -sf http://localhost:3000/v1/hubs \
  -H "Authorization: Bearer $APIKEY" | python3 -m json.tool
echo

echo "=== /v1/hubs/scale ==="
curl -sf -X POST http://localhost:3000/v1/hubs/scale \
  -H "Authorization: Bearer $APIKEY" | python3 -m json.tool
echo

kill $SERVER_PID 2>/dev/null || true
wait $SERVER_PID 2>/dev/null || true
echo "=== All tests passed ==="
