#!/bin/bash
# Stella agent — identity & continuity
# Commands: health-check, ping, status, memory-summary, identity-check

COMMAND="${1:-ping}"
ARGS="${2:-{}}"

case "$COMMAND" in
  ping)
    echo '{"status":"ok","message":"pong","agent":"stella"}'
    ;;
  health-check)
    MEM_USAGE=$(free -m | awk '/Mem:/{printf "%.1f", $3/$2*100}')
    DISK_USAGE=$(df -h / | awk 'NR==2{print $5}')
    UPTIME=$(uptime -p 2>/dev/null || uptime)
    echo "{\"status\":\"healthy\",\"memory_pct\":$MEM_USAGE,\"disk_usage\":\"$DISK_USAGE\",\"uptime\":\"$UPTIME\",\"agent\":\"stella\",\"hub\":\"trillian\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
    ;;
  status)
    echo "{\"agent\":\"stella\",\"hub\":\"trillian\",\"mode\":\"active\",\"capabilities\":[\"identity-continuity\",\"session-memory\",\"conversation-strategy\",\"judgment\"],\"uptime\":\"$(uptime -p 2>/dev/null || uptime)\",\"pid\":$$,\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
    ;;
  memory-summary)
    # Count memory files
    MEM_FILES=$(find /home/stella/openclaw-workspace/stella/memory -name "*.md" 2>/dev/null | wc -l)
    DAILY_FILES=$(find /home/stella/openclaw-workspace/stella/memory/daily -name "*.md" 2>/dev/null | wc -l)
    echo "{\"agent\":\"stella\",\"memory_files\":$MEM_FILES,\"daily_files\":$DAILY_FILES,\"status\":\"ok\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
    ;;
  *)
    echo "{\"status\":\"error\",\"error\":\"unknown command: $COMMAND\",\"agent\":\"stella\",\"available\":[\"ping\",\"health-check\",\"status\",\"memory-summary\"]}"
    ;;
esac
