# Benchmark Run v2 vs v1 — Comparison Analysis

- v1: 2026-05-22 14:55 (baseline, pre-tuning)
- v2: 2026-05-22 22:12 (post-tuning: CPU limits + trigger + Kafka tune + merged aggregations)

---

## 1. Tổng quan thay đổi giữa v1 → v2

| # | Thay đổi | Target |
|---|----------|--------|
| 1 | CPU limits: Spark `cpus=4→2`, Kafka `cpus=2`, API `cpus=2` | Giảm contention |
| 3 | Spark trigger: thêm `.trigger(processingTime='30s')` | Batch ổn định |
| 5 | Kafka tune: `num.io.threads=8`, `num.network.threads=4` | Kafka TPS > 10K |
| 8 | Merge aggregations C+D, thêm `batch_df.cache()` | Batch duration < 10s |

---

## 2. Kết quả API Latency

### So sánh

| Metric | v1 | v2 | Delta |
|--------|----|----|-------|
| Requests | 3,993 | 4,148 | +3.9% |
| RPS | 22.03 | 22.95 | +4.2% |
| avg | 873ms | 818ms | **-6.3%** |
| med | 114ms | 126ms | +10.5% |
| p90 | 3,295ms | 3,574ms | +8.5% |
| **p95** | **4,485ms** | **4,952ms** | **+10.4%** |
| max | 6,184ms | 6,469ms | +4.6% |
| error rate | 0% | 0% | — |
| SLA p95<500ms | FAIL | FAIL | — |

### Hiện tượng

- p95 tăng nhẹ (+10%), không đạt SLA.
- Median tăng nhẹ (114→126ms), có thể do CPU limit Spark giảm → Kafka queue dài hơn → API chờ lâu hơn khi flush batch.
- avg giảm (-6%) do nhiều request nhanh đầu test hơn.

### Nguyên nhân

1. **Spark CPU giảm** (4→2) khiến batch kéo dài → Kafka queue tích tụ → Redis buffer tăng → API latency bị ảnh hưởng gián tiếp.
3. **Kafka throughput giảm 30%** (xem mục 3) → event handler (`kafka_queue.put_nowait()`) chờ lâu hơn.

### Giải pháp

- **Kafka restore**: cần giải quyết Kafka regression trước (mục 3).

---

## 3. Kết quả Kafka Producer

### So sánh

| Metric | v1 | v2 | Delta |
|--------|----|----|-------|
| Records | 200,000 | 200,000 | — |
| **TPS** | **5,264.8** | **3,669.7** | **-30.3%** |
| avg latency | 5,221ms | 7,280ms | **+39.4%** |
| p50 | 3,912ms | 6,147ms | **+57.1%** |
| p95 | 9,893ms | 11,828ms | +19.6% |
| max | 10,887ms | 12,836ms | +17.9% |
| SLA TPS > 5000 | PASS | **FAIL** | — |

### Hiện tượng

- TPS giảm mạnh -30%, từ PASS xuống FAIL.
- Latency tăng ở mọi percentile, đặc biệt p50 (+57%).
- Kafka v1 peak CPU ~200% (đã bão hòa 2 core). v2 Kafka peak cũng ~200%.

### Nguyên nhân

1. **Spark CPU giảm 4→2** → Spark batch duration tăng gấp đôi (~49s→~97s). Batch dài hơn → Spark chiếm disk I/O lâu hơn → Kafka (cùng disk) bị ảnh hưởng.
2. **Kafka tune có hại**: `KAFKA_NUM_IO_THREADS=8` + `KAFKA_NUM_NETWORK_THREADS=4` trong môi trường chỉ có 2 CPU gây contention nội bộ. Mặc định Kafka io.threads=8, network.threads=3. Tăng network.threads lên 4 mà CPU không đủ → context switch nhiều hơn → throughput giảm.
3. **Shared disk I/O**: Kafka log và Spark checkpoint cùng nằm trên 1 disk (97G total, 62% used).

