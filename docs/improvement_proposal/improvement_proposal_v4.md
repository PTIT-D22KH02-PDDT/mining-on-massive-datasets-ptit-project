# Improvement Proposal v4 — Performance Optimization from Benchmark Results

**Date:** 2026-05-21

**Scope:** Cải thiện hiệu năng hệ thống dựa trên kết quả benchmark thực tế (2 lần chạy ngày 21/05/2026). Tập trung vào **API latency**, **Kafka bottleneck**, **Spark resource contention**, và **benchmark tooling**.

**Bối cảnh:** Benchmark cho thấy hệ thống hoạt động đúng (0% lỗi, pipeline Kafka→Spark→Postgres→Dashboard đầy đủ), nhưng có 3 vấn đề hiệu năng chính:
- API p95 latency ~4-7s (threshold mong muốn: 500ms)
- Kafka luôn ở 200% CPU (bão hòa 2-core limit)
- Spark streaming consume không kiểm soát, cạnh tranh tài nguyên với Kafka

---

## Phase 1: API Kafka Producer Optimization

### 1.1 Thêm Timeout + Config Cho AIOKafkaProducer

**File:** `src/core/infra/kafka.py` (dòng 58-83)

**Vấn đề:**

Hiện tại `KafkaProducerService.start()` hardcode `acks="all"`, `enable_idempotence=True` và không đọc các config khác từ `config/config.yml`:

```python
# src/core/infra/kafka.py:67-72
self._producer = AIOKafkaProducer(
    bootstrap_servers=self._bootstrap,
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    acks="all",
    enable_idempotence=True
)
```

Config đã định nghĩa trong `config/config.yml` (dòng 14-23) nhưng không được sử dụng:
```yaml
kafka:
  producer:
    acks: "all"
    retries: 3
    linger_ms: 10
    enable_idempotence: true
```

Hậu quả:
- **Không có `request_timeout_ms`**: nếu Kafka chậm, background task có thể chờ vô thời hạn
- **Không có `linger_ms`**: mỗi message được gửi ngay lập tức, không gom batch → tăng số request đến Kafka
- **`acks="all"` không cần thiết**: trên single-node Kafka, `acks=1` là đủ, `acks=all` chỉ thêm overhead chờ ISR confirm không cần thiết

**Tại sao cần cải thiện:**

Từ kết quả benchmark:
- API latency p95: 4.28s (lần 1) → 7.21s (lần 2)
- Mặc dù Kafka produce chạy trong background task (không block HTTP response), nhưng các background task chạy trên cùng event loop. Khi Kafka chậm, background tasks backlog, gây áp lực lên toàn bộ event loop
- 22.5 req/s (lần 1) → 10.5 req/s (lần 2) — throughput giảm 53% khi Kafka bão hòa

**Cách cải thiện:**

```python
# src/core/infra/kafka.py
import yaml
from pathlib import Path

def _load_producer_config():
    config_path = Path(__file__).parents[3] / "config/config.yml"
    if config_path.exists():
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        return cfg.get("kafka", {}).get("producer", {})
    return {}

class KafkaProducerService:
    async def start(self):
        if self._producer:
            return
        producer_cfg = _load_producer_config()
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            acks=producer_cfg.get("acks", "1"),
            enable_idempotence=producer_cfg.get("enable_idempotence", False),
            linger_ms=producer_cfg.get("linger_ms", 10),
            retries=producer_cfg.get("retries", 3),
            request_timeout_ms=producer_cfg.get("request_timeout_ms", 5000),
        )
        await self._producer.start()
```

**Tác động:**

| Metric | Trước | Sau (dự kiến) |
|--------|-------|---------------|
| API p95 latency | 4.28s | < 1s |
| API throughput | 22 req/s | > 40 req/s |
| Background task blocking | Không giới hạn (chờ Kafka) | Tối đa 5s (timeout) |
| Kafka request rate | 1 request/message (do linger_ms=0) | Gom batch (linger_ms=10ms) |

