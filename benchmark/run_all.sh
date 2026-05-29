#!/bin/bash
# run_all.sh - Chay toan bo benchmark tu dong
# Output: benchmark/results/<ts>_*.csv/json/log

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
RESULTS_DIR="${BASE_DIR}/results"
mkdir -p "$RESULTS_DIR"

TS=$(date +%Y%m%d_%H%M%S)
SUMMARY_LOG="${RESULTS_DIR}/run_summary_${TS}.log"
LOGGER_PID=""

cleanup() {
  if [ -n "$LOGGER_PID" ] && kill -0 "$LOGGER_PID" 2>/dev/null; then
    kill "$LOGGER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo "============================================" | tee -a "$SUMMARY_LOG"
echo " OTTO Benchmark Run - $(date)" | tee -a "$SUMMARY_LOG"
echo "============================================" | tee -a "$SUMMARY_LOG"

# Check stack
echo "[1/7] Checking stack..." | tee -a "$SUMMARY_LOG"
docker compose -f "${BASE_DIR}/../docker-compose.dev.yml" ps > /dev/null 2>&1 || {
    echo "Stack not running. Start with: docker compose -f docker-compose.dev.yml up -d" | tee -a "$SUMMARY_LOG"
    exit 1
}

# Check k6
echo "[2/7] Checking k6..." | tee -a "$SUMMARY_LOG"
if ! command -v k6 > /dev/null 2>&1; then
    if [ -x "${BASE_DIR}/k6" ]; then
        export PATH="${BASE_DIR}:${PATH}"
        echo "Using local k6 binary" | tee -a "$SUMMARY_LOG"
    else
        echo "k6 not found. Run: ${BASE_DIR}/install_k6.sh" | tee -a "$SUMMARY_LOG"
        exit 1
    fi
fi

# Phase 1: Baseline
echo "[3/7] Phase 1: Baseline (30s)..." | tee -a "$SUMMARY_LOG"
${BASE_DIR}/log_resources.sh "${RESULTS_DIR}/baseline_${TS}.csv" 5 &
LOGGER_PID=$!
sleep 30
kill $LOGGER_PID 2>/dev/null || true

# Phase 2: Kafka producer benchmark
echo "[4/7] Phase 2: Kafka producer benchmark..." | tee -a "$SUMMARY_LOG"
${BASE_DIR}/log_resources.sh "${RESULTS_DIR}/during_kafka_${TS}.csv" 5 &
LOGGER_PID=$!
${BASE_DIR}/kafka_producer_test.sh user-events 200000 1024
kill $LOGGER_PID 2>/dev/null || true

# Phase 3: API load test
echo "[5/7] Phase 3: API load test (3 min)..." | tee -a "$SUMMARY_LOG"
${BASE_DIR}/log_resources.sh "${RESULTS_DIR}/during_api_${TS}.csv" 5 &
LOGGER_PID=$!
k6 run "${BASE_DIR}/loadtest.js" \
  -e RESULTS_DIR="${RESULTS_DIR}" \
  -e BENCHMARK_TS="${TS}" \
  --out json="${RESULTS_DIR}/k6_results_${TS}.json"
kill $LOGGER_PID 2>/dev/null || true

# Phase 4: Export DB metrics to JSON files on host
echo "[6/7] Phase 4: Exporting DB metrics..." | tee -a "$SUMMARY_LOG"
DB_JSON="${RESULTS_DIR}/db_metrics_${TS}.json"
docker exec otto-api python3 -c "
import psycopg2, os, json

conn = psycopg2.connect(
    host=os.getenv('POSTGRES_HOST', 'postgres'),
    port=int(os.getenv('POSTGRES_PORT', 5432)),
    dbname=os.getenv('POSTGRES_DB', 'otto_recommender'),
    user=os.getenv('POSTGRES_USER', 'otto'),
    password=os.getenv('POSTGRES_PASSWORD', 'otto123')
)
cur = conn.cursor()
tables = ['spark_metrics', 'collected_events', 'predictions_log', 'popular_items', 'stats_hourly', 'anomaly_logs', 'stats_items', 'stats_sessions']
result = {}
for table in tables:
    try:
        cur.execute('SELECT * FROM ' + table)
        rows = cur.fetchall()
        colnames = [desc[0] for desc in cur.description]
        data = [dict(zip(colnames, row)) for row in rows]
        result[table] = {'rows': len(data), 'data': data}
    except Exception as e:
        result[table] = {'rows': 0, 'error': str(e)}
        print(f'  {table}: ERROR - {e}')
conn.close()
print(json.dumps(result, default=str))
" 2>&1 > "${DB_JSON}.tmp" && mv "${DB_JSON}.tmp" "$DB_JSON"
# Split into per-table files
python3 -c "
import json, os
with open('${DB_JSON}') as f:
    data = json.load(f)
out_dir = '${RESULTS_DIR}'
for table, tbl_data in data.items():
    fpath = os.path.join(out_dir, f'{table}_${TS}.json')
    with open(fpath, 'w') as f:
        json.dump(tbl_data, f, indent=2, default=str)
    print(f'  {table}: {tbl_data.get(\"rows\",0)} rows -> {fpath}')
" 2>&1 | tee -a "$SUMMARY_LOG"

# Phase 5: Generate report
echo "[7/7] Phase 5: Generating report..." | tee -a "$SUMMARY_LOG"
bash "${BASE_DIR}/report_generator.sh" "$RESULTS_DIR" 2>&1 | tee -a "$SUMMARY_LOG"

echo "" | tee -a "$SUMMARY_LOG"
echo "============================================" | tee -a "$SUMMARY_LOG"
echo " Benchmark complete!" | tee -a "$SUMMARY_LOG"
echo " Report: ${RESULTS_DIR}/report_*.txt" | tee -a "$SUMMARY_LOG"
echo " Raw data: ${RESULTS_DIR}/" | tee -a "$SUMMARY_LOG"
echo "============================================" | tee -a "$SUMMARY_LOG"