### Giải pháp

- **Tách disk cho Kafka**: volume riêng (SSD preferred).
- **Revert Kafka tune**: giữ mặc định hoặc giảm `num.io.threads=4`, `num.network.threads=2` cho 2 CPU.
- **Tăng lại Kafka CPU**: thử `cpus: '4.0'` để xem Kafka có scale không.

---

## 4. Kết quả Spark Streaming

### So sánh

| Metric | v1 | v2 | Delta |
|--------|----|----|-------|
| Số batch | 4 (data) | 2 (data) | — |
| Batch 0 (init) | 3.2s | 7.2s | — |
| Batch 1 | 42.7s | **87.7s** | **+105%** |
| Batch 2 | 54.1s | **106.9s** | **+98%** |
| Batch 3 | 55.1s | — | — |
| Batch 4 | 45.0s | — | — |
| **Avg (data batches)** | **49.2s** | **97.3s** | **+98%** |
| Input rows/s (batch 1) | 762 | 941 | +23% |
| Input rows/s (batch 2) | 4,689 | 2,284 | -51% |

### Hiện tượng

- Batch duration gần như **tăng gấp đôi** (~49s → ~97s).
- Chỉ có 2 data batches trong v2 (so với 4 trong v1) trong cùng thời gian API test (3 phút).
- Trigger 30s không có tác dụng vì batch duration > trigger interval (back-pressure).

### Nguyên nhân

1. **CPU limit giảm 4→2**: Spark groupBy operations bound bởi CPU. Halving CPU → halving throughput → doubling batch time. Confirm: v1 Spark avg CPU ~226%, v2 ~156% (bị clamp ở 200%).
2. **Merge aggregations không đủ bù**: Giảm từ 6→5 groupBy không bù được mất 2 CPU cores. Cache giúp tránh re-scan nhưng shuffle vẫn cần CPU.
3. **Trigger 30s không生效**: Spark không ép batch chạy đúng 30s nếu processing time > trigger interval. Nó chạy ngay khi batch trước kết thúc.

### Giải pháp

- **Tăng lại Spark CPU**: `cpus=4` hoặc thử `cpus=3` để cân bằng với Kafka.
- **Tinh chỉnh merge**: có thể merge thêm E (model) vào C+D hoặc dùng multi-dimensional GROUPING SETS.
- **Tăng parallelism**: thêm `.config("spark.sql.shuffle.partitions", "8")` để tận dụng 8 cores system.

---

## 5. Kết quả E2E Pipeline

### So sánh

| Metric | v1 | v2 | Delta |
|--------|----|----|-------|
| Events processed | 3,993 | 4,148 | +3.9% |
| avg age | 88s | 87s | -1% |
| p50 | 87s | 82s | -6% |
| p95 | 159s | 161s | +1% |
| SLA p95 < 300s | PASS | PASS | — |

### Hiện tượng

- E2E ổn định, không thay đổi đáng kể.
- p50 giảm nhẹ (87→82s) dù Spark batch lâu hơn.

### Nguyên nhân

E2E latency được đo bằng Redis buffer age (timestamp ghi vào Redis → timestamp hiện tại). Nếu Spark xử lý chậm hơn, buffer sẽ chứa nhiều events cũ hơn → age tăng. Nhưng v2 không tăng đáng kể vì:
1. API throughput tương đương (~22 RPS).
2. Kafka TPS giảm → ít events hơn vào Redis mỗi giây → buffer nhỏ hơn → age không tăng dù Spark chậm.

### Giải pháp

- E2E đã pass SLA, không cần can thiệp ngay.
- Khi Kafka TPS hồi phục, cần theo dõi E2E lại.

---

## 6. Resource Usage

### CPU comparison (avg during API test)

