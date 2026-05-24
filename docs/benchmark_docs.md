# Benchmark Documentation -- OTTO Recommender Pipeline

**Ngày:** 2026-05-21
**Phiên bản:** v1
**Phạm vi:** Đo throughput, latency, stability, và resource utilization của toàn bộ pipeline.

---

## 1. Tổng Quan

### 1.1 Mục đích

Benchmark này được thiết kế để:

1. **Xác định capacity** của từng tier trong pipeline (Kafka, API, Spark, PostgreSQL, Redis)
2. **Phát hiện bottleneck** trước khi chúng ảnh hưởng đến production
3. **Thiết lập SLA** (Service Level Agreement) cơ sở cho từng thành phần
4. **Làm cơ sở** để đánh giá tác động của các improvement trong tương lai

### 1.2 Kiến trúc hệ thống (các tier được test)

```
Client (k6/curl)
    |
    v
API (FastAPI :8000) -----> Kafka (user-events topic)
    |                           |
    v                           v
Redis (session/cache)      Spark Streaming (micro-batch)
                                |
                                v
                           PostgreSQL (persistence)
                                |
                                v
                           Dashboard (Streamlit :8501)
```

| Tier | Công nghệ | Vai trò | Rủi ro khi không benchmark |
|------|-----------|---------|---------------------------|
| 1 | Kafka | Message broker | Mất message, consumer lag, OOM broker |
| 2 | Spark Streaming | Stream processing | Backpressure, checkpoint corruption, mất dữ liệu |
| 3 | FastAPI | Recommendation API | Timeout, circuit breaker cascade, connection pool exhaustion |
| 4 | PostgreSQL | Data persistence | Slow query, connection saturation, đầy disk |
| 5 | Redis | Session + cache | Memory exhaustion, eviction của active sessions |

### 1.3 Các loại test

| Loại test | Dùng để phát hiện | Ví dụ |
|-----------|------------------|-------|
| Load test | Performance dưới tải kỳ vọng | 100 req/s trong 5 phút |
| Stress test | Điểm gãy của hệ thống | Tăng dần req/s đến khi hệ thống gãy |
| Soak test | Memory leak, degradation theo thời gian | 50 req/s trong 30 phút |
| Spike test | Khả năng recovery sau burst đột ngột | 10 -> 200 req/s ngay lập tức |

Trong đợt benchmark này, chúng ta tập trung vào **load test** và **stress test**.

---

## 2. KPIs và SLAs

### 2.1 Định nghĩa KPI

| KPI | Công thức | Đơn vị | Giải thích |
|-----|-----------|--------|------------|
| Throughput | Số request thành công / đơn vị thời gian | req/s hoặc msg/s | Khả năng xử lý của hệ thống |
| P50 latency | Median thời gian response | ms | Trải nghiệm người dùng thông thường |
| P95 latency | 95% requests có response nhanh hơn giá trị này | ms | SLA chính cho production |
| P99 latency | 99% requests có response nhanh hơn giá trị này | ms | Khả năng chịu tail latency |
| Error rate | Số request lỗi / tổng số request | % | Độ tin cậy của hệ thống |
| Stability ratio | Spark processing time / batch interval | ratio | Khả năng theo kịp input của Spark |
| E2E latency | Thời gian từ event -> dashboard hiển thị | s | Data freshness |

### 2.2 SLA Targets

| Metric | Good [OK] | Warning [WARN] | Critical [FAIL] | Ghi chú |
|--------|-----------|----------------|-----------------|---------|
| API P50 latency | <100ms | <200ms | >500ms | Đo bằng k6 |
| API P95 latency | <200ms | <500ms | >1s | |
| API P99 latency | <500ms | <2s | >5s | |
| API throughput | >100 req/s | >50 req/s | <10 req/s | Với 50 concurrent users |
| API error rate | <0.1% | <1% | >5% | Status != 200 |
| Kafka producer TPS | >200K msg/s | >100K msg/s | <50K msg/s | Record-size 1KB, acks=1 |
| Kafka producer P95 latency | <500ms | <5s | >5s | |
| Kafka consumer TPS | >100K msg/s | >50K msg/s | <20K msg/s | |
| Spark stability ratio | <0.5 | <0.8 | >1.0 | processing_time / batch_interval |
| Spark batch duration | <5s | <8s | >10s | Với trigger interval 5-10s |
| E2E P50 latency | <10s | <30s | >60s | Từ API call -> DB insert |
| E2E P95 latency | <30s | <60s | >5 phút | |
| CPU utilization | <50% | <80% | >90% | Per container |
| Memory utilization | <60% | <80% | >90% | Per container |

