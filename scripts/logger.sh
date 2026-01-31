#!/bin/bash
# Logger script - logs timestamps at regular intervals

LOG_INTERVAL=${LOG_INTERVAL:-5}

echo "Logger started at $(date)"
echo "Logging every $LOG_INTERVAL seconds"

while true; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Heartbeat - System is running"
    sleep $LOG_INTERVAL
done
