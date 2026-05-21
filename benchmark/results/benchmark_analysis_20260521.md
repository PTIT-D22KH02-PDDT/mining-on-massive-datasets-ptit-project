# Phân Tích Chi Tiết Benchmark OTTO - 21/05/2026

## Tổng Quan

Benchmark được thực hiện trên hệ thống OTTO với các thành phần chính:
- **Kafka**: Hệ thống message queue
- **Spark Streaming**: Xử lý dòng dữ liệu real-time
- **API Service**: Nhận và xử lý sự kiện
- **PostgreSQL & Redis**: Lưu trữ và cache

---

## 1. Kafka Producer Benchmark

### Kết Quả Đo Lường

| Chỉ số | Giá trị |
|--------|---------|
| Số bản ghi | 200,000 (1KB mỗi bản ghi) |
| Throughput | 8,249.5 rec/s (8.06 MB/s) |
| Độ trễ trung bình | 3,371 ms |
| Độ trễ p50 | 3,277 ms |
| Độ trễ p95 | 7,289 ms |
| Độ trễ p99 | 8,085 ms |

### Phân Tích Chi Tiết

**Hiệu suất thấp do nguyên nhân:**

1. **Ràng buộc CPU Kafka**: Kafka container chỉ được phân bổ 2 CPU cores, nhưng trong quá trình test CPU đạt **200% (208%)** - tức là đang chạy ở mức tối đa. Điều này gây ra:
   - Hàng đợi (queue) các request xuất hiện
   - Độ trễ tăng dần theo thời gian (từ ~3s đến ~8s)

2. **Kafka ack=1 đồng bộ**: Với cấu hình `acks=1`, producer phải chờ máy chủ xác nhận ghi thành công trước khi gửi tiếp, tạo ra độ trễ cố định ~3s cho mỗi batch.

3. **Spark Streaming đồng thời xử lý**: Khi Kafka nhận dữ liệu, Spark Streaming cũng đang tiêu thụ (consume) và xử lý, gây tăng CPU lên đến **363%**.

---

## 2. API Load Test (k6)

### Kết Quả Đo Lường

| Chỉ số | Giá trị |
|--------|---------|
| Tổng request | 4,068 |
| Throughput | 22.5 req/s |
| Tỷ lệ lỗi | 0% |
| Độ trễ trung bình | 854 ms |
| Độ trễ trung vị (p50) | 31 ms |
| Độ trễ p95 | 4,284 ms |
| Độ trễ p99 | 7,237 ms |

### Phân Tích Chi Tiết - Hiện Tượng "Bimodal Latency"

**Đặc trưng nổi bật: Median latency chỉ 31ms nhưng p95 lên tới 4.28s**

#### Nguyên nhân:

1. **API gọi Kafka đồng bộ**: Khi nhận request, API thực hiện produce message tới Kafka đồng bộ. Khi Kafka đang quá tải:
   - Request mới phải chờ trong hàng đợi
   - Độ trễ tăng theo cấp số nhân

2. **Mô hình "Fast Path vs Slow Path"**:
   - **Fast Path (31ms)**: Khi Kafka chưa quá tải, request được xử lý ngay
   - **Slow Path (hàng trăm ms - hơn 7s)**: Khi Kafka đang quá tải, request phải chờ

3. **Tương tác giữa Kafka và Spark**: 
   - Kafka gửi message → Spark tiêu thụ → Tạo tải cho Kafka
   - Vòng phản hồi này làm tăng độ trễ có hệ thống

---

## 3. Tài Nguyên Hệ Thống

### Trạng Thái Idle (Không tải)

| Container | CPU trung bình | Memory |
|-----------|----------------|--------|
| otto-spark-streaming | ~12% | 1.52 GiB (19%) |
| kafka | ~12% | 926 MiB (45%) |
| otto-api | ~0.8% | 100 MiB (5%) |
| postgres | ~0.1% | 43 MiB (2%) |
| redis | ~1.2% | 11 MiB (0.7%) |

**Nhận xét**: Hệ thống ổn định khi không có tải.

### Trong Khi Chạy Kafka Producer Test

| Container | CPU max | Memory |
|-----------|---------|--------|
| **kafka** | **208%** | **1.146 GiB (57%)** |
| otto-spark-streaming | 363% | 1.608 GiB (20%) |
| otto-api | 16% | 111 MiB (5%) |