### 2.3 Tại sao chọn các SLA này

**API latency:**
- FastAPI async + sync DB calls -> latency <200ms P95 là khả thi nếu không có circuit breaker timeout.
- P99 >2s cho thấy có vấn đề về connection pool, DB query, hoặc SASRec remote call timeout.

**Kafka throughput:**
- Kafka 4.x có thể đạt >1M msg/s / broker trong điều kiện tối ưu.
- Với containerized deployment (resource-limited), 200K msg/s là target thực tế.

**Spark stability:**
- Nếu processing_time > batch_interval, backlog tăng dần -> memory exhaustion -> container OOM kill.
- Đây là nguyên nhân số 1 gây mất dữ liệu trong streaming pipeline (theo HPE Telecom case study).

---

## 3. Setup

### 3.1 Tools cần cài đặt

```bash
# k6 (Grafana) - load testing tool
wget -q https://github.com/grafana/k6/releases/latest/download/k6-linux-amd64.tar.gz
tar xzf k6-linux-amd64.tar.gz
sudo mv k6-v*/k6 /usr/local/bin/
rm -rf k6-*

# Kiem tra
k6 version
```

### 3.2 File structure

```
benchmark/
├── curl-format.txt          # Format output cho curl timing
├── loadtest.js              # K6 test script
├── kafka_producer_test.sh   # Kafka producer benchmark
├── kafka_consumer_test.sh   # Kafka consumer benchmark
├── e2e_latency.sql          # SQL query do E2E latency
├── report_generator.sh      # Sinh report tu raw data
└── results/                 # Output directory (auto-created)
    ├── k6_results_<ts>.json
    ├── docker_stats_<ts>.csv
    ├── kafka_producer_<ts>.log
    └── report_<ts>.txt
```

### 3.3 Tạo file curl-format.txt

```bash
cat > benchmark/curl-format.txt << 'EOF'
    time_namelookup:  %{time_namelookup}s
       time_connect:  %{time_connect}s
    time_appconnect:  %{time_appconnect}s
   time_pretransfer:  %{time_pretransfer}s
      time_redirect:  %{time_redirect}s
 time_starttransfer:  %{time_starttransfer}s
    time_total:      %{time_total}s
EOF
```

### 3.4 Kiểm tra stack sẵn sàng

```bash
# Tat ca services dang up
docker compose -f docker-compose.dev.yml ps

# API health check
curl -s http://localhost:8000/api/health | python3 -m json.tool

# Kafka ready
docker exec kafka kafka-broker-api-versions.sh --bootstrap-server localhost:9092 > /dev/null && echo "Kafka OK"
```

### 3.5 Tổ chức chạy benchmark

Mở **3 terminal** song song:

| Terminal | Vai trò | Lệnh chạy |
|----------|---------|-----------|
| 1 | Resource monitor | `docker stats` -> file CSV |
| 2 | Test runner | `k6` hoặc `kafka-perf-test` |
| 3 | DB monitor | `watch` query `spark_metrics` |

---

## 4. Phase 1: Baseline (5 phút)

**Làm gì:** Ghi lại resource utilization và latency khi hệ thống ở trạng thái idle (không có load).

**Tại sao:** Baseline là điểm tham chiếu để so sánh khi có load. Nếu CPU ở idle đã >50%, có thể có leak hoặc service khác đang conflict resource.

**Tác động:** Không có. Đây là thông số tham chiếu.

### 4.1 Các bước thực hiện

