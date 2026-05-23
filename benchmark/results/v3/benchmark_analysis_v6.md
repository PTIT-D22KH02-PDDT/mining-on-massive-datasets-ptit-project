# Benchmark Run v3 vs v1/v2 — Comparison Analysis

- v1: 2026-05-22 14:55 (baseline)
- v2: 2026-05-22 22:12 (post-tuning: CPU limits 4→2 + trigger + Kafka tune + merge agg)
- v3: 2026-05-22 22:59 (reverted: Spark CPU 2→4, Kafka tune default; giữ lại trigger, merge agg)

---

## 1. Tổng quan thay đổi v3 so với v2/v1

| Thay đổi | v2 | v3 | So với v1 |
|----------|----|----|-----------|
| Spark `cpus=4` (default) | ❌ (2) | ✅ (4) | **Revert về v1** |
| Kafka `num.io.threads=8, num.network.threads=4` | ✅ | ❌ (default) | **Revert về v1** |
| Trigger `processingTime='30s'` | ✅ | ✅ | **Giữ** |
| Merge C+D + cache | ✅ | ✅ | **Giữ** |

**Kỳ vọng**: v3 ≈ v1 (vì đã revert các thay đổi có hại từ v2).

---

## 2. API Latency — So sánh 3 runs

| Metric | v1 | v2 | v3 | v3 vs v1 |
|--------|----|----|----|----------|
| Requests | 3,993 | 4,148 | **3,686** | -7.7% |
| RPS | 22.03 | 22.95 | **20.44** | -7.2% |
| avg | 873ms | 818ms | **1,020ms** | +16.8% |
| **med** | **114ms** | **126ms** | **214ms** | **+87.7%** |
| p90 | 3,295ms | 3,574ms | **4,276ms** | +29.8% |
| **p95** | **4,485ms** | **4,952ms** | **5,319ms** | **+18.6%** |
| max | 6,184ms | 6,469ms | **7,671ms** | +24.0% |
| error rate | 0% | 0% | 0% | — |
| SLA | FAIL | FAIL | FAIL | — |

### Hiện tượng

- **API degradation nghiêm trọng ở v3**: p95=5,319ms (cao nhất từ trước đến nay).
- Median tăng gần gấp đôi (114→214ms) — không còn "nhanh cho đa số request" nữa.
- RPS giảm 7% (22→20) dù CPU nhiều hơn v2.
- All percentiles đều tăng — không phải chỉ tail.

### Nguyên nhân

1. **Kafka TPS giảm mạnh (xem mục 3)**: Event handler dùng `kafka_queue.put_nowait()` bị back-pressure → API request queue tích tụ → latency tăng ở mọi percentile.
3. **Median tăng 87%** cho thấy ngay cả request "thường" cũng bị ảnh hưởng bởi Kafka back-pressure, không chỉ tail.

### Giải pháp

- Cần giải quyết Kafka trước (mục 3).

---

## 3. Kafka Producer — So sánh 3 runs

| Metric | v1 | v2 | v3 | v3 vs v1 |
|--------|----|----|----|----------|
| TPS | 5,264.8 | 3,669.7 | **2,882.7** | **-45.2%** |
| avg latency | 5,221ms | 7,280ms | **9,328ms** | +78.7% |
| p50 | 3,912ms | 6,147ms | **9,819ms** | +151.0% |
| p95 | 9,893ms | 11,828ms | **13,192ms** | +33.3% |
| max | 10,887ms | 12,836ms | **15,233ms** | +39.9% |
| Warm-up 1 TPS | 8,888 | 6,252 | **5,144** | -42.1% |
| Warm-up 2 TPS | 8,418 | 4,994 | **5,317** | -36.8% |
| SLA TPS>5K | PASS | FAIL | **FAIL** | — |

### Hiện tượng

- **Degradation theo chiều dọc**: mỗi run Kafka chậm hơn run trước:
  - v1: 5,265 TPS
  - v2: 3,670 TPS
  - v3: 2,883 TPS
- Warm-up runs cũng giảm: v1 8.8K → v3 5.1K (-42%).
- p50 tăng 151% so với v1 (3.9s → 9.8s).
- Disk full: 62% → 63% (không đáng kể).

### Nguyên nhân