---

### 1.2 Thêm Producer Queue Riêng

**File mới:** `src/core/infra/kafka_queue.py`
**File sửa:** `src/api/main.py`

**Vấn đề:**

Hiện tại, mỗi request API tạo một background task gọi `_send_to_kafka` → `send_and_wait()`. Các background task này chạy trên cùng event loop với request handler. Khi Kafka chậm, background tasks chiếm event loop, làm chậm tất cả request khác:

```
Timeline:
  Request 1: → handler → add_task → response sent
  Request 2: → handler → add_task → response sent
  Event loop: [task1 kafka wait] [task2 kafka wait] [req3 handler wait] [req4 handler wait]
                                                                    ↑ req3 bị delay vì event loop busy
```

Kafka CPU ở 200% (bão hòa 2-core) làm trầm trọng thêm vấn đề này — mỗi `send_and_wait()` mất 2-7s.

**Tại sao cần cải thiện:**

Benchmark cho thấy median latency lần 1 chỉ 31ms (khi không có backlog) nhưng avg lên 854ms (khi backlog tích tụ). Đây là dấu hiệu của **convoy effect**: một background task chậm chặn các request khác.

**Cách cải thiện:**

Tách Kafka produce ra một queue riêng với dedicated worker:

```python
# src/core/infra/kafka_queue.py
import asyncio
from dataclasses import dataclass
from typing import Optional

@dataclass
class KafkaMessage:
    topic: str
    message: dict
    key: Optional[str] = None

class KafkaQueue:
    def __init__(self, producer_service, max_size=1000):
        self._producer = producer_service
        self._queue: asyncio.Queue[KafkaMessage] = asyncio.Queue(maxsize=max_size)
        self._worker_task: Optional[asyncio.Task] = None

    async def start(self):
        self._worker_task = asyncio.create_task(self._worker_loop())

    async def stop(self):
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def put(self, msg: KafkaMessage):
        """Non-blocking push to queue. Drop if queue full (graceful degradation)."""
        try:
            self._queue.put_nowait(msg)
        except asyncio.QueueFull:
            logger.warning("Kafka queue full, dropping message")

    async def _worker_loop(self):
        """Single worker: consume queue and produce to Kafka sequentially."""
        while True:
            msg = await self._queue.get()
            try:
                await self._producer.send(msg.topic, msg.message, key=msg.key)
            except Exception as e:
                logger.error(f"Kafka send failed (queued message dropped): {e}")
            finally:
                self._queue.task_done()
```

Trong API:
```python
# src/api/main.py — startup
kafka_queue = KafkaQueue(kafka_producer)
await kafka_queue.start()

# Trong event handler — thay vì background_tasks.add_task
await kafka_queue.put(KafkaMessage("user-events", payload, key=str(event.session_id)))
```

**Tác động:**

| Metric | Trước | Sau (dự kiến) |
|--------|-------|---------------|
| Event loop blocking | Có (background task chờ Kafka) | Không (queue.put là O(1)) |
| Graceful degradation | Không (task accumulate) | Có (queue đầy → drop message) |
| API throughput | 22 req/s | > 100 req/s (giới hạn bởi Redis/DB) |
| Message loss khi Kafka down | Background tasks lỗi + log | Buffer trong queue (có bound) |

**Rủi ro:** Worker là single point — nếu worker crash, messages trong queue bị mất. Có thể thêm retry + dead-letter queue sau này nếu cần.

---

## Phase 2: Kafka Broker Optimization

### 2.1 Tăng CPU Limit + JVM Tuning

**File:** `docker-compose.yml` (dòng 32-36)

**Vấn đề:**

Từ benchmark resource data:
- Kafka luôn ở ~200% CPU khi có tải (lần 1: 164-208%, lần 2: 190-207%)
- Memory: 926 MiB → 1.146 GiB (ổn, dưới limit 2 GiB)
- Kafka dùng heap default (-Xms1G -Xmx1G), không có JVM tuning

