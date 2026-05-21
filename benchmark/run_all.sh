#!/bin/bash
# run_all.sh - Chay toan bo benchmark tu dong
# Output: benchmark/results/report_<ts>.txt

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
echo "[1/6] Checking stack..." | tee -a "$SUMMARY_LOG"
docker compose -f "${BASE_DIR}/../docker-compose.dev.yml" ps > /dev/null 2>&1 || {
    echo "Stack not running. Start with: docker compose -f docker-compose.dev.yml up -d" | tee -a "$SUMMARY_LOG"
    exit 1
}

# Check k6
echo "[2/6] Checking k6..." | tee -a "$SUMMARY_LOG"
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
echo "[3/6] Phase 1: Baseline (30s)..." | tee -a "$SUMMARY_LOG"
${BASE_DIR}/log_resources.sh "${RESULTS_DIR}/baseline_${TS}.csv" 5 &
LOGGER_PID=$!
sleep 30
kill $LOGGER_PID 2>/dev/null || true

# Phase 2: Kafka producer benchmark
echo "[4/6] Phase 2: Kafka producer benchmark..." | tee -a "$SUMMARY_LOG"
${BASE_DIR}/log_resources.sh "${RESULTS_DIR}/during_kafka_${TS}.csv" 5 &
LOGGER_PID=$!
${BASE_DIR}/kafka_producer_test.sh user-events 200000 1024
kill $LOGGER_PID 2>/dev/null || true

# Phase 3: API load test
echo "[5/6] Phase 3: API load test (3 min)..." | tee -a "$SUMMARY_LOG"
${BASE_DIR}/log_resources.sh "${RESULTS_DIR}/during_api_${TS}.csv" 5 &
LOGGER_PID=$!
k6 run "${BASE_DIR}/loadtest.js" --out json="${RESULTS_DIR}/k6_results_${TS}.json"
kill $LOGGER_PID 2>/dev/null || true

# Phase 5: Generate report
echo "[6/6] Phase 5: Generating report..." | tee -a "$SUMMARY_LOG"
bash "${BASE_DIR}/report_generator.sh" "$RESULTS_DIR" 2>&1 | tee -a "$SUMMARY_LOG"

echo "" | tee -a "$SUMMARY_LOG"
echo "============================================" | tee -a "$SUMMARY_LOG"
echo " Benchmark complete!" | tee -a "$SUMMARY_LOG"
echo " Report: ${RESULTS_DIR}/report_*.txt" | tee -a "$SUMMARY_LOG"
echo " Raw data: ${RESULTS_DIR}/" | tee -a "$SUMMARY_LOG"
echo "============================================" | tee -a "$SUMMARY_LOG"
