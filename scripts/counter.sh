#!/bin/bash
# Counter script - counts to a specified number and exits

COUNT_TO=${COUNT_TO:-10}

echo "Counter started at $(date)"
echo "Counting to $COUNT_TO"

for i in $(seq 1 $COUNT_TO); do
    echo "Count: $i"
    sleep 1
done

echo "Counter finished at $(date)"
exit 0
