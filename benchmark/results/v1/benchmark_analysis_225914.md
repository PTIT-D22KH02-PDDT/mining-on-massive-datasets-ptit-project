# Báo Cáo Benchmark — 2026-05-21 22:59:14

## Tổng Quan

Đây là lần chạy benchmark thứ 2 trong phiên, thực hiện liền sau lần chạy trước đó (22:53:25) mà không khởi động lại stack. Kết quả phản ánh hiệu năng hệ thống trong trạng thái **đã có tải tồn đọng**.

---

## 1. Kafka Producer Benchmark

| Chỉ số | acks=1 |
|---|---|
| Số bản ghi | 200,000 (1 KB mỗi bản ghi) |
| Throughput | ~8,250 bản ghi/s (~8 MB/s) |
| Độ trễ trung bình | ~3,371 ms |
| Độ trễ tối đa | ~8,174 ms |
| p50 | ~3,277 ms |
| p95 | ~7,289 ms |
| p99 | ~8,085 ms |

Kafka producer không thay đổi giữa 2 lần chạy — throughput giữ nguyên ~8 MB/s.

---

## 2. API Load Test (k6)

| Chỉ số | Lần 1 (22:53) | Lần 2 (22:59) | Biến động |
|---|---|---|---|
| Duration | 3m | 3m | — |
| Số request | 4,068 | **1,891** | ⬇ 53% |
| Throughput | 22.5 req/s | **10.5 req/s** | ⬇ 53% |
| Tỉ lệ lỗi | 0% | 0% | ✅ |
| Avg latency | 854 ms | **2.78s** | ⬆ 3.3x |
| Median latency | 31 ms | **2.24s** | ⬆ 72x |
| p95 latency | 4.28s | **7.21s** | ⬆ 1.7x |
| Max latency | 7.23s | **10.0s** | ⬆ 38% |

Threshold `p(95)<500ms` thất bại ở cả 2 lần, nhưng lần 2 **nghiêm trọng hơn nhiều**.

---

## 3. Mức Sử Dụng Tài Nguyên

### Baseline (không tải)

| Container | Lần 1 (22:53) | Lần 2 (22:59) | Nhận xét |
|---|---|---|---|
| Kafka | ~12% CPU, 926 MiB | **~89% CPU, 938 MiB** | 🚩 CPU lần 2 cao bất thường dù chưa chạy load test |
| Spark Streaming | ~12% CPU, 1.52 GiB | ~14% CPU, 1.47 GiB | Bình thường |
| API | ~0.8% CPU, 100 MiB | ~7% CPU, 100 MiB | CPU nhỉnh hơn 1 chút |
| Postgres | ~0.1% CPU, 43 MiB | ~2% CPU, 50 MiB | Bình thường |
| Redis | ~1.2% CPU, 11 MiB | ~1.1% CPU, 12 MiB | Bình thường |

### Trong lúc Kafka Producer

| Container | CPU max | Mem max |
|---|---|---|
| Kafka | 208% | 1.196 GiB (60%) |
| Spark Streaming | 257% | 1.885 GiB (23.6%) |

### Trong lúc API Load Test

| Container | CPU max | Mem max |
|---|---|---|
| Spark Streaming | **399%** | **2.04 GiB (25.5%)** |
| Kafka | 207% (burst) | 1.02 GiB (50%) |
| API | **60%** | 115 MiB (5.6%) |
| Postgres | 47% | 55 MiB (2.7%) |
| Redis | 9.6% | 12.4 MiB (0.8%) |

---

## 4. Phân Tích Nguyên Nhân

### 4.1. Vì sao lần 2 chậm hơn lần 1 rất nhiều?

**Nguyên nhân chính: Kafka bị bão hòa từ trước khi test.**

Trong baseline của lần 2, Kafka đã ngốn **89% CPU** — trong khi baseline lần 1 chỉ ~12%. Điều này là do:
- Lần chạy benchmark thứ nhất (22:53) đã gửi 200K records qua Kafka producer + 4,068 request API
- Spark streaming vẫn đang xử lý micro-batch từ đợt trước khi lần 2 bắt đầu
- Kafka bị mắc kẹt ở chế độ CPU cao vì các partition chưa được cleanup, replication backlog
- Khi load test lần 2 khởi động, API gửi message vào Kafka — Kafka đã quá tải từ trước, dẫn đến hàng đợi producer bị chặn

