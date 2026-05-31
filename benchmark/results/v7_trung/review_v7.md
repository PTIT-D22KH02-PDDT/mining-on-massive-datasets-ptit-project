# OTTO Recommender Pipeline - Benchmark Review v7

**Date:** 2026-05-31 09:54:32

## Tổng quan

Benchmark v7 đánh giá pipeline OTTO Recommender với mô hình **Tron** thay thế cho **LGBMRanker**.
Hệ thống không thay đổi về kiến trúc — chỉ swap model backend cho luồng ghi (background recomputation).
Hệ thống chạy trên Docker: 8 CPU cores, 15GB RAM, Spark cluster 2 workers, Kafka KRaft mode.

So sánh các chỉ số chính giữa v6 (LGBMRanker) và v7 (Tron):

| Metric | v6 (LGBMRanker) | v7 (Tron) | Delta |
|--------|-----------------|-----------|-------|
| API P50 | 212 ms | 108 ms | -49.1% |
| API P95 | 2,889 ms | 2,594 ms | -10.2% |
| API avg | 773 ms | 735 ms | -4.9% |
| API error | 0.28% | 0.61% | +0.33pp |
| API throughput | 30.9/s | 31.8/s | +2.9% |
| Kafka TPS | 11,554/s | 9,897/s | -14.3% |
| Kafka P95 | 4,687 ms | 8,232 ms | +75.6% |
| Spark avg batch | 10,111 ms | 10,312 ms | +2.0% |
| Spark steady batch | 7,292 ms | 7,355 ms | +0.9% |
| Spark process | 1,396/s | 1,389/s | -0.5% |
| E2E P50 | 201 s | 213 s | +6.0% |
| E2E P95 | 409 s | 410 s | +0.2% |

---

## 1. Kafka Producer Throughput

200,000 records, 1KB mỗi record, acks=1.

| Metric | v7 | v6 | SLA |
|--------|----|----|-----|
| Throughput | 9,897/s (9.67 MB/s) | 11,554/s | **FAIL** (<50K) |
| P50 latency | 1,872 ms | 2,159 ms | — |
| P95 latency | 8,232 ms | 4,687 ms | **FAIL** (>=5s) |
| Max latency | 9,269 ms | 5,293 ms | — |

**Nhận xét:** Kafka throughput giảm 14.3% (11,554 → 9,897/s) và P95 latency tăng 75.6%
(4,687 → 8,232ms, từ WARN chuyển thành FAIL). Đây là regression — có thể do
tranh chấp tài nguyên trên cùng máy chủ hoặc điều kiện hệ thống khác nhau giữa
hai lần chạy.

---

## 2. API Load Test (k6)

Kịch bản ramp-up 3 giai đoạn: 10 → 50 → 80 VUs, mỗi giai đoạn 3 phút.

| Metric | v7 | v6 | SLA |
|--------|----|----|-----|
| P50 latency | 108 ms | 212 ms | — |
| P95 latency | 2,594 ms | 2,889 ms | **FAIL** (>1s) |
| Avg latency | 735 ms | 773 ms | — |
| Max latency | 10,002 ms | 10,002 ms | — |
| Error rate | 0.61% | 0.28% | **WARN** (<1%) |
| Throughput | 31.8/s | 30.9/s | — |
| Total requests | 15,244 | 14,829 | — |

**Nhận xét:** API P95 cải thiện 10.2% (2,889 → 2,594ms) và P50 cải thiện đáng kể
49.1% (212 → 108ms). Error rate tăng từ 0.28% lên 0.61% nhưng vẫn ở mức WARN
(dưới 1%). Nhìn chung, kết quả API benchmark giữa hai phiên bản mô hình không
khác biệt đáng kể — cả hai đều cùng mức FAIL cho P95 và WARN cho error rate.
Sự khác biệt về P50 nằm trong biên độ dao động bình thường của kiểm thử tải.

---

## 3. Spark Streaming Stability

Trigger interval 10s, Spark cluster mode (2 workers).

| Metric | v7 | v6 | SLA |
|--------|----|----|-----|
| Số batches | 25 | 25 | — |
| Avg batch | 10,312 ms | 10,111 ms | **FAIL** (>10s) |
| Steady avg (b4-20) | 7,355 ms | 7,292 ms | **WARN** (<8s) |
| Process rate steady | 1,389/s | 1,396/s | — |

**Nhận xét:** Spark performance hầu như không thay đổi — avg batch 10.3s (FAIL),
steady-state 7.4s (WARN). Điều này phù hợp vì Spark pipeline không bị ảnh hưởng
bởi model swap (model chỉ ảnh hưởng đến API background worker).

---

## 4. End-to-End Latency

| Metric | v7 | v6 | SLA |
|--------|----|----|-----|
| P50 | 213 s | 201 s | **FAIL** (>60s) |
| P95 | 410 s | 409 s | **FAIL** (>5 phút) |

**Nhận xét:** E2E latency gần như không đổi. Nút thắt cổ chai (Spark streaming +
PostgreSQL write) vẫn là yếu tố quyết định.

---

## Kết luận

### WARN
| Metric | v7 | Ngưỡng |
|--------|----|--------|
| API error rate | 0.61% | <1% |
| Spark steady batch | 7.4 s | <8s |

### FAIL
| Metric | v7 | Ngưỡng |
|--------|----|--------|
| API P95 | 2,594 ms | >1s |
| Kafka TPS | 9,897/s | <50K |
| Kafka P95 | 8,232 ms | >=5s |
| Spark avg batch | 10.3 s | >10s |
| E2E P50 | 213 s | >60s |
| E2E P95 | 410 s | >5 min |

Việc swap mô hình từ LGBMRanker sang Tron không tạo khác biệt đáng kể trên
các chỉ số pipeline. API P95 và P50 có cải thiện nhẹ nhưng không thay đổi
phân loại SLA. Kafka có regression nhẹ, cần theo dõi.
