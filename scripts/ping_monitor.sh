#!/bin/bash
# Ping monitor script - monitors connectivity to a target

PING_TARGET=${PING_TARGET:-"8.8.8.8"}
PING_INTERVAL=${PING_INTERVAL:-10}

echo "Ping monitor started at $(date)"
echo "Monitoring: $PING_TARGET every $PING_INTERVAL seconds"

while true; do
    if ping -c 1 -W 2 $PING_TARGET > /dev/null 2>&1; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] $PING_TARGET is REACHABLE"
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] $PING_TARGET is UNREACHABLE" >&2
    fi
    sleep $PING_INTERVAL
done