```bash
# Terminal 1: Ghi docker stats baseline trong 2 phút
mkdir -p benchmark/results
TS=$(date +%Y%m%d_%H%M%S)

echo "=== BASELINE $(date) ===" > benchmark/results/baseline_${TS}.txt
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" >> benchmark/results/baseline_${TS}.txt

for i in $(seq 12); do
  docker stats --no-stream --format "{{.Name}},{{.CPUPerc}},{{.MemUsage}},{{.NetIO}}" \
    >> benchmark/results/baseline_${TS}.csv
  sleep 10
done
```

### 4.2 Ghi lại kết quả

```bash
# API single request latency
curl -w "@benchmark/curl-format.txt" -s -o /dev/null http://localhost:8000/api/health >> benchmark/results/baseline_${TS}.txt

# Spark idle
docker exec otto-postgres psql -U otto -d otto_recommender \
  -c "SELECT NOW() - MAX(created_at) AS last_batch_ago, COUNT(*) AS total_batches FROM spark_metrics;" \
  >> benchmark/results/baseline_${TS}.txt
```

---

## 5. Phase 2: Kafka Throughput (10 phút)

**Làm gì:** Đo throughput và latency của Kafka broker khi produce và consume messages.

**Tại sao:** Kafka là backbone của pipeline. Nếu Kafka không theo kịp input rate, toàn bộ downstream (Spark, DB) bị ảnh hưởng. Theo Intel benchmark methodology, đây là bước đầu tiên trước khi test bất kỳ streaming application nào.

**Tác động:** Tạo ~500K messages trên topic `user-events`. Consumer (Spark streaming) sẽ đọc các messages này, gây tăng CPU và memory cho Spark container.

### 5.1 Producer benchmark

```bash
cat > benchmark/kafka_producer_test.sh << 'SHSCRIPT'
#!/bin/bash
TOPIC=${1:-user-events}
NUM_RECORDS=${2:-500000}
RECORD_SIZE=${3:-1024}

TS=$(date +%Y%m%d_%H%M%S)
LOG="benchmark/results/kafka_producer_${TS}.log"

echo "=== Kafka Producer Benchmark $(date) ===" | tee -a "$LOG"
echo "Topic: $TOPIC, Records: $NUM_RECORDS, Size: $RECORD_SIZE" | tee -a "$LOG"

docker exec kafka kafka-producer-perf-test.sh \
  --topic "$TOPIC" \
  --num-records "$NUM_RECORDS" \
  --record-size "$RECORD_SIZE" \
  --throughput -1 \
  --producer-props bootstrap.servers=localhost:9092 acks=1 \
  --warmup-records 50000 2>&1 | tee -a "$LOG"

echo "--- acks=all test ---" | tee -a "$LOG"
docker exec kafka kafka-producer-perf-test.sh \
  --topic "$TOPIC" \
  --num-records 100000 \
  --record-size "$RECORD_SIZE" \
  --throughput -1 \
  --producer-props bootstrap.servers=localhost:9092 acks=all \
  --warmup-records 10000 2>&1 | tee -a "$LOG"

echo "Done: $LOG"
SHSCRIPT
chmod +x benchmark/kafka_producer_test.sh
```

### 5.2 Consumer benchmark

```bash
cat > benchmark/kafka_consumer_test.sh << 'SHSCRIPT'
#!/bin/bash
TOPIC=${1:-user-events}
MESSAGES=${2:-200000}
TIMEOUT=${3:-60000}

TS=$(date +%Y%m%d_%H%M%S)
LOG="benchmark/results/kafka_consumer_${TS}.log"

echo "=== Kafka Consumer Benchmark $(date) ===" | tee -a "$LOG"
echo "Topic: $TOPIC, Messages: $MESSAGES, Timeout: ${TIMEOUT}ms" | tee -a "$LOG"

docker exec kafka kafka-consumer-perf-test.sh \
  --bootstrap-server localhost:9092 \
  --topic "$TOPIC" \
  --messages "$MESSAGES" \
  --timeout "$TIMEOUT" 2>&1 | tee -a "$LOG"

echo "Done: $LOG"
SHSCRIPT
chmod +x benchmark/kafka_consumer_test.sh
```

### 5.3 Cách chạy

```bash
# Terminal 1: Resource monitoring
docker stats --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"  # watch mode

# Terminal 2: Producer benchmark
./benchmark/kafka_producer_test.sh user-events 500000 1024

# Sau do consumer benchmark
./benchmark/kafka_consumer_test.sh user-events 200000
```