| Service | v1 | v2 | Note |
|---------|----|----|------|
| Spark | ~226% | ~156% | Giảm do cpus 4→2 limit |
| Kafka | ~47% | ~50% | Ổn định |
| API | ~29% | ~37% | Tăng nhẹ |
| Postgres | ~10% | ~5% | Giảm |
| Redis | ~3% | ~5% | Tăng nhẹ |

### Memory

| Service | Limit | v1 peak | v2 peak |
|---------|-------|---------|---------|
| Spark | 8GiB | 1.32GiB | 1.06GiB |
| Kafka | 2GiB | 1.06GiB | 837MiB |
| API | 2GiB | 127MiB | 166MiB |

### Hiện tượng

1. Spark CPU avg giảm từ 226% → 156% do limit mới, nhưng batch duration tăng gấp đôi.
2. Kafka memory thấp hơn v1 (837MiB vs 1.06GiB) dù cùng limit, phản ánh throughput thấp hơn.
3. API memory tăng nhẹ, có thể do queue tích tụ nhiều hơn.

---

## 7. DB Metrics Export

### So sánh

| Table | v1 rows | v2 rows | Note |
|-------|---------|---------|------|
| popular_items | 1,937 | 300 | Giảm mạnh |
| stats_items | 1,637 | **0** | Bug? |
| stats_hourly | 3 | 1 | Ít batch hơn |
| anomaly_logs | 12 | 24 | Tăng |
| stats_sessions | 3 | 3 | OK |

### Hiện tượng

- `stats_items=0` trong v2: có thể do merged code hoặc batch chưa kịp ghi. Cần debug.
- `popular_items` 300 rows trong v2 = 100 aids × 3 types. Trong v1 là 1,937 items → nhiều hơn vì nhiều batch hơn.

### Giải pháp

- Debug `stats_items=0`: kiểm tra `merged_items_df.isEmpty()` + `collect()` có hoạt động đúng không.
- Nếu là timing issue (Export trước khi Spark ghi xong), cần đợi Spark batch hoàn tất trước khi export.

---

## 8. Tổng kết

### SLA verdict

| SLA | v1 | v2 |
|-----|----|----|
| API p95 < 500ms | FAIL (4,485ms) | FAIL (4,952ms) |
| API error rate < 1% | PASS (0%) | PASS (0%) |
| Kafka TPS > 5000 | PASS (5,265) | FAIL (3,670) |
| E2E p95 < 300s | PASS (159s) | PASS (161s) |

### Tác động của từng thay đổi

| Thay đổi | Expected | Actual |
|----------|----------|--------|
| CPU limits Spark 4→2 | Giảm contention | Batch duration x2, Kafka TPS -30% — **tác dụng phụ nghiêm trọng** |
| Trigger 30s | Batch ổn định | Không hiệu quả (batch > trigger) |
| Kafka IO/NETWORK threads | Tăng TPS | TPS giảm (-30%) — có thể do mismatch CPU |
| Merge aggregations + cache | Batch < 10s | Batch ~97s — merge không đủ bù CPU loss |

### Kết luận

1. **CPU limit Spark 4→2 là thay đổi có hại nhất**. Batch duration x2 kéo theo Kafka TPS giảm 30%.
2. **Kafka tune (IO/NETWORK threads) phản tác dụng** với CPU hạn chế. Cần revert hoặc giảm.
3. **Merge aggregations + cache** có lợi nhưng không đáng kể (giảm 1 shuffle trong 6).
4. **E2E ổn định** — không bị ảnh hưởng bởi các thay đổi.

### Giải pháp ưu tiên

| # | Giải pháp | Target | Ghi chú |
|---|-----------|--------|---------|
| 1 | **Revert Spark CPU**: quay lại `cpus: 4.0` | Hồi phục Kafka TPS + Spark batch | Ngay |
| 2 | **Revert Kafka tune**: xóa `num.io.threads`, `num.network.threads` hoặc giảm | Kafka TPS > 5K | Ngay |
| 3 | **Separate disk cho Kafka** | Kafka P95 < 1s | Giảm I/O contention |