Docker stats trong baseline:
```
# Lần 1 baseline (chưa có tải): Kafka CPU ~12%, mem 926 MiB
# Lần 2 baseline (sau 1 lần benchmark): Kafka CPU ~89%, mem 938 MiB
#            ↑ khởi tạo cao vì chưa cleanup từ lần trước
```

**Tại sao cần cải thiện:**

Kafka 4.x trên single node cần CPU cho:
- Network threads (xử lý requests từ producer/consumer)
- I/O threads (ghi log segments, flush disk)
- GC (JVM garbage collection)
- Background tasks (log compaction, retention)

Với 2 cores và không có tuning, Kafka là bottleneck chính của toàn bộ pipeline.

**Cách cải thiện:**

```yaml
# docker-compose.yml — service kafka
kafka:
  image: docker.io/apache/kafka:4.1.1
  deploy:
    resources:
      limits:
        cpus: '4.0'
        memory: 4g
  environment:
    # ... existing configs ...
    - KAFKA_HEAP_OPTS=-Xms2G -Xmx2G
    - KAFKA_OPTS=-XX:+UseG1GC -XX:MaxGCPauseMillis=100 -Djava.net.preferIPv4Stack=true
    - KAFKA_CFG_NUM_IO_THREADS=8
    - KAFKA_CFG_NUM_NETWORK_THREADS=6
    - KAFKA_CFG_NUM_REPLICA_FETCHERS=2
    - KAFKA_CFG_LOG_FLUSH_INTERVAL_MESSAGES=10000
    - KAFKA_CFG_LOG_FLUSH_INTERVAL_MS=1000
    - KAFKA_CFG_LOG_SEGMENT_BYTES=536870912  # 512 MB segments
```

Giải thích các config:

| Config | Giá trị | Tác dụng |
|--------|---------|----------|
| `KAFKA_HEAP_OPTS` | `-Xms2G -Xmx2G` | Heap cố định 2G, tránh resize |
| `-XX:+UseG1GC` | G1GC | GC thấp latency, phù hợp Kafka |
| `-XX:MaxGCPauseMillis=100` | 100ms | Giới hạn GC pause |
| `num.io.threads` | 8 | Xử lý I/O song song (default 8, hiện tại không set) |
| `num.network.threads` | 6 | Xử lý network requests (default 3) |
| `num.replica.fetchers` | 2 | Fetch dữ liệu replication (trên single node không cần nhưng harmless) |
| `log.flush.interval.ms` | 1000ms | Flush log segments mỗi 1 giây (cân bằng giữa durability và I/O) |
| `log.segment.bytes` | 512 MB | Segment lớn hơn → ít file hơn → ít I/O overhead |

**Tác động:**

| Metric | Trước | Sau (dự kiến) |
|--------|-------|---------------|
| Kafka CPU usage | 200% (bão hòa) | < 150% (có headroom) |
| Kafka throughput | ~8 MB/s (producer test) | > 20 MB/s |
| GC pause time | Không rõ (default GC) | < 100ms (G1GC) |
| API produce latency | avg 3.3s | avg < 500ms |

---

### 2.2 Tăng Kafka Log Retention Cho Benchmark

**File:** `docker-compose.yml` — thêm vào service kafka environment

**Vấn đề:**

Lần benchmark thứ 2 cho thấy Kafka CPU baseline đã ở 89% vì:
- Data từ lần benchmark trước vẫn còn trong Kafka log
- Spark streaming vẫn đang consume catch-up
- Retention mặc định (7 ngày) giữ lại quá nhiều data cho môi trường dev

**Cách cải thiện:**