### 5.4 Giải thích kết quả

Output mẫu:
```
500000 records sent, 247524.752475 records/sec (241.72 MB/sec), average latency: 1.8 ms, max latency: 45.0 ms.
```

Đọc kết quả:
- **Records/sec**: Throughput. So với SLA: >200K/s là [OK], <100K/s là [WARN]
- **Avg latency**: Thời gian trung bình để Kafka broker xác nhận ghi. <5ms là [OK]
- **Max latency**: Tail latency. <100ms là [OK], >500ms cần kiểm tra disk I/O
- **acks=1 vs acks=all**: `acks=all` đảm bảo dữ liệu được replicate sang tất cả replicas trước khi ack -> throughput thấp hơn nhưng an toàn hơn

---

## 6. Phase 3: API Load Test (15 phút)

**Làm gì:** Đo API latency và throughput dưới các mức tải khác nhau (10, 50, 100 concurrent users).

**Tại sao:** Đây là KPI chính dành cho người dùng cuối. API xử lý recommendation request, gọi SASRec remote, ghi vào Redis và Kafka. Bottleneck thường gặp: circuit breaker mở, connection pool cạn, SASRec timeout, Redis memory exhaustion.

**Tác động:** Tạo events vào Kafka, ghi vào Redis session, kích hoạt Spark streaming processing. Có thể làm tăng consumer lag (nếu Spark không theo kịp).

### 6.1 K6 test script

```javascript
// benchmark/loadtest.js
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate } from 'k6/metrics';

const BASE_URL = 'http://localhost:8000';
const sessionPool = Array.from({length: 2000}, (_, i) => 100000 + i);
const eventTypes = ['clicks', 'carts', 'orders'];

const apiLatency = new Trend('api_latency');
const errorRate = new Rate('api_errors');

export const options = {
  stages: [
    { duration: '3m', target: 10 },     // Warm-up: thiet lap connections
    { duration: '3m', target: 50 },     // Medium load: typical production
    { duration: '3m', target: 100 },    // Heavy load: stress test
    { duration: '2m', target: 0 },      // Ramp-down: kiem tra recovery
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],   // P95 < 500ms
    http_req_failed: ['rate<0.01'],     // Error rate < 1%
  },
};

export default function () {
  const sessionId = sessionPool[Math.floor(Math.random() * sessionPool.length)];
  const eventType = eventTypes[Math.floor(Math.random() * 3)];
  const payload = JSON.stringify({
    session_id: sessionId,
    aid: Math.floor(Math.random() * 1850000),
    type: eventType,
  });

  const res = http.post(`${BASE_URL}/api/event`, payload, {
    headers: { 'Content-Type': 'application/json' },
    timeout: '10s',
  });

  apiLatency.add(res.timings.duration);
  check(res, { 'status 200': (r) => r.status === 200 }) || errorRate.add(1);

  // Random think time: 300ms - 1300ms
  sleep(Math.random() * 1 + 0.3);
}
```

### 6.2 Giải thích script

| Component | Giải thích |
|-----------|------------|
| `stages` | Tăng dần tải để tránh shock cho hệ thống, giống kiểu "warm-up" của Intel benchmark |
| `sessionPool: 2000` | 2000 session IDs khác nhau để tránh Redis hotspot contention |
| `eventTypes: random` | Phân bố event type giống production: chủ yếu clicks, ít carts/orders |
| `timeout: 10s` | Tránh request bị treo mãi (SASRec remote call có thể timeout) |
| `sleep(0.3-1.3)` | Simulate user think time, không spam API ở tốc độ tối đa |
| `thresholds` | k6 tự động FAIL nếu SLA bị vi phạm |

### 6.3 Cách chạy

