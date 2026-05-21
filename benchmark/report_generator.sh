#!/bin/bash
# report_generator.sh
# Tu dong tong hop ket qua benchmark -> report file
# Usage: ./benchmark/report_generator.sh [results_dir]

RESULTS_DIR="${1:-benchmark/results}"
TS=$(date +%Y%m%d_%H%M%S)
REPORT="benchmark/results/report_${TS}.txt"

mkdir -p "$RESULTS_DIR"

{
  echo "========================================================================"
  echo "  OTTO RECOMMENDER PIPELINE - BENCHMARK REPORT"
  echo "  Date: $(date '+%Y-%m-%d %H:%M:%S')"
  echo "  Docker version: $(docker info --format '{{.ServerVersion}}' 2>/dev/null)"
  echo "========================================================================"
  echo ""

  # 1. System Info
  echo "--- SYSTEM INFO ---"
  echo "CPU cores: $(nproc)"
  echo "Memory: $(free -h | grep Mem | awk '{print $2}') total"
  echo "Disk: $(df -h . | tail -1 | awk '{print $2}') total, $(df -h . | tail -1 | awk '{print $5}') used"
  echo ""

  # 2. Docker containers
  echo "--- SERVICES ---"
  docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"
  echo ""

  # 3. Kafka metrics
  KAFKA_LOG=$(ls -t ${RESULTS_DIR}/kafka_producer_*.log 2>/dev/null | head -1)
  if [ -f "$KAFKA_LOG" ]; then
    echo "--- KAFKA PRODUCER ---"
    grep -E "records sent" "$KAFKA_LOG" | tail -3
    echo ""
  fi

  KAFKA_CON_LOG=$(ls -t ${RESULTS_DIR}/kafka_consumer_*.log 2>/dev/null | head -1)
  if [ -f "$KAFKA_CON_LOG" ]; then
    echo "--- KAFKA CONSUMER ---"
    grep -E "records consumed" "$KAFKA_CON_LOG" | tail -3
    echo ""
  fi

  # 5. Spark stability
  echo "--- SPARK STREAMING STABILITY ---"
  docker exec otto-postgres psql -U otto -d otto_recommender -t -A \
    -c "SELECT
      COUNT(*) AS batches,
      ROUND(AVG(batch_duration_ms)) AS avg_ms,
      ROUND(MAX(batch_duration_ms)) AS max_ms,
      ROUND(AVG(batch_duration_ms::numeric / 10000), 2) AS stability
    FROM spark_metrics
    WHERE timestamp > NOW() - INTERVAL '30 minutes';" 2>/dev/null || echo "Cannot query spark_metrics"
  echo ""

  # 6. E2E latency
  echo "--- E2E PIPELINE LATENCY ---"
  docker exec otto-postgres psql -U otto -d otto_recommender -t -A \
    -c "SELECT
      COUNT(*) AS events,
      ROUND(AVG(EXTRACT(EPOCH FROM (NOW() - created_at)))) AS avg_s,
      ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (NOW() - created_at)))) AS p50_s,
      ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (NOW() - created_at)))) AS p95_s
    FROM collected_events
    WHERE created_at > NOW() - INTERVAL '15 minutes';" 2>/dev/null || echo "Cannot query collected_events"
  echo ""

  # 7. Resource summary
  echo "--- RESOURCE USAGE (AVG during test) ---"
  STATS_FILE=$(ls -t ${RESULTS_DIR}/stats_*.csv 2>/dev/null | head -1)
  if [ -f "$STATS_FILE" ]; then
    for svc in "otto-api" "otto-spark-streaming" "kafka" "otto-postgres" "redis"; do
      AVG_CPU=$(grep "$svc" "$STATS_FILE" | awk -F',' '{gsub(/%/,"",$3); sum+=$3; count++} END{if(count>0) printf "%.1f", sum/count; else print "N/A"}')
      PEAK_CPU=$(grep "$svc" "$STATS_FILE" | awk -F',' '{gsub(/%/,"",$3); if($3>max) max=$3} END{if(max>0) printf "%.1f", max; else print "N/A"}')
      AVG_MEM=$(grep "$svc" "$STATS_FILE" | awk -F',' '{print $4}' | grep -oP '[\d.]+' | awk '{sum+=$1; count++} END{if(count>0) printf "%.0f", sum/count; else print "N/A"}')
      echo "  $svc: CPU avg=${AVG_CPU}% peak=${PEAK_CPU}% | Mem avg=${AVG_MEM}MB"
    done
  else
    echo "  No docker stats CSV found (looked for stats_*.csv)"
  fi

  # 8. SLA Summary
  echo ""
  echo "--- SLA VERDICT ---"
  echo "  API P95 latency:      [PENDING] (run k6 with --summary-export)"
  echo "  API error rate:       [PENDING]"
  echo "  Kafka producer TPS:   [PENDING]"
  echo "  Spark stability:      [PENDING]"
  echo "  E2E latency P50:      [PENDING]"
  echo "  E2E latency P95:      [PENDING]"
  echo ""
  echo "========================================================================"
  echo "  Report saved to: $REPORT"
  echo "========================================================================"

} > "$REPORT"

cat "$REPORT"
