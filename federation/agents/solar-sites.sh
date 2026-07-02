#!/bin/bash
# Solar-sites agent — web deployment & visualization
# Commands: ping, health-check, status, list-sites

COMMAND="${1:-ping}"

case "$COMMAND" in
  ping)
    echo '{"status":"ok","message":"pong","agent":"solar-sites"}'
    ;;
  health-check)
    SITES=$(ls /home/stella/openclaw-workspace/stella/sites/ 2>/dev/null | wc -l || echo 0)
    echo "{\"status\":\"healthy\",\"agent\":\"solar-sites\",\"hub\":\"trillian\",\"sites_count\":$SITES,\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
    ;;
  status)
    echo "{\"agent\":\"solar-sites\",\"hub\":\"trillian\",\"mode\":\"active\",\"capabilities\":[\"web-deployment\",\"d3-visualization\",\"solar-data-display\",\"surge-deployment\"],\"pid\":$$}"
    ;;
  list-sites)
    SITES=$(ls /home/stella/openclaw-workspace/stella/sites/ 2>/dev/null | head -10 | python3 -c "import sys,json; print(json.dumps(sys.stdin.read().split()))" 2>/dev/null || echo '[]')
    echo "{\"agent\":\"solar-sites\",\"sites\":$SITES,\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
    ;;
  *)
    echo "{\"status\":\"error\",\"error\":\"unknown command: $COMMAND\",\"agent\":\"solar-sites\",\"available\":[\"ping\",\"health-check\",\"status\",\"list-sites\"]}"
    ;;
esac