```bash
# Terminal 1: Docker stats log
TS=$(date +%Y%m%d_%H%M%S)
echo "timestamp,name,cpu,mem,net_in,net_out" > benchmark/results/docker_stats_${TS}.csv
for i in $(seq 180); do
  docker stats --no-stream --format "{{.Name}},{{.CPUPerc}},{{.MemUsage}},{{.NetIO}}" \
    | while read line; do
      echo "$(date +%H:%M:%S),$line" >> benchmark/results/docker_stats_${TS}.csv
    done
  sleep 5
done &

# Terminal 2: Spark monitoring
watch -n 10 'docker exec otto-postgres psql -U otto -d otto_recommender \
  -c "SELECT id, batch_duration_ms, input_rows_per_second, \
      ROUND(batch_duration_ms::numeric / 10000, 2) AS stability
      FROM spark_metrics ORDER BY id DESC LIMIT 5;"'

# Terminal 3: Run k6
k6 run benchmark/loadtest.js --out json=benchmark/results/k6_results_${TS}.json
```

### 6.4 Giải thích kết quả

k6 output mẫu:
```
    http_req_duration..........: avg=45.2ms  min=3.1ms  med=38.5ms  max=1250ms
      { expected_response:true }........: avg=45.2ms  min=3.1ms  med=38.5ms  max=1250ms
    http_req_failed............: 0.12%  ✓ 12  ✗ 9846
    api_latency................: avg=45.2ms  min=3.1ms  med=38.5ms  max=1250ms
    api_errors.................: 0.12%  ✓ 12  ✗ 9846
```

Đọc kết quả:
- **avg latency**: 45.2ms -> [OK] (SLA <200ms)
- **P95 latency**: k6 tự động report. Nếu <200ms -> [OK], 200-500ms -> [WARN]
- **Error rate**: 0.12% -> [OK] (SLA <1%)
- **Max latency**: 1250ms -> [WARN] cần kiểm tra (có thể do SASRec circuit breaker mở)

Phân tích từng stage:
- Stage 1 (10 users, 0-3 phút): Latency thấp nhất, error rate ~0%
- Stage 2 (50 users, 3-6 phút): Latency bắt đầu tăng, kiểm tra database connection pool
- Stage 3 (100 users, 6-9 phút): Đây là stress test. Nếu error rate tăng đột biến -> bottleneck
- Stage 4 (ramp-down, 9-11 phút): Kiểm tra hệ thống có recover về baseline không

---

## 7. Phase 4: Spark Streaming Stability (trong lúc chạy load test)

**Làm gì:** Đo Spark processing time và so sánh với batch interval để tính stability ratio.

**Tại sao:** Theo HPE Telecom và Intel, Spark streaming chỉ ổn định khi processing_time <= batch_interval. Nếu processing_time > batch_interval, backlog tăng dần, cuối cùng dẫn đến OOM hoặc checkpoint corruption. Đây là bug nguy hiểm nhất trong streaming pipeline.

**Tác động:** Chỉ đọc từ DB, không tác động đến pipeline.

### 7.1 Stability analysis

```sql
-- benchmark/e2e_latency.sql
WITH spark_stats AS (
  SELECT
    batch_duration_ms,
    input_rows_per_second,
    process_rows_per_second,
    timestamp,
    ROUND(batch_duration_ms::numeric / 10000, 2) AS stability_ratio
  FROM spark_metrics
  WHERE timestamp > NOW() - INTERVAL '30 minutes'
)
SELECT
  COUNT(*) AS total_batches,
  ROUND(AVG(batch_duration_ms)) AS avg_batch_ms,
  ROUND(MAX(batch_duration_ms)) AS max_batch_ms,
  ROUND(AVG(stability_ratio), 2) AS avg_stability,
  ROUND(MAX(stability_ratio), 2) AS max_stability,
  ROUND(AVG(input_rows_per_second)) AS avg_input_rows_s,
  ROUND(AVG(process_rows_per_second)) AS avg_process_rows_s,
  CASE
    WHEN AVG(stability_ratio) < 0.5 THEN 'EXCELLENT'
    WHEN AVG(stability_ratio) < 0.8 THEN 'GOOD'
    WHEN AVG(stability_ratio) < 1.0 THEN 'WARNING'
    ELSE 'UNSTABLE'
  END AS verdict
FROM spark_stats;
```

### 7.2 Đọc kết quả