**Kết quả:**
- Request API phải chờ Kafka produce hoàn tất
- Thời gian chờ tăng từ ~20ms (lần 1) lên ~2-3s (lần 2)
- Số request hoàn thành giảm từ ~22 req/s xuống ~10 req/s
- Median latency tăng từ 31ms lên 2.24s

### 4.2. Vì sao median lần 1 chỉ 31ms nhưng avg lên 854ms?

Đây là dấu hiệu của **phân phối latency hai đỉnh (bimodal)**:
- **Đỉnh thấp (~30ms)**: request đến khi không có hàng đợi Kafka produce — xử lý nhanh
- **Đỉnh cao (~3-7s)**: request đến khi hàng đợi Kafka produce đầy — phải chờ

Khi load thấp (đầu test), hầu hết request rơi vào đỉnh thấp. Khi VU tăng dần (30 → 80), hàng đợi tích tụ và đẩy request sang đỉnh cao.

### 4.3. Vì sao Kafka luôn ở ~200% CPU?

- Container Kafka giới hạn **2 CPU cores**
- 200% = cả 2 cores đều bão hòa
- Kafka 4.x trên single node không có replication nhưng vẫn phải ghi log segment, flush disk, xử lý IO
- Với throughput ~8 MB/s đầu vào + streaming read từ Spark, Kafka chạm giới hạn IO/CPU

### 4.4. Spark Streaming: "quái vật" tài nguyên

- CPU max: **399%** (trên 4 cores allocated)
- Memory max: **2.04 GiB** (25.5% của 8 GiB limit)
- Spark liên tục consume từ Kafka topic, xử lý micro-batch, ghi vào Postgres
- Khi Kafka produce chậm, Spark cũng không thể consume nhanh hơn — gây hiệu ứng domino

---

## 5. Giải Pháp Đề Xuất

### 5.1. Ngắn hạn (ưu tiên cao)

| Giải pháp | Tác động |
|---|---|
| **Async Kafka producer trong API** — chuyển từ `produce().get()` (sync) sang fire-and-forget + callback | Giảm p95 latency từ 4-7s xuống ~50ms |
| **Tăng Kafka CPU limit** từ 2 → 4 cores | Giảm bottleneck CPU, tăng throughput |
| **Restart stack giữa các lần benchmark** — `docker compose restart` để reset trạng thái Kafka/Spark | Tránh tải tồn đọng ảnh hưởng kết quả đo |

### 5.2. Trung hạn

| Giải pháp | Tác động |
|---|---|
| **Tunning Kafka** — tối ưu `num.io.threads`, `num.network.threads`, `log.flush.interval` | Tăng throughput và giảm latency dưới tải |
| **Điều chỉnh Spark streaming batch interval** — hiện đang mặc định, có thể tăng lên 10-30s | Giảm CPU overhead do micro-batch quá thường xuyên |
| **Connection pooling cho Postgres** — từ cả API và Spark | Giảm overhead kết nối DB |

### 5.3. Dài hạn

| Giải pháp | Tác động |
|---|---|
| **Tách Kafka ra máy riêng** | Không còn cạnh tranh CPU với Spark + API |
| **Thêm Kafka partition** — hiện đang 1 partition, tăng lên 3-6 | Tận dụng song song consume từ Spark |
| **Monitor với Prometheus + Grafana** thay vì docker stats 5s | Phát hiện bottleneck realtime |

---

## 6. Kết Luận

Hệ thống **hoạt động đúng** (0% lỗi, pipeline đầy đủ Kafka → Spark → Postgres → Dashboard). Tuy nhiên:

1. **API latency không đạt threshold** dưới tải do synchronous Kafka produce
2. **Kafka là bottleneck chính** — single node, 2 core limit, luôn ở 200% CPU
3. **Trạng thái tích lũy giữa các lần benchmark ảnh hưởng lớn đến kết quả** — nên reset stack trước mỗi lần đo
4. **Hệ thống phù hợp cho throughput vừa phải** (~20 req/s, ~8 MB/s Kafka) nhưng cần cải thiện cho production

**Cần ưu tiên:** Async Kafka producer + tăng Kafka CPU limit — 2 thay đổi này sẽ cải thiện latency dramatically.
