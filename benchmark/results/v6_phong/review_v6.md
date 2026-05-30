# OTTO Recommender Pipeline - Benchmark Review v6

**Date:** 2026-05-30 21:27:34

## Tổng quan

Benchmark v6 đánh giá pipeline OTTO Recommender với kiến trúc Read-Path/Write-Path hoàn thiện.
Hệ thống chạy trên Docker: 8 CPU cores, 15GB RAM, Spark cluster 2 workers, Kafka KRaft mode.

---

## 1. Kafka Producer Throughput

200,000 records, 1KB mỗi record, acks=1.

| Metric | Giá trị | SLA |
|--------|---------|-----|
| Throughput | 11,554 records/sec (11.28 MB/s) | **FAIL** (ngưỡng: >50K OK, >100K WARN) |
| P50 latency | 2,159 ms | — |
| P95 latency | 4,687 ms | **WARN** (ngưỡng: <500ms OK, <5s WARN, >=5s FAIL) |
| Max latency | 5,293 ms | — |

**Nhận xét:** Throughput Kafka đạt ~11,500 records/s, dưới ngưỡng FAIL 50K. Nguyên nhân chính là tài nguyên CPU giới hạn trên máy chủ (8 cores) và tranh chấp I/O giữa Kafka log với Spark checkpoint trên cùng ổ đĩa. P95 4.7s ở mức WARN (dưới ngưỡng FAIL 5s).

---

## 2. API Load Test (k6)

Kịch bản ramp-up 3 giai đoạn: 10 → 50 → 80 VUs, mỗi giai đoạn 3 phút.

| Metric | Giá trị | SLA |
|--------|---------|-----|
| P50 latency | 212 ms | — |
| P95 latency | 2,889 ms | **FAIL** (ngưỡng: <200ms OK, <500ms WARN, >1s FAIL) |
| Avg latency | 773 ms | — |
| Max latency | 10,002 ms | — |
| Error rate | 0.28% | **WARN** (ngưỡng: <0.1% OK, <1% WARN, >=5% FAIL) |
| Throughput | 30.9 req/s | — |
| Total requests | 14,829 | — |

**Nhận xét:** P95 2.9s vượt ngưỡng FAIL (>1s). Nguyên nhân là các request đầu phiên phải chờ worker nền tính toán khi cache Redis trống. Tuy nhiên, P50 chỉ 212 ms cho thấy đa số request được phục vụ nhanh từ cache. Error rate 0.28% ở mức WARN - 41 request lỗi trên 14,829, xảy ra ở giai đoạn tải cao. Throughput 30.9 req/s cho thấy API có khả năng xử lý tốt dưới áp lực concurrent users.

---

## 3. Spark Streaming Stability

Trigger interval 10s, Spark cluster mode (2 workers).

| Metric | Giá trị | SLA |
|--------|---------|-----|
| Số batches | 25 | — |
| Avg batch duration | 10,111 ms | **FAIL** (ngưỡng: <5s OK, <8s WARN, >10s FAIL) |
| Steady-state avg (b4-20) | 7,292 ms | **WARN** (ngưỡng <8s) |
| Steady-state process rate | 1,396 rows/s | — |
| Min batch | 5,216 ms | — |
| Max batch | 25,154 ms (catch-up) | — |

**Nhận xét:** Avg batch 10.1s ở mức FAIL, nhưng steady-state (batches 4-20) duy trì ~7.3s (WARN). Batch đầu mất 25.2s do bắt kịp dữ liệu tồn đọng. Tốc độ xử lý steady-state ~1,400 rows/s vượt input rate ~500 rows/s, cho thấy Spark đủ khả năng theo kịp luồng dữ liệu. Các batch cuối (21-24) duration cao do backpressure khi nguồn cạn.

---

## 4. End-to-End Latency

Thời gian từ API nhận event → dữ liệu xuất hiện trong PostgreSQL.

| Metric | Giá trị | SLA |
|--------|---------|-----|
| P50 | 201 s | **FAIL** (ngưỡng: <10s OK, <30s WARN, >60s FAIL) |
| P95 | 409 s (~6.8 min) | **FAIL** (ngưỡng: <30s OK, <60s WARN, >5min FAIL) |

**Nhận xét:** Độ trễ đầu cuối ở mức FAIL. Nguyên nhân chính: Spark Streaming ghi vào PostgreSQL với batch interval 10s và checkpoint overhead, cộng với Kafka producer latency. Để cải thiện, cần tối ưu Spark micro-batch interval và PostgreSQL batch write throughput.

---

## 5. Tài nguyên hệ thống (trung bình khi test)

| Container | CPU (avg) | Memory |
|-----------|-----------|--------|
| otto-spark-streaming | N/A | 2.1 GB / 8 GB (26.8%) |
| redis-1 | 12.6% | 145 MB |
| postgres-1 | 9.5% | 23 MB |
| kafka | 2.3% | 433 MB |
| spark-worker-1 | 0.1% | 117 MB |
| spark-worker-2 | 0.1% | 109 MB |

**Nhận xét:** Spark streaming chiếm ~2.1GB RAM. Worker nodes hầu như không tải (~0.1% CPU) — workload streaming chạy chủ yếu trên driver (spark-streaming container). Redis CPU ~12.6% là service tốn CPU nhất ngoài Spark.

---

## Kết luận

### OK
— *(không có metric nào)*

### WARN
| Metric | Giá trị | Ngưỡng |
|--------|---------|--------|
| Kafka P95 latency | 4,687 ms | <5s |
| API error rate | 0.28% | <1% |
| Spark steady-state batch | ~7.3 s | <8s |

### FAIL
| Metric | Giá trị | Ngưỡng |
|--------|---------|--------|
| API P95 latency | 2,889 ms | >1s |
| Kafka throughput | 11,554/s | <50K |
| Spark avg batch | 10.1 s | >10s |
| E2E P50 | 201 s | >60s |
| E2E P95 | 409 s | >5 min |

### Hướng cải thiện ưu tiên

1. **Spark checkpoint I/O**: Tách riêng ổ đĩa cho checkpoint và Kafka log — giảm tranh chấp I/O, cải thiện cả Spark lẫn Kafka.
2. **API cold start penalty**: Cache warming hoặc precompute cho session đầu — giảm P95 latency.
3. **Kafka throughput**: Tăng CPU allocation cho Kafka broker và tuning batch size.
4. **PostgreSQL batch write**: Tối ưu batch size và connection pool cho Spark streaming output.