| avg_stability | Verdict | Ý nghĩa |
|---------------|---------|---------|
| < 0.5 | EXCELLENT | Spark dùng CPU < 50% của batch interval. Còn dư capacity |
| 0.5 - 0.8 | GOOD | Processing ổn. Còn dư capacity để xử lý các trận thiếu |
| 0.8 - 1.0 | WARNING | Gần nghẽn. Cần tăng batch interval hoặc Spark resources |
| > 1.0 | UNSTABLE | **Backpressure**. Spark không theo kịp. Sẽ mất dữ liệu nếu kéo dài |

### 7.3 Tại sao stability ratio quan trọng

Khi stability = 1.2 (processing mất 12s cho batch 10s):
- Batch 1: process 12s, batch 2 trễ 2s
- Batch 2: process 13s (nhiều input hơn vì backlog), batch 3 trễ 5s
- ...
- Sau N batches: backlog -> memory full -> Spark driver OOM -> container restart -> mất checkpoint -> mất dữ liệu

---

## 8. Phase 5: End-to-End Pipeline Latency (5 phút)

**Làm gì:** Đo thời gian từ lúc API nhận event -> dữ liệu được ghi vào PostgreSQL -> có thể query được.

**Tại sao:** Đây là KPI quan trọng nhất cho real-time dashboard. User gửi event, bao lâu sau dashboard hiển thị? E2E latency bao gồm: Kafka produce time + Spark batch interval + Spark processing time + DB insert + Streamlit auto-refresh.

**Tác động:** Chỉ đọc từ DB, không tác động.

### 8.1 E2E measurement script

```sql
-- benchmark/e2e_latency.sql
WITH e2e AS (
  SELECT
    created_at AS event_time,
    NOW() - created_at AS age,
    EXTRACT(EPOCH FROM (NOW() - created_at)) AS age_seconds
  FROM collected_events
  WHERE created_at > NOW() - INTERVAL '15 minutes'
)
SELECT
  COUNT(*) AS total_events,
  ROUND(AVG(age_seconds)) AS avg_seconds,
  ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY age_seconds)) AS p50_seconds,
  ROUND(PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY age_seconds)) AS p90_seconds,
  ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY age_seconds)) AS p95_seconds,
  ROUND(MAX(age_seconds)) AS max_seconds,
  CASE
    WHEN AVG(age_seconds) < 10 THEN 'REALTIME'
    WHEN AVG(age_seconds) < 30 THEN 'NEAR_REALTIME'
    WHEN AVG(age_seconds) < 60 THEN 'BATCH_LIKE'
    ELSE 'OFFLINE'
  END AS freshness_verdict
FROM e2e;
```

### 8.2 Các thành phần của E2E latency

```
API event -> Kafka produce -> Spark consume -> Spark process -> DB insert -> Streamlit refresh
 |                               |                  |              |               |
 | Kafka batch (linger.ms)       | 1 batch interval | processing   | DB write     | 5s auto-refresh
 ~1-5ms                          | 5-10s            | 5-10s        | ~1-5ms       | 0-5s
```

E2E latency ước tính: `Kafka_produce(5ms) + batch_interval(10s) + processing(5s) + DB(5ms) + Streamlit(2.5s avg) = ~17.5s`

**SLA:** P50 < 30s, P95 < 60s

### 8.3 Đọc kết quả

| freshness_verdict | Ý nghĩa |
|-------------------|---------|
| REALTIME | Dữ liệu được xử lý trong <10s. Lý tưởng cho dashboard |
| NEAR_REALTIME | Dữ liệu được xử lý trong 10-30s. Chấp nhận được |
| BATCH_LIKE | Dữ liệu được xử lý trong 30-60s. Cần kiểm tra Spark batch interval |
| OFFLINE | Dữ liệu trễ >60s. **Critical** -- Spark có thể đang bị backpressure |

---

## 9. Phase 6: Resource Utilization (trong suốt quá trình test)

**Làm gì:** Ghi lại CPU, memory, network của từng container trong suốt các phase test.

**Tại sao:** Bottleneck không phải lúc nào cũng là code. CPU saturation ở Kafka container, memory pressure ở Spark JVM, hoặc disk I/O ở PostgreSQL đều có thể gây degraded performance mà không có error log.

