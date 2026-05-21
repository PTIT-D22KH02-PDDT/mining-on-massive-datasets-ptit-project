#!/bin/bash
# log_resources.sh - Ghi docker stats vao CSV lien tuc
# Usage: ./benchmark/log_resources.sh [output_file] [interval_sec]

OUTPUT="${1:-benchmark/results/docker_stats.csv}"
INTERVAL="${2:-5}"

mkdir -p "$(dirname "$OUTPUT")"
echo "timestamp,name,cpu_percent,mem_usage,mem_percent,net_io" > "$OUTPUT"

echo "Logging docker stats every ${INTERVAL}s to ${OUTPUT} (PID: $$)"

while true; do
  docker stats --no-stream --format "{{.Name}},{{.CPUPerc}},{{.MemUsage}},{{.MemPerc}},{{.NetIO}}" \
    | while read line; do
      echo "$(date +%Y-%m-%d_%H:%M:%S),$line" >> "$OUTPUT"
    done
  sleep "$INTERVAL"
done