1. **Cumulative disk fragmentation**: Kafka log và Spark checkpoint cùng 1 disk (97G total). Sau 3 benchmark runs (~600K events mỗi run), Kafka log files bị fragmented, làm giảm throughput.
2. **stats_items bug**: merged code gây stats_items=0 rows ở cả v2 và v3. Nếu write bị lỗi silent, pipeline back-pressure ảnh hưởng đến Kafka.
3. **Merge code chưa revert**: Merge code có thể có bug gây memory leak trong foreachBatch.
4. **Chưa có resource isolation**: Tất cả service cùng 1 disk, cùng bridge network. Spark + Kafka contention về disk I/O.

### Giải pháp

- **Tách disk cho Kafka**: volume riêng (SSD). Đây là giải pháp duy nhất triệt để cho shared I/O contention.
- **Debug stats_items=0**: kiểm tra merged_items_df code.
- **Resource isolation**: cấu hình docker network QoS hoặc tách service ra host riêng.

---

## 4. Spark Streaming — So sánh 3 runs

| Metric | v1 | v2 | v3 |
|--------|----|----|----|
| Data batches | 4 | 2 | 1 |
| Batch 0 (init) | 3.2s | 7.2s | **129.2s** |
| Batch 1 | 42.7s | 87.7s | **75.6s** |
| Batch 2 | 54.1s | 106.9s | — |
| Batch 3 | 55.1s | — | — |
| Batch 4 | 45.0s | — | — |
| **Avg (data)** | **49.2s** | **97.3s** | **75.6s** |
| Spark CPU avg (during API) | ~226% | ~156% | **~178%** |

### Hiện tượng

- **Batch 0 mất 129s** để init — bất thường (v1: 3.2s, v2: 7.2s). Có thể do disk I/O contention làm chậm checkpoint restore.
- Batch 1 = 75.6s — cải thiện so với v2 (87.7s) nhờ CPU 4→2 revert, nhưng VẪN TỆ hơn v1 (42.7s).
- Chỉ có 1 data batch trong suốt API test (3 phút) — rất ít.
- Trigger 30s hoàn toàn vô hiệu vì processing time > trigger interval.

### Nguyên nhân

1. **Disk I/O contention** với Kafka: Batch 0 init mất 129s (so với 3.2s ở v1) gợi ý checkpoint write/read bị chậm do disk đầy hơn sau nhiều run.
2. **Merge code có thể gây overhead**: `batch_df.cache()` + `isEmpty()` check trên merged_items_df tốn thêm 1 Spark action (so với lazy evaluation thuần túy ở v1). Điều này thêm latency cho mỗi batch.
3. **stats_items write lỗi**: Nếu `write_stats_items_from_rows` gặp lỗi, nó vẫn chiếm slot trong ThreadPoolExecutor, làm chậm các write khác.

### Giải pháp

- **Debug merged code**: kiểm tra `isEmpty()` + `collect()` có hoạt động đúng không.
- **Revert merge aggregation** nếu cần: quay lại 6 groupBy riêng (v1 style) để loại trừ.
- **Tăng shuffle partitions**: thêm `spark.sql.shuffle.partitions=8`.
- **Tách disk** cũng giúp Spark checkpoint không bị ảnh hưởng bởi Kafka log.

---

## 5. E2E — So sánh 3 runs

| Metric | v1 | v2 | v3 | v3 vs v1 |
|--------|----|----|----|----------|
| Events | 3,993 | 4,148 | **3,686** | -7.7% |
| avg_age | 88s | 87s | **86s** | -2.3% |
| p50 | 87s | 82s | **86s** | -1.1% |
| p95 | 159s | 161s | **160s** | +0.6% |
| SLA p95<300s | PASS | PASS | PASS | — |

### Nhận xét

- E2E ổn định qua 3 runs (86-88s avg, 159-161s p95).
- E2E không bị ảnh hưởng bởi các thay đổi vì nó chỉ đo Redis buffer age, không phải true end-to-end latency.
- Nếu đo từ lúc event gửi → Spark ghi xong vào DB, con số sẽ cao hơn nhiều và không ổn định.

---

## 6. Resource Usage

### CPU (avg during API test)

| Service | v1 | v2 | v3 | Note |
|---------|----|----|----|------|
| Spark | ~226% | ~156% | ~178% | Hồi phục 1 phần (4 cores) |
| Kafka | ~47% | ~50% | ~45% | Ổn định |
| API | ~29% | ~37% | ~33% | Ổn định |
| Postgres | ~10% | ~5% | ~11% | Dao động |

