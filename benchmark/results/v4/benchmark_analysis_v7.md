# Benchmark Analysis v7 — Phase 2-4 Optimization Results

**Date:** 2026-05-23
**Run timestamp:** 10:44:34
**Duration:** 8 phút (Phase 3 API load test)
**Changes so far:** Phase 1 (Kafka producer config + queue), Phase 2 (Kafka CPU 4 + JVM tuning), Phase 3 (Spark trigger 10s + maxOffsetsPerTrigger 1000), Phase 4 (loadtest 8 phút)

---

## Tổng Quan

| Metric | v1 | v2 | v3 | **v4** |
|--------|-----|-----|-----|--------|
| **API P95 latency** | 4,485ms | 4,952ms | 5,319ms | **4,946ms** |
| **API P90 latency** | 3,295ms | 3,574ms | 4,276ms | **4,261ms** |
| **API median** | 114ms | 126ms | 214ms | **268ms** |
| **API avg** | 873ms | 818ms | 1,020ms | **1,322ms** |
| **Throughput** | 22.0 req/s | 22.9 req/s | 20.4 req/s | **23.0 req/s** |
| **Error rate** | 0% | 0% | 0% | **0%** |

### Kafka Producer (200K records)

| Metric | v1 | v2 | v3 | **v4** | Change |
|--------|-----|-----|-----|--------|--------|
| Throughput | 5,265 rec/s | 3,670 rec/s | 2,883 rec/s | **12,781 rec/s** | **+4.4x vs v3** |
| MB/sec | 5.14 | 3.58 | 2.82 | **12.48** | **+4.4x vs v3** |
| Avg latency | 5,221ms | 7,280ms | 9,328ms | **2,201ms** | **-76% vs v3** |
| P95 latency | 9,893ms | 11,828ms | 13,192ms | **4,254ms** | **-68% vs v3** |
| Max latency | 10,887ms | 12,836ms | 15,233ms | **4,382ms** | **-71% vs v3** |

### Spark Streaming

| Metric | v1 | v2 | v3 | **v4** |
|--------|-----|-----|-----|--------|
| Batches | 12 | 9 | 6 | **43** |
| Avg batch duration | 8,300ms | 10,800ms | 15,200ms | **10,610ms** |
| Max batch duration | 16,200ms | 18,500ms | 28,400ms | **26,721ms** |
| Avg input rows/s | 120 | 95 | 70 | **90** |
| Avg process rows/s | 85 | 72 | 55 | **102** |

### Resource Usage (avg trong during_api)

| Service | v1 | v2 | v3 | **v4** |
|---------|-----|-----|-----|--------|
| Spark CPU | ~300% | ~320% | ~350% | **229%** |
| Kafka CPU | ~185% | ~190% | ~180% | **61%** |
| API CPU | ~25% | ~28% | ~30% | **31%** |
| Postgres CPU | ~8% | ~10% | ~12% | **9%** |

---

## Phân Tích Chi Tiết

### 1. Kafka Producer (Phase 2 — Thành công lớn nhất)

Kafka throughput tăng **4.4 lần** (12,781 vs 2,883 rec/s) và latency giảm **76%** (2.2s vs 9.3s). Đây là kết quả trực tiếp của:

- **CPU limit 2→4 cores**: Kafka không còn bão hòa CPU. CPU avg giảm từ ~185% xuống 61%.
- **JVM tuning (+UseG1GC, MaxGCPauseMillis=100)**: GC pause giảm, throughput ổn định hơn.
- **num.io.threads=8, num.network.threads=6**: Xử lý I/O song song, tận dụng 4 cores.
- **memory 2g→4g**: Heap cố định 2GB, đủ cho producer test 200K records.

Kết quả: Kafka producer P95 latency 4.3s (so với 13.2s ở v3) — giảm gần 9 giây.

### 2. API Latency (Chưa cải thiện đáng kể)

P95 latency v4 (4,946ms) gần tương đương v2 (4,952ms) và tốt hơn v3 (5,319ms), nhưng vẫn rất xa mục tiêu 500ms.

**Nguyên nhân chính:** API latency không chỉ đến từ Kafka produce — nó bao gồm:
- Recommendation model (SASRec remote call: covisitation fallback cold_start)
- Logic xử lý event
- Và Kafka produce (chiếm phần nhỏ trong tổng latency)

Median latency chỉ 268ms — hầu hết request nhanh, nhưng tail latency (P90-P95) cao do:
- **SASRec remote timeout 2s**: Khi model remote timeout, API phải fallback → mất 2s+ cho mỗi request
- **Covisitation cache miss**: Hầu hết request fallback xuống cold_start vì không tìm thấy kết quả từ covisitation

**Cần tập trung vào recommendation model tuning để cải thiện P95.**

### 3. Spark Streaming (Có cải thiện nhưng chưa tối ưu)

Spark avg CPU giảm từ ~350% (v3) xuống **229%** (v4) nhờ:
- **Trigger 10s**: Spark không còn back-to-back processing
- **maxOffsetsPerTrigger=1000**: Giới hạn records/batch, mỗi batch xử lý trong ~7-10s

Tuy nhiên, batch đầu tiên mất 26.7s (catch-up từ Kafka producer test). Về sau ổn định ở ~7-10s, bằng trigger interval → Spark gần như không có idle time.

**Vấn đề:** Batch duration vẫn xấp xỉ trigger interval (10s). Lý tưởng là batch xử lý trong ~3-5s rồi Spark nghỉ 5-7s để Kafka có CPU.

### 4. E2E Pipeline

- collected_events: 11,055 rows (từ Redis buffer flush → PostgreSQL, không qua Spark)
- stats_hourly: 0 rows (Spark không kịp xử lý)
- stats_items: 0 rows
- stats_sessions: 3 rows
- popular_items: 300 rows
- E2E latency: avg 237s, P95 420s (rất cao do Spark catch-up chậm với maxOffsetsPerTrigger=1000)

**Lưu ý:** Một phần data không qua Kafka → Spark do lỗi `send_async` (`ensure_future` nuốt lỗi). Lỗi này đã được fix sau benchmark.

---

## SLA Verdict

| SLA | Target | Result | Status |
|-----|--------|--------|--------|
| API P95 latency | < 500ms | 4,946ms | **FAIL** |
| API error rate | < 1% | 0.00% | **PASS** |
| Kafka producer TPS | > 10,000 | 12,781 | **PASS** |
| Kafka P95 latency | < 5,000ms | 4,254ms | **PASS** |

---

## Kết Luận

### What worked
- **Phase 2 (Kafka tuning)**: Hiệu quả vượt mong đợi. Kafka throughput tăng 4.4x, latency giảm 76%.
- **Phase 3 (Spark trigger)**: Giảm CPU contention giữa Spark và Kafka.
- **Phase 4 (8 phút benchmark)**: Cho nhiều data hơn, kết quả đáng tin cậy hơn.

### What didn't work
- **send_async bug** (`ensure_future`): Lỗi nuốt exception, data không tới Kafka. Đã fix.
- **API P95 latency**: Vẫn 4.9s, không cải thiện đáng kể. Bottleneck là recommendation model, không phải Kafka.

### Next steps
1. **API P95 latency**: Fix recommendation model (SASRec remote timeout → giảm timeout từ 2s xuống 500ms)
2. **Spark idle time**: Tăng trigger lên 20-30s hoặc giảm maxOffsetsPerTrigger xuống 500
3. **Remove Phase 0 restart**: Đã xóa (user tự cleanup)
4. **Run benchmark lại** sau khi fix `send_async` và recommendation model
