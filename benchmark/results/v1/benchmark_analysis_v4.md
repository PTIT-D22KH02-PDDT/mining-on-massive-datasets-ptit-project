# Benchmark Analysis — Run 2026-05-22 14:55:28

## Executive Summary

| SLA | Target | Actual | Verdict |
|-----|--------|--------|---------|
| API P95 latency | <500ms | **4,485ms** | ✗ FAIL |
| API error rate | <1% | 0.0% | ✓ PASS |
| Kafka producer TPS | >5,000 | **5,264** | ✓ PASS (sát) |
| Spark stability | batches > 0 | **5 batches** | ✓ PASS |
| E2E latency P50 | — | **87s** | — |
| E2E latency P95 | — | **159s** | — |

---

## 1. API Latency

| Metric | Value | So với previous runs |
|--------|-------|---------------------|
| avg | 873ms | ~ v2 (857ms) |
| med | **114ms** | ~ v2 (110ms), cải thiện 95% so với v1 (2.2s) |
| p(90) | 3,294ms | ~ v2 (3,533ms) |
| p(95) | **4,485ms** | ~ v2 (4,249ms) |
| p(99) | 5,784ms* | — |
| max | 6,184ms | ~ v2 (6,215ms) |
| samples | 3,993 | 22.5 req/s trong 3 phút |

### Vấn đề

**Tai latency rất cao so với median**: med=114ms nhưng p95=4,485ms (gap 4,371ms, ~38x). Điều này cho thấy:

1. **Đa số request nhanh** (114ms median) — Phase 1 (Kafka queue offload) hoạt động tốt
2. **Một số request rất chậm** (p95=4.5s, max=6.2s) — kéo cả phân phối lên

### Nguyên nhân có thể

| Nguyên nhân | Bằng chứng | Tác động ước lượng |
|------------|------------|-------------------|
| **SASRec remote call timeout** — circuit breaker mở, fallback mất >3s | Fallback chiếm 24% predictions (955/3993) | ~60% |
| **CPU contention** — Spark (229%) + Kafka (47%) + API (29%) > 300% trên 8-core | Docker stats trong API test | ~20% |
| **Redis pipeline** — mỗi request ghi 4-5 lần (event, prediction, online_hits, online_metrics) | API CPU chỉ 29% (I/O bound) | ~10% |

### Giải pháp đề xuất

| Giải pháp | Phức tạp | Tác động kỳ vọng |
|-----------|----------|-----------------|
| **Circuit breaker tuning**: giảm timeout SASRec từ 10s → 2s, fallback sớm hơn | Thấp | Giảm p95 từ 4.5s → ~2s |
| **Local SASRec model**: thay vì remote call, deploy local model | Cao | p95 ~500ms |
| **CPU reservation cho API**: giới hạn Spark CPU (cpus=2) | Thấp | Giảm jitter do scheduling |

---

## 2. Model Distribution

| Model | Count | % | Ghi chú |
|-------|-------|---|---------|
| cold_start | 2,534 | 63.5% | Session < 3 events → cold start |
| covisitation_fallback_cold_start | 955 | 23.9% | SASRec fallback → covisitation failed |
| cached_hybrid | 504 | 12.6% | Session đã có cache |

**24% requests fallback từ SASRec** — circuit breaker thường xuyên mở. p95=4.5s tương ứng với 1-2 lần SASRec timeout (10s mỗi lần) + fallback.

---

## 3. Kafka Producer

| Metric | Value |
|--------|-------|
| Throughput | **5,264 rec/s** (5.14 MB/s) |
| P50 latency | 3,912ms |
| P95 latency | **9,893ms** |
| P99 latency | 10,809ms |
| Max latency | 10,887ms |
| Records | 200,000 (size 1KB) |

### Vấn đề

- Throughput giảm so với v2 (9,473 rec/s) và v3 (7,643 rec/s)
- P95 latency ~10s rất cao so với các run trước (v2: 3.4s, v3: 6.3s)

### Nguyên nhân

1. **CPU contention**: Kafka (175%) + Spark (215%) + API (8.5%) trong Kafka test phase
2. **Disk I/O**: Docker volumes trên cùng ổ đĩa, Spark checkpoint + Kafka log cùng disk

