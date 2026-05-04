#!/bin/bash
# Infra agent — system administration & deployment
# Commands: ping, health-check, status, sys-info, services, disk-usage

COMMAND="${1:-ping}"

case "$COMMAND" in
  ping)
    echo '{"status":"ok","message":"pong","agent":"infra"}'
    ;;
  health-check)
    LOAD=$(cat /proc/loadavg | awk '{print $1}')
    MEM=$(free -m | awk '/Mem:/{printf "{\"total\":%d,\"used\":%d,\"pct\":%.1f}", $2, $3, $3/$2*100}')
    echo "{\"status\":\"healthy\",\"agent\":\"infra\",\"hub\":\"trillian\",\"load_1m\":\"$LOAD\",\"memory\":$MEM,\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
    ;;
  status)
    echo "{\"agent\":\"infra\",\"hub\":\"trillian\",\"mode\":\"active\",\"capabilities\":[\"system-administration\",\"cron-management\",\"deployment\",\"git-workflow\"],\"pid\":$$}"
    ;;
  sys-info)
    KERNEL=$(uname -r)
    ARCH=$(uname -m)
    CPU_COUNT=$(nproc)
    UPTIME=$(uptime -p 2>/dev/null || uptime)
    echo "{\"agent\":\"infra\",\"kernel\":\"$KERNEL\",\"arch\":\"$ARCH\",\"cpu_count\":$CPU_COUNT,\"uptime\":\"$UPTIME\",\"hostname\":\"$(hostname)\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
    ;;
  services)
    # Check manifold-related services
    MANIFOLD_PID=$(pgrep -f "standalone.cjs" | head -1 || echo "down")
    RUNNER_PID=$(pgrep -f "agent-runner" | head -1 || echo "down")
    CADDY=$(pgrep caddy | head -1 || echo "down")
    echo "{\"agent\":\"infra\",\"services\":{\"manifold\":\"${MANIFOLD_PID:+running}\",\"runner\":\"${RUNNER_PID:+running}\",\"caddy\":\"${CADDY:+running}\"},\"manifold_pid\":\"$MANIFOLD_PID\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
    ;;
  disk-usage)
    USAGE=$(df -h / | awk 'NR==2{printf "{\"total\":\"%s\",\"used\":\"%s\",\"avail\":\"%s\",\"pct\":\"%s\"}", $2, $3, $4, $5}')
    echo "{\"agent\":\"infra\",\"disk\":$USAGE,\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
    ;;
  *)
    echo "{\"status\":\"error\",\"error\":\"unknown command: $COMMAND\",\"agent\":\"infra\",\"available\":[\"ping\",\"health-check\",\"status\",\"sys-info\",\"services\",\"disk-usage\"]}"
    ;;
esac
