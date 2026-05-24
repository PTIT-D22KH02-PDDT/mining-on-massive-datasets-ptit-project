#!/bin/bash
# report_generator.sh
# Tu dong tong hop ket qua benchmark -> report file
# Usage: ./benchmark/report_generator.sh [results_dir]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RESULTS_DIR="${1:-${SCRIPT_DIR}/results}"
TS=$(date +%Y%m%d_%H%M%S)
REPORT="${RESULTS_DIR}/report_${TS}.txt"

mkdir -p "$RESULTS_DIR"

# --- Helper: run query inside otto-api container via stdin ---
# Usage: query_db spark | query_db events | query_db tables | query_db all_events
query_db() {
  docker exec -i otto-api python3 /dev/stdin "$1" < "${SCRIPT_DIR}/query_db.py" 2>/dev/null
}

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

  # 4. Spark streaming metrics
  echo "--- SPARK STREAMING PERFORMANCE ---"
  SPARK_DATA=$(query_db spark)
  if [ -n "$SPARK_DATA" ] && [ "$(echo "$SPARK_DATA" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('found',True))" 2>/dev/null)" != "False" ]; then
    echo "  $(echo "$SPARK_DATA" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f'batches={d.get(\"batches\",\"?\")} avg_ms={d.get(\"avg_ms\",\"?\")}ms max_ms={d.get(\"max_ms\",\"?\")}ms avg_rps={d.get(\"avg_rps\",\"?\")} rows/s total_rows={d.get(\"total_rows\",\"?\")}')" 2>/dev/null)"
  else
    echo "  No spark_metrics found (is Spark streaming running?)"
    [ -n "$SPARK_DATA" ] && echo "  Debug: $SPARK_DATA"
  fi
  echo ""

  # 5. E2E pipeline latency
  echo "--- E2E PIPELINE LATENCY ---"
  E2E_DATA=$(query_db events)
  if [ -n "$E2E_DATA" ] && [ "$(echo "$E2E_DATA" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('found',True))" 2>/dev/null)" != "False" ]; then
    echo "  $(echo "$E2E_DATA" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f'events={d.get(\"events\",\"?\")} avg_age={d.get(\"avg_age_s\",\"?\")}s p50={d.get(\"p50_s\",\"?\")}s p95={d.get(\"p95_s\",\"?\")}s')" 2>/dev/null)"
  else
    echo "  No collected_events found (no events flushed yet)"
  fi
  echo ""

  # 6. Resource summary
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

  # 7. SLA Summary
  echo ""
  echo "--- SLA VERDICT ---"

  # Parse k6 summary from handleSummary JSON
  K6_SUMMARY=$(ls -t ${RESULTS_DIR}/k6_summary_*.json 2>/dev/null | head -1)
  if [ -f "$K6_SUMMARY" ]; then
    P95=$(python3 -c "
import json
d = json.load(open('$K6_SUMMARY'))
m = d.get('metrics', {})
hd = m.get('http_req_duration', {}).get('values', {}) or m.get('http_req_duration', {}).get('data', {}).get('values', {})
print(hd.get('p(95)', 'N/A'))
" 2>/dev/null)
    ERR_RATE=$(python3 -c "
import json
d = json.load(open('$K6_SUMMARY'))
m = d.get('metrics', {})
hf = m.get('http_req_failed', {}).get('values', {}) or m.get('http_req_failed', {}).get('data', {}).get('values', {})
r = hf.get('rate', -1)
print(f'{r*100:.2f}%')
" 2>/dev/null)
    API_OK=$(python3 -c "
import json
d = json.load(open('$K6_SUMMARY'))
m = d.get('metrics', {})
hd = m.get('http_req_duration', {}).get('values', {}) or m.get('http_req_duration', {}).get('data', {}).get('values', {})
p = hd.get('p(95)', 9999)
print('FAIL' if p > 1000 else ('WARN' if p > 500 else 'PASS'))
" 2>/dev/null)
    ERR_OK=$(python3 -c "
import json
d = json.load(open('$K6_SUMMARY'))
m = d.get('metrics', {})
hf = m.get('http_req_failed', {}).get('values', {}) or m.get('http_req_failed', {}).get('data', {}).get('values', {})
r = hf.get('rate', 1)
print('PASS' if r < 0.01 else 'FAIL')
" 2>/dev/null)
    echo "  API P95 latency:      ${P95:-N/A}ms  [${API_OK:-?}]"
    echo "  API error rate:       ${ERR_RATE:-N/A}  [${ERR_OK:-?}]"
  else
    echo "  API P95 latency:      N/A (no k6 summary found)"
    echo "  API error rate:       N/A"
  fi

  # Parse Kafka log for TPS
  KAFKA_LOG=$(ls -t ${RESULTS_DIR}/kafka_producer_*.log 2>/dev/null | head -1)
  if [ -f "$KAFKA_LOG" ]; then
    LAST_LINE=$(grep "records sent" "$KAFKA_LOG" | tail -1)
    TPS=$(echo "$LAST_LINE" | grep -oP '[\d,.]+(?= records/sec)' | tr -d ',')
    LAT_P95=$(echo "$LAST_LINE" | grep -oP '[\d,.]+(?= ms 95th)' | tr -d ',')
    KAFKA_OK=$(python3 -c "t=float('${TPS:-0}'.replace(',','')); print('FAIL' if t < 50000 else ('WARN' if t < 100000 else 'PASS'))" 2>/dev/null)
    KAFKA_P95_OK=$(python3 -c "p=float('${LAT_P95:-0}'.replace(',','')); print('FAIL' if p >= 5000 else ('WARN' if p >= 500 else 'PASS'))" 2>/dev/null)
    echo "  Kafka producer TPS:   ${TPS:-N/A}  [${KAFKA_OK:-?}]"
    echo "  Kafka P95 latency:    ${LAT_P95:-N/A}ms  [${KAFKA_P95_OK:-?}]"
  else
    echo "  Kafka producer TPS:   N/A"
  fi

  # Spark stability (from DB query via JSON)
  SPARK_FOUND=$(echo "$SPARK_DATA" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('found',True))" 2>/dev/null)
  if [ -n "$SPARK_DATA" ] && [ "$SPARK_FOUND" != "False" ]; then
    STABILITY=$(echo "$SPARK_DATA" | python3 -c "import sys,json; print(json.load(sys.stdin).get('avg_s','N/A'))" 2>/dev/null)
    SPARK_OK=$(python3 -c "s=float('${STABILITY:-0}'); t=float('${BATCHES:-1}'); print('FAIL' if s > 10 else ('WARN' if s > 8 else 'PASS'))" 2>/dev/null)
    BATCHES=$(echo "$SPARK_DATA" | python3 -c "import sys,json; print(json.load(sys.stdin).get('batches',0))" 2>/dev/null)
    echo "  Spark batch duration: ${STABILITY:-N/A}s  [${SPARK_OK:-?}]"
    echo "  Spark batches:        ${BATCHES:-0}"
  else
    echo "  Spark stability:      N/A (no spark_metrics found)"
  fi

  # E2E latency (from DB query via JSON)
  E2E_FOUND=$(echo "$E2E_DATA" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('found',True))" 2>/dev/null)
  if [ -n "$E2E_DATA" ] && [ "$E2E_FOUND" != "False" ]; then
    P50_E=$(echo "$E2E_DATA" | python3 -c "import sys,json; print(json.load(sys.stdin).get('p50_s','N/A'))" 2>/dev/null)
    P95_E=$(echo "$E2E_DATA" | python3 -c "import sys,json; print(json.load(sys.stdin).get('p95_s','N/A'))" 2>/dev/null)
    E2E_P50_OK=$(python3 -c "p=float('${P50_E:-0}'); print('FAIL' if p > 60 else ('WARN' if p > 30 else 'PASS'))" 2>/dev/null)
    E2E_P95_OK=$(python3 -c "p=float('${P95_E:-0}'); print('FAIL' if p > 300 else ('WARN' if p > 60 else 'PASS'))" 2>/dev/null)
    echo "  E2E latency P50:      ${P50_E:-N/A}s  [${E2E_P50_OK:-?}]"
    echo "  E2E latency P95:      ${P95_E:-N/A}s  [${E2E_P95_OK:-?}]"
  else
    echo "  E2E latency P50:      N/A"
    echo "  E2E latency P95:      N/A"
  fi
  echo ""
  echo "========================================================================"
  echo "  Report saved to: $REPORT"
  echo "========================================================================"

} > "$REPORT"
