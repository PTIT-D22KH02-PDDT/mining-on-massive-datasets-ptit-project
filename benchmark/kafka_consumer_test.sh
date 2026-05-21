#!/bin/bash
TOPIC=${1:-user-events}
MESSAGES=${2:-200000}
TIMEOUT=${3:-60000}

TS=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="benchmark/results"
mkdir -p "$RESULTS_DIR"
LOG="${RESULTS_DIR}/kafka_consumer_${TS}.log"

echo "=== Kafka Consumer Benchmark $(date) ===" | tee -a "$LOG"
echo "Topic: $TOPIC, Messages: $MESSAGES, Timeout: ${TIMEOUT}ms" | tee -a "$LOG"

docker exec kafka bash -c "/opt/kafka/bin/kafka-consumer-perf-test.sh \
  --bootstrap-server localhost:9092 \
  --topic '$TOPIC' \
  --messages '$MESSAGES' \
  --timeout '$TIMEOUT'" 2>&1 | tee -a "$LOG"

echo ""
echo "Done. Log: $LOG"