**Tác động:** `docker stats` gọi API của Docker daemon, chỉ tốn rất ít CPU (<0.1%).

### 9.1 Script ghi docker stats liên tục

```bash
cat > benchmark/log_resources.sh << 'SHSCRIPT'
#!/bin/bash
# Ghi docker stats vao CSV file, chay lien tuc den khi bi kill
OUTPUT="${1:-benchmark/results/docker_stats.csv}"
INTERVAL="${2:-5}"  # seconds

mkdir -p "$(dirname "$OUTPUT")"
echo "timestamp,name,cpu_percent,mem_usage,mem_percent,net_io" > "$OUTPUT"

while true; do
  docker stats --no-stream --format "{{.Name}},{{.CPUPerc}},{{.MemUsage}},{{.MemPerc}},{{.NetIO}}" \
    | while read line; do
      echo "$(date +%Y-%m-%d_%H:%M:%S),$line" >> "$OUTPUT"
    done
  sleep "$INTERVAL"
done
SHSCRIPT
chmod +x benchmark/log_resources.sh
```

### 9.2 Cách chạy

```bash
# Start logger (chay ngam)
./benchmark/log_resources.sh benchmark/results/stats_${TS}.csv 5 &
LOGGER_PID=$!

# ... chay cac test ...

# Cuoi cung, stop logger
kill $LOGGER_PID
```

### 9.3 Phân tích resource bottleneck

Khi có kết quả, tìm bottleneck bằng cách trả lời các câu hỏi:

| Triệu chứng | Bottleneck có thể | Check |
|-------------|------------------|-------|
| API latency cao nhưng CPU thấp | Connection pool exhaustion | `ss -s`, connection count |
| API latency cao, CPU > 80% | CPU-bound (tính toán, serialization) | flamegraph, profiling |
| Kafka latency cao | Disk I/O | `iostat -x 1` |
| Spark processing time tăng dần | Memory pressure (GC) | Spark UI GC time |
| PostgreSQL connection refused | Connection pool exhausted | `max_connections` config |
| Redis memory > 80% | Eviction của active sessions | `redis-cli info evicted_keys` |
| 2+ services CPU > 80% | Host resource contention | `htop`, host CPU/memory |

### 9.4 Công thức tính utilization

```bash
# Tu docker stats CSV, tinh avg CPU per service
cat benchmark/results/stats_${TS}.csv | \
  grep "otto-api" | \
  awk -F',' '{gsub(/%/,"",$3); sum+=$3; count++} END {printf "API avg CPU: %.1f%%\n", sum/count}'

# Peak CPU
cat benchmark/results/stats_${TS}.csv | \
  grep "otto-api" | \
  awk -F',' '{gsub(/%/,"",$3); if($3>max) max=$3} END {printf "API peak CPU: %.1f%%\n", max}'
```

---

## 10. Report Generator

**Làm gì:** Tự động tổng hợp kết quả từ các file raw thành một report text file.

**Tại sao:** Tránh manually copy-paste số liệu, đảm bảo tính nhất quán và tiết kiệm thời gian.

```bash
cat > benchmark/report_generator.sh << 'SHSCRIPT'
#!/bin/bash
# benchmark/report_generator.sh
# Usage: ./benchmark/report_generator.sh <results_dir>

RESULTS_DIR="${1:-benchmark/results}"
TS=$(date +%Y%m%d_%H%M%S)
REPORT="benchmark/results/report_${TS}.txt"

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

  # 4. API k6 metrics
  K6_RESULT=$(ls -t ${RESULTS_DIR}/k6_results_*.json 2>/dev/null | head -1)
  if [ -f "$K6_RESULT" ]; then
    echo "--- API LOAD TEST (k6) ---"
    # Trich xuat metrics tu k6 JSON output
    echo "Note: Run 'k6 run --summary-export=summary.json' de co detailed summary"
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
    echo "  No docker stats CSV found"
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
SHSCRIPT
chmod +x benchmark/report_generator.sh
```

### 10.1 Cách chạy report generator

```bash
# Sau khi hoan tat tat ca cac test
./benchmark/report_generator.sh benchmark/results
```

---

