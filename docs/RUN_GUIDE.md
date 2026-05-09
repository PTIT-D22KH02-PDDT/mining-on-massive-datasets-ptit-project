# Hướng dẫn chạy hệ thống pipeline

---

## 1. Khởi động Hạ tầng (Docker)
Đảm bảo bạn đã cài đặt Docker và Docker Compose. Hệ thống sử dụng Kafka (Message Queue), PostgreSQL (Database), và Redis (Cache).

```bash
# Khởi động Kafka, Postgres, Redis ở chế độ chạy ngầm
docker-compose up -d

# Kiểm tra trạng thái các container
docker ps
```

---

## 2. Khởi tạo Kafka Topic
Bạn cần tạo topic `user-events` trước khi bắt đầu gửi dữ liệu.

```bash
python src/scripts/create_kafka_topic.py
```

---


## 3. Chạy các Dịch vụ Lõi

### A. Khởi chạy Backend API
API xử lý việc nhận sự kiện và trả về kết quả gợi ý.

```bash
# Chạy API với port 8000
python src/api/main.py
```

### B. Khởi chạy Spark Streaming Job
Đây là công cụ xử lý dữ liệu thời gian thực, tính toán phễu và hiệu suất model.

```bash
python src/streaming/spark_streaming_job.py
```
*Lưu ý: Nếu gặp lỗi state corruption, hãy chạy: `rm -rf /tmp/spark-checkpoints/otto-streaming` trước khi chạy lệnh trên.*

---

## 4. Khởi chạy Dashboard Giao diện


```bash
streamlit run streamlit_app.py
```
Truy cập tại: `http://localhost:8501`

---

## 4. Chạy các file python độc lập để chuẩn bị dữ liệu

```bash
python src/batch/seed_popular_items.py
```


```bash
python src/batch/funnel_analysis.py
```

---

## 5. Chạy client.py giả lập 

```bash
python src/batch/client.py --file <đường dẫn file test.jsonl>
```

## Phụ lục: Các Port quan trọng
- **API**: 8000
- **Dashboard**: 8501
- **Kafka UI**: 8989 (Xem dữ liệu trên Kafka qua trình duyệt)
- **Postgres**: 5432
- **Redis**: 6379