**Phân tích**:
- Kafka đạt **giới hạn CPU 200%** - là bottleneck chính
- Spark Streaming tiêu thụ nhiều tài nguyên nhưng vẫn trong giới hạn

### Trong Khi Chạy API Load Test

| Container | CPU max | Memory |
|-----------|---------|--------|
| **otto-spark-streaming** | **389%** | **1.967 GiB (24.6%)** |
| **kafka** | **199%** | **1.019 GiB (49.7%)** |
| otto-api | 42.6% | 112 MiB (5.5%) |
| postgres | 50% | 50 MiB (2.4%) |
| redis | 10% | 13 MiB (0.9%) |

---

## 4. Đánh Giá Chi Tiết Các Thành Phần

### 4.1 Kafka - Bottleneck Chính

**Vấn đề:**
- Giới hạn CPU 2 cores là quá thấp cho workload
- Memory dùng ổn định ~1 GiB nhưng CPU luôn max out
- Disk I/O không được đo nhưng có thể là yếu tố giới hạn

**Giải pháp đề xuất:**
1. Tăng CPU limit từ 2 → 4 cores
2. Hoặc chuyển Kafka sang node riêng biệt
3. Tối ưu cấu hình `num.network.threads`, `num.io.threads`

### 4.2 Spark Streaming - Tiêu Thụ Tài Nguyên Cao

**Đặc điểm:**
- CPU dao động rất cao: 12% → 389%
- Memory ổn định ~1.5-2 GiB
- **Không bị OOM** - tốt, nhưng gần giới hạn

**Phân tích:**
- Spark đang xử lý micro-batch liên tục
- Mỗi micro-batch tiêu tốn CPU cao
- Cần tối ưu số lượng partition và batch interval

### 4.3 API Service - Ổn Định

**Kết quả tốt:**
- CPU chỉ ~42% dù throughput 22.5 req/s
- Memory ổn định ~112 MiB
- **0% lỗi** - ổn định

**Vấn đề:**
- Latency p95 vượt ngưỡng 500ms (thực tế 4.28s)
- Nguyên nhân: API blocking chờ Kafka

### 4.4 PostgreSQL & Redis - Dưỡng Dưỡng

- PostgreSQL: CPU < 50%, Memory ~50 MiB
- Redis: CPU < 10%, Memory ~12 MiB
- **Chưa đạt tới khả năng tối đa**

---

## 5. Khuyến Nghị Cải Thiện

### Ưu Tiên Cao

1. **Chuyển Kafka produce thành async**
   - Sử dụng background producer với callback queue
   - Giảm p95 latency từ ~4s xuống ~50ms
   - Code thay đổi: Thay vì `producer.send().get()` dùng `producer.sendAsync()`

2. **Tăng CPU cho Kafka**
   - Từ 2 → 4 cores
   - Hoặc chuyển Kafka sang node riêng

3. **Tối ưu Spark Streaming**
   - Tăng `spark.streaming.batch.interval` từ 1s lên 2-5s
   - Giảm số lượng partition nếu không cần thiết

### Ưu Tiên Trung Bình

4. **Thêm Caching Layer**
   - Redis có thể dùng để cache kết quả xử lý
   - Giảm tải cho Spark và Kafka

5. **Kéo dài thời gian test**
   - Hiện tại chỉ 3 phút
   - Cần 10+ phút để đánh giá steady-state

### Ưu Tiên Thấp

6. **Scale PostgreSQL/Redis**
   - Hiện tượng underutilized - chưy đâu đến giới hạn
   - Có thể giảm tài nguyên phân bổ

---

## 6. Kết Luận

Hệ thống OTTO hiện có **hiệu suất chấp nhận được** nhưng còn hạn chế:

**Điểm mạnh:**
- 0% lỗi dữ liệu (100% thành công)
- API phản hồi nhanh khi không có tải (31ms)
- Spark không bị crash dù tiêu thụ cao tài nguyên

**Điểm yếu:**
- Latency p95 quá cao (4.28s > 500ms threshold)
- Kafka là bottleneck duy nhất
- Spark tiêu thụ tài nguyên quá mức

**ROI cao nhất:** Chuyển Kafka produce sang async sẽ cải thiện đáng kể trải nghiệm người dùng.