## 11. SLA Verdict Table (điền sau khi chạy benchmark)

| # | KPI | Target [OK] | Measured | Verdict |
|---|-----|-------------|----------|---------|
| 1 | API P50 latency | <100ms | | [PENDING] |
| 2 | API P95 latency | <200ms | | [PENDING] |
| 3 | API P99 latency | <500ms | | [PENDING] |
| 4 | API throughput (50 users) | >100 req/s | | [PENDING] |
| 5 | API error rate | <0.1% | | [PENDING] |
| 6 | Kafka producer TPS (acks=1) | >200K msg/s | | [PENDING] |
| 7 | Kafka producer P99 latency | <10ms | | [PENDING] |
| 8 | Kafka consumer TPS | >100K msg/s | | [PENDING] |
| 9 | Spark stability ratio | <0.8 | | [PENDING] |
| 10 | Spark avg batch duration | <5s | | [PENDING] |
| 11 | E2E latency P50 | <30s | | [PENDING] |
| 12 | E2E latency P95 | <60s | | [PENDING] |
| 13 | API container CPU avg | <50% | | [PENDING] |
| 14 | API container Memory | <60% | | [PENDING] |
| 15 | Kafka container CPU avg | <50% | | [PENDING] |
| 16 | Spark container CPU avg | <80% | | [PENDING] |
| 17 | PostgreSQL connections | <50 | | [PENDING] |
| 18 | Redis memory usage | <80% | | [PENDING] |

---

## 12. Tuning Recommendations (nếu SLA không đạt)

### 12.1 API latency cao

| Nguyên nhân | Khắc phục | File |
|-------------|-----------|------|
| SASRec remote timeout | Tăng `SASREC_TIMEOUT` hoặc cải thiện network | `src/api/main.py:83` |
| DB connection pool exhaustion | Tăng `pool_size` hoặc `pool_overflow` | `src/api/db.py` |
| Redis slow | Kiểm tra `redis-cli --latency`, tăng `maxmemory` | docker-compose.yml |

### 12.2 Spark unstable (stability > 0.8)

| Nguyên nhân | Khắc phục | File |
|-------------|-----------|------|
| Batch interval quá ngắn | Tăng trigger interval 5s -> 10s | `spark_streaming_job.py` |
| Spark executor memory thiếu | Tăng `spark.executor.memory` | `spark_streaming_job.py` |
| Quá nhiều shuffle partitions | Giảm `spark.sql.shuffle.partitions` | `spark_streaming_job.py` |

### 12.3 Kafka producer slow

| Nguyên nhân | Khắc phục | File |
|-------------|-----------|------|
| Disk I/O bottleneck | Kiểm tra `iostat`, sử dụng SSD | Hardware |
| `acks=all` quá chậm | Cân bằng consistency vs performance | Producer config |
| Batch size quá nhỏ | Tăng `linger.ms` và `batch.size` | Kafka producer config |

### 12.4 PostgreSQL query slow

| Nguyên nhân | Khắc phục | File |
|-------------|-----------|------|
| Thiếu index | Kiểm tra `pg_stat_user_indexes` | Migration SQL |
| Table quá lớn | Kiểm tra cleanup job (Phase 6.1) | `02_cleanup_old_data.sql` |
| Connection pool exhausted | Tăng `max_connections` hoặc dùng pgBouncer | docker-compose.yml |

---

## 13. Tham Khảo

- Intel Kafka Optimization Guide: `kafka-producer-perf-test` methodology, warmup records, SLA sweep testing
- HPE Telecom Case Study: Spark stability ratio, batch interval tuning, 12x speedup example
- LinkedIn Venice Benchmark: Multi-layer SLA prioritization (read SLA > write SLA)
- Databricks Streaming Benchmark: End-to-end latency measurement with source timestamp propagation
- Myntra Engineering: Production traffic replay, Gatling + Kafka protocol for load testing
- Dynatrace Research 2026: Latin Hypercube Sampling + Simulated Annealing for automated Kafka config tuning
- Apache Kafka Documentation: `kafka-producer-perf-test.sh`, `kafka-consumer-perf-test.sh`
- k6 Documentation: Stages, thresholds, custom metrics, JSON output
