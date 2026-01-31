#!/bin/bash
# Worker script - simulates a background worker processing tasks

WORKER_ID=${WORKER_ID:-1}

echo "Worker $WORKER_ID started at $(date)"

task_count=0
while true; do
    task_count=$((task_count + 1))
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Worker $WORKER_ID - Processing task #$task_count"
    
    # Simulate work (random sleep between 2-5 seconds)
    sleep_time=$((RANDOM % 4 + 2))
    sleep $sleep_time
    
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Worker $WORKER_ID - Task #$task_count completed"
done