```yaml
- KAFKA_LOG_RETENTION_HOURS=2       # Giữ log tối đa 2 tiếng (dev)
- KAFKA_LOG_RETENTION_BYTES=-1       # Không giới hạn theo size (dùng time-based)
- KAFKA_LOG_SEGMENT_DELETE_DELAY_MS=10000  # Xóa segment sau 10s (default 60000)
```

**Tác động:**
- Kafka không accumulate data từ các lần chạy benchmark trước
- Giảm CPU/disk I/O cho log compaction
- Dev environment cleaner

---

## Phase 3: Spark Streaming Optimization

### 3.1 Thêm Trigger Interval (processingTime)

**File:** `src/streaming/spark_streaming_job.py` (dòng 568-572)

**Vấn đề:**

Hiện tại Spark streaming không có `.trigger()` → dùng default trigger: process micro-batches ngay khi batch trước hoàn thành (back-to-back):

```python
query = events_df.writeStream \
    .outputMode("update") \
    .queryName("Unified-OTTO-Streaming-Query") \
    .foreachBatch(unified_foreach_batch) \
    .start()
```

Hậu quả từ benchmark:
- Spark streaming CPU: 250-400% liên tục (dùng gần hết 4 cores)
- Spark consume Kafka không kiểm soát → Kafka phải serve consumer + producer cùng lúc
- Khi không có event mới, Spark vẫn poll Kafka liên tục (waste CPU)

```
Docker stats trong during_api:
22:54:37  Spark 330% | Kafka 95%
22:54:44  Spark 347% | Kafka 1%   (Kafka vừa gửi xong batch cho Spark)
22:54:52  Spark 367% | Kafka 70%  (Kafka đang produce cho API)
22:55:06  Spark 292% | Kafka 1%
22:55:13  Spark 368% | Kafka 2%
```
Dạng sóng: Spark và Kafka "giằng co" CPU.

**Tại sao cần cải thiện:**

Spark không cần xử lý realtime — batch 5-10 giây là chấp nhận được cho dashboard. Với trigger interval:
- Spark có thời gian "nghỉ" giữa các batch → giải phóng CPU cho Kafka
- Giảm CPU contention → Kafka produce nhanh hơn → API latency giảm
- Spark vẫn bắt kịp throughput (22 events/s) vì 10s batch = 220 events, xử lý trong <1s

**Cách cải thiện:**

```python
query = events_df.writeStream \
    .outputMode("update") \
    .trigger(processingTime="10 seconds") \
    .queryName("Unified-OTTO-Streaming-Query") \
    .foreachBatch(unified_foreach_batch) \
    .start()
```

**Tác động:**

| Metric | Trước | Sau (dự kiến) |
|--------|-------|---------------|
| Spark batch pattern | Back-to-back (liên tục) | 10s interval |
| Kafka CPU available | Cạnh tranh với Spark | ~30% thêm cho Kafka |
| API p95 latency | 4.28s | < 2s (Kafka có thêm CPU để produce) |
| Dashboard staleness | ~1-3s | ~10-15s (chấp nhận được) |
| Spark CPU average | ~300% | ~50-100% (chỉ chạy 1s mỗi 10s) |

**Rủi ro:** Nếu throughput > 5000 events/10s, Spark không kịp xử lý → cần điều chỉnh `maxOffsetsPerTrigger`. Với throughput hiện tại ~22 req/s, 10s batch = 220 events → an toàn.

---

### 3.2 Thêm maxOffsetsPerTrigger

**File:** `src/streaming/spark_streaming_job.py` (dòng 552-557)

**Vấn đề:**

Không có `maxOffsetsPerTrigger` → Spark consume tất cả available offsets mỗi micro-batch. Khi restart sau downtime hoặc benchmark, Spark consume hàng loạt data cũ, gây CPU spike:

```
during_kafka baseline:
22:59:59  Spark 257% — catch-up từ kafka producer test trước
23:00:15  Spark 277%
```

**Cách cải thiện:**

