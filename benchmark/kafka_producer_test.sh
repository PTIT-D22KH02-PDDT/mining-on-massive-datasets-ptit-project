#!/bin/bash
TOPIC=${1:-user-events}
NUM_RECORDS=${2:-500000}
RECORD_SIZE=${3:-1024}

TS=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="benchmark/results"
mkdir -p "$RESULTS_DIR"
LOG="${RESULTS_DIR}/kafka_producer_${TS}.log"

echo "=== Kafka Producer Benchmark $(date) ===" | tee -a "$LOG"
echo "Topic: $TOPIC, Records: $NUM_RECORDS, Size: $RECORD_SIZE" | tee -a "$LOG"

echo "--- acks=1 test ---" | tee -a "$LOG"
docker exec kafka bash -c "/opt/kafka/bin/kafka-producer-perf-test.sh \
  --topic '$TOPIC' \
  --num-records '$NUM_RECORDS' \
  --record-size '$RECORD_SIZE' \
  --throughput -1 \
  --producer-props bootstrap.servers=localhost:9092 acks=1 \
  2>&1 | tee -a "$LOG"

echo "" | tee -a "$LOG"
echo "--- acks=all test ---" | tee -a "$LOG"
docker exec kafka bash -c "/opt/kafka/bin/kafka-producer-perf-test.sh \
  --topic '$TOPIC' \
  --num-records 100000 \
  --record-size '$RECORD_SIZE' \
  --throughput -1 \
  --producer-props bootstrap.servers=localhost:9092 acks=all \
  2>&1 | tee -a "$LOG"

echo ""
echo "Done. Log: $LOG"