### Giải pháp

| Giải pháp | Tác động |
|-----------|----------|
| **Tách disk**: Kafka log trên ổ riêng | Cao |
| **Giảm Spark parallelism**: `spark.executor.cores=2` thay vì mặc định | Trung bình |
| **Tune Kafka**: `num.io.threads=4`, `num.network.threads=3` cho single node | Trung bình |

---

## 4. Spark Streaming

| Metric | Value |
|--------|-------|
| Số batch | 5 batches |
| Batch duration avg | **40,005ms** (40s) |
| Batch duration max | 55,087ms (55s) |
| Input rows/s | avg 1,096 rows/s |
| Total input rows | 7,270 rows |

### Vấn đề

- **Batch duration 40-55s rất cao** — kỳ vọng <5s
- Chỉ 5 batches trong ~3 phút → xử lý chậm, backlog tăng
- Input throughput thấp (1,096 rps) so với Kafka produce rate (5,264 rps)

### Nguyên nhân

1. **CPU starvation**: Spark cần CPU để process, nhưng bị Kafka (175%) và API (8.5%) cạnh tranh
2. **6 aggregations per batch**: 6 aggregation queries + 6 PostgreSQL writes trong `foreachBatch`

### Giải pháp

| Giải pháp | Phức tạp | Tác động |
|-----------|----------|----------|
| **Tăng trigger interval**: `.trigger(processingTime='30s')` để giảm overhead | Thấp | Ổn định batch, giảm số lần trigger |
| **Giảm aggregation count**: merge 6 queries thành 2-3 | Trung bình | Giảm batch duration 50% |

---

## 5. E2E Pipeline Latency

| Metric | Value |
|--------|-------|
| Events flushed | 3,993 |
| Avg age | 88s |
| P50 | 87s |
| P95 | **159s** (~2.6 phút) |

Con số này là **flush buffer age** — thời gian event nằm trong Redis buffer trước khi flush vào `collected_events`, KHÔNG phải real E2E latency từ user event đến Spark output.

---

## 6. Resource Usage (Docker stats during API test)

| Service | CPU avg | CPU peak | MEM avg |
|---------|---------|----------|---------|
| otto-spark-streaming | **229.4%** | 378.8% | 12.7% |
| kafka | 46.7% | 143.8% | 43.1% |
| otto-api | 29.4% | 62.9% | 5.3% |
| postgres | 10.7% | 27.3% | 2.0% |
| redis | 3.5% | 14.6% | 0.9% |

**CPU total ~320% trên 8-core (800%)** — Spark (229%) chiếm gần 3 core. API (29%) chỉ <0.5 core. Cần CPU limits để giảm contention.

---

## 7. So sánh các run

| Metric | v1 (11 min) | v2 (3 min) | v3 (3 min) | v4 (run này) |
|--------|------------|-----------|-----------|-------------|
| API med | 2,238ms | 110ms | 91ms | **114ms** |
| API p95 | 7,209ms | 4,249ms | 4,446ms | **4,485ms** |
| API max | 10,002ms | 6,215ms | 6,072ms | **6,184ms** |
| Kafka TPS | — | 9,473 | 7,643 | **5,264** |
| Kafka P95 | — | 3,418ms | 6,286ms | **9,893ms** |
| Samples | 1,891 | 4,064 | 4,270 | **3,993** |
| DB metrics exported | ✗ | ✗ | ✗ | **✓** |
| Spark metrics | — | — | — | **5 batches** |

---

## 8. Giải pháp

1. **Circuit breaker tuning**: SASRec timeout 10s → 2s, max 2 fails → open (API p95 < 2s)
2. **CPU limits**: Spark cpus=2, Kafka cpus=2, API cpus=2 (giảm jitter)
3. **Spark trigger interval**: `.trigger(processingTime='30s')` (batch ổn định)
4. **Covisitation cache**: top-K per session precompute (API p95 < 1s)
5. **Kafka tune**: `num.io.threads`, `num.network.threads` (Kafka TPS > 10K)
6. **Local SASRec model** (API p95 < 500ms)
7. **Separate disk for Kafka** (Kafka P95 < 1s)
8. **Merge Spark aggregations** (batch duration < 10s)

---