```python
raw_df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS) \
    .option("subscribe", KAFKA_TOPIC) \
    .option("startingOffsets", os.getenv("SPARK_STARTING_OFFSETS", "earliest")) \
    .option("maxOffsetsPerTrigger", os.getenv("SPARK_MAX_OFFSETS_PER_TRIGGER", "5000")) \
    .load()
```

**Tác động:**
- Giới hạn 5000 records/batch → tránh CPU spike khi catch-up
- Kết hợp với `trigger(processingTime="10s")` → max throughput ~500 events/s
- Với 22 req/s hiện tại, không bao giờ chạm limit này

---

## Phase 4: Benchmark Tooling

### 4.1 Reset Stack Trước Mỗi Lần Benchmark

**File:** `benchmark/run_all.sh`

**Vấn đề:**

Lần benchmark thứ 2 bị ảnh hưởng bởi trạng thái tồn đọng từ lần 1:
- Kafka CPU baseline: 89% (so với 12% ở lần 1)
- API median latency: 2.24s (so với 31ms ở lần 1)
- Throughput: 10.5 req/s (so với 22 req/s ở lần 1)

**Cách cải thiện:**

Thêm phase reset trước Phase 1:

```bash
# Phase 0: Reset stack
echo "[0/6] Resetting stack for clean state..." | tee -a "$SUMMARY_LOG"
docker compose -f "${BASE_DIR}/../docker-compose.dev.yml" restart kafka spark-streaming 2>/dev/null || true
sleep 15  # Đợi Kafka + Spark khởi động lại
```

**Tác động:**

| Metric | Trước | Sau |
|--------|-------|-----|
| Kết quả giữa các lần chạy | Không nhất quán (accumulated state) | Nhất quán (clean state) |
| Debug benchmark | Khó (biến "trạng thái trước đó") | Dễ (mỗi lần độc lập) |
| Thời gian benchmark | ~4 phút | ~4.5 phút (+15s reset) |

---

### 4.2 Tăng Benchmark Duration

**File:** `benchmark/loadtest.js` (dòng 13-17)

**Vấn đề:**

Hiện tại 3 phút — quá ngắn để quan sát steady-state behavior:
- Ramp-up chưa kịp ổn định thì đã ramp-down
- Không thấy được hệ thống behavior khi tải ổn định kéo dài
- Batch interval 10s của Spark (sau Phase 3) chỉ chạy ~18 lần trong 3 phút

**Cách cải thiện:**

```javascript
stages: [
  { duration: '2m', target: 30 },    // Ramp lên 30 VU
  { duration: '2m', target: 60 },    // Ramp lên 60 VU
  { duration: '1m', target: 80 },    // Ramp lên 80 VU
  { duration: '2m', target: 80 },    // Steady-state 80 VU (quan trọng nhất)
  { duration: '1m', target: 0 },     // Ramp về 0
],
```

Tổng: **8 phút** (thay vì 3 phút).

Lý do chọn 8 phút thay vì 11 phút như ban đầu:
- 2 phút steady-state đủ để Spark chạy ~12 batches (với 10s interval)
- Đủ để Kafka và API thể hiện behavior dưới tải ổn định
- Không quá dài (vẫn acceptable để chạy nhiều lần)

**Tác động:**

| Metric | Trước (3 phút) | Sau (8 phút) |
|--------|----------------|--------------|
| Ramp stages | 3 stages (30→80→0) | 5 stages (30→60→80→steady→0) |
| Steady-state | 0 phút | 2 phút |
| Spark batches | ~18 (với trigger 10s) | ~48 (đủ để thấy trend) |
| Total events sent | ~4,000 | ~10,000+ |
| Độ tin cậy kết quả | Trung bình | Cao |

---

### 4.3 Dọn Log Orphan + Fix Path