### CPU (avg during Kafka test)

| Service | v1 | v2 | v3 |
|---------|----|----|----|
| Spark | ~229% | ~133% | ~129% |
| Kafka | ~172% | ~164% | ~166% |

### Hiện tượng

1. **Spark CPU v3 (178%) cao hơn v2 (156%)** — đúng vì revert cpus 2→4.
2. **Kafka CPU trong Kafka test gần như giống nhau qua 3 runs** (~166-172%), nhưng TPS giảm dần (5.2K → 3.7K → 2.9K). Điều này chứng tỏ bottleneck là disk I/O, không phải CPU.
3. **Spark batch 0 init mất 129s ở v3** — dấu hiệu rõ ràng của disk degradation.

### Memory

| Service | Limit | v1 peak | v2 peak | v3 peak |
|---------|-------|---------|---------|---------|
| Spark | 8GiB | 1.32GiB | 1.06GiB | 1.31GiB |
| Kafka | 2GiB | 1.06GiB | 837MiB | 915MiB |
| API | 2GiB | 127MiB | 166MiB | 118MiB |

---

## 7. DB Metrics Export

| Table | v1 rows | v2 rows | v3 rows |
|-------|---------|---------|---------|
| popular_items | 1,937 | 300 | 300 |
| stats_items | 1,637 | **0** | **0** |
| stats_hourly | 3 | 1 | 1 |
| anomaly_logs | 12 | 24 | 20 |
| stats_sessions | 3 | 3 | 3 |

### Hiện tượng

- `stats_items=0` ở cả v2 và v3 — confirm bug trong merged code.
- `popular_items=300` = 100 aids × 3 types. Với v1, 1,937 items qua 4 batches, v2/v3 chỉ 1-2 batches → 300 là hợp lý.
- Debug: cần kiểm tra `merged_items_df.isEmpty()` + `collect()` có hoạt động đúng không. Nếu `isEmpty()` trigger evaluate và `collect()` trigger evaluate lại, kết quả vẫn phải giống nhau.
- Khả năng khác: `write_stats_items_from_rows` gặp SQL error nhưng bị silent catch trong `write_with_label`.

---

## 8. Tổng kết

### SLA verdict qua 3 runs

| SLA | v1 | v2 | v3 | Trend |
|-----|----|----|----|-------|
| API p95 < 500ms | FAIL (4.5s) | FAIL (5.0s) | FAIL (5.3s) | **Xấu dần** |
| API error < 1% | PASS | PASS | PASS | — |
| Kafka TPS > 5000 | PASS (5,265) | FAIL (3,670) | FAIL (2,883) | **Xấu dần** |
| E2E p95 < 300s | PASS (159s) | PASS (161s) | PASS (160s) | Ổn định |

### Phân tích tác động của từng thay đổi

| Thay đổi | Expected vs v1 | Actual vs v1 |
|----------|----------------|--------------|
| **Revert Spark 4→2→4** | Về baseline | API p95 +18.6%, Kafka TPS -45% — **v3 tệ hơn v1 dù đã revert** |
| **Revert Kafka tune** | Về baseline | Kafka TPS vẫn giảm — **không phải nguyên nhân** |
| **Giữ merge + cache** | Batch < 10s | Batch ~75s — **có bug (stats_items=0)** |
| **Giữ trigger 30s** | Batch ổn định | Batch > trigger — vô hiệu |

### Kết luận

1. **Revert CPU và Kafka tune không cứu được v3** — vẫn tệ hơn v1. Nguyên nhân chính là **disk I/O contention cumulative** (cùng 1 disk cho Kafka log + Spark checkpoint). Mỗi run benchmark làm đầy disk thêm, giảm throughput.
2. **Merge aggregation có bug** — stats_items=0 rows ở cả v2 và v3. Cần debug hoặc revert.
3. **Disk là bottleneck chính**: cả Kafka TPS và Spark batch duration đều degradation qua các run do shared disk.

### Giải pháp ưu tiên

| # | Giải pháp | Target | Ghi chú |
|---|-----------|--------|---------|
| 1 | **Tách disk riêng cho Kafka logs** (SSD preferred) | Kafka TPS > 5K, Spark batch < 30s | **Quan trọng nhất** |
| 2 | **Fix/debug merged code stats_items=0** | stats_items writes hoạt động | Có thể revert merge nếu cần |