**File:** `benchmark/run_all.sh` (đã fix trong phiên)
**File:** `benchmark/kafka_producer_test.sh` (đã fix)
**File:** `benchmark/kafka_consumer_test.sh` (đã fix)
**File:** `benchmark/log_resources.sh` (đã fix)
**File:** `benchmark/report_generator.sh` (đã fix)

Đã hoàn thành trong phiên làm việc. Các thay đổi:
1. Thêm `trap cleanup EXIT INT TERM` trong `run_all.sh`
2. Sửa relative path → absolute path trong tất cả script benchmark
3. Dọn `benchmark/benchmark/results` (thư mục rác do sai path)

---

## Tổng Kết

### Roadmap

| Phase | Task | Effort | Impact | Phụ thuộc |
|-------|------|--------|--------|-----------|
| 1.1 | AIOKafkaProducer config | 30 phút | Cao (giảm latency) | Không |
| 1.2 | Kafka producer queue | 1-2 giờ | Cao (loại bỏ blocking) | 1.1 |
| 2.1 | Kafka CPU + JVM tuning | 15 phút | Cao (tăng throughput) | Restart container |
| 2.2 | Kafka log retention | 5 phút | Thấp (clean dev) | 2.1 |
| 3.1 | Spark trigger interval | 5 phút | Cao (giảm CPU contention) | Restart Spark |
| 3.2 | Spark maxOffsetsPerTrigger | 5 phút | Trung bình (chống CPU spike) | 3.1 |
| 4.1 | Benchmark reset phase | 10 phút | Trung bình (kết quả nhất quán) | Không |
| 4.2 | Tăng benchmark duration | 5 phút | Thấp (kết quả đáng tin cậy hơn) | Không |

### Expected Results Sau Khi Implement

| Benchmark Metric | Trước | Mục tiêu |
|-----------------|-------|----------|
| API p95 latency | 4.28s | < 500ms |
| API error rate | 0% | 0% (giữ nguyên) |
| API throughput | 22 req/s | > 50 req/s |
| Kafka CPU | 200% (bão hòa) | < 120% |
| Kafka throughput | 8 MB/s | > 20 MB/s |
| Spark CPU avg | ~300% | ~80% (với trigger 10s) |

### Implementation Order Đề Xuất

```
Phase 1.1 → Phase 2.1 → Phase 3.1 → Phase 4.1 → 4.2 → Benchmark
  (config)     (CPU+JVM)   (trigger)   (reset)    (duration)
                                        ↓
                                Chạy benchmark
                                        ↓
                            Đánh giá kết quả → nếu cần → Phase 1.2 (queue)
```

Phase 1.2 (producer queue) là thay đổi kiến trúc lớn nhất, nên làm sau khi đã tuning các config đơn giản và đánh giá lại benchmark. Có thể không cần queue nếu tuning đủ.

---

## Tham Khảo

- `benchmark/results/benchmark_analysis_225914.md` — Phân tích chi tiết kết quả benchmark
- `benchmark/results/benchmark_report_20260521_225325.md` — Báo cáo benchmark lần 1
- `docs/improvement_proposal/improvement_proposal_v3.md` — Phase 6-9 (data retention, infra, dashboard)
- `docs/improvement_proposal/improvement_proposal_v2.md` — Phase 1-5 (streaming, API, anomaly)
- `src/core/infra/kafka.py` — Kafka producer service (cần sửa)
- `src/streaming/spark_streaming_job.py` — Spark streaming job (cần sửa)
- `docker-compose.yml` — Resource limits + Kafka config (cần sửa)

---

## Changelog

| Version | Date | Description |
|---------|------|-------------|
| v1 | 2026-05-17 | Docker optimization proposal |
| v2 | 2026-05-17 | Phase 1-5: Streaming, API, Anomaly, Dashboard, Evaluation |
| v3 | 2026-05-20 | Phase 6-9: Data retention, Infrastructure, Dashboard polish |
| v4 | 2026-05-21 | Phase 1-4 (v4): Performance optimization từ benchmark results |
