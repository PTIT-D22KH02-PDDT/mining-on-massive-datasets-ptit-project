# Hướng dẫn Vận hành Hệ thống OTTO Recommender

Dự án đã được cấu hình hóa hoàn toàn bằng Docker Compose. Chỉ cần một lệnh duy nhất để khởi động toàn bộ hệ thống (Hạ tầng, Tiền xử lý, Backend API, Spark Streaming, và Giao diện Dashboard).

---


Tạo thư mục lưu dữ liệu Kafka

```bash

sudo chown -R 1000:1000 ./kafka_data
```

Chạy uv sync toàn bộ extra 

```bash
uv sync --all-extras
```


## 1. Khởi động Toàn bộ Hệ thống

Đảm bảo bạn đã cài đặt Docker và Docker Compose. Mở terminal tại thư mục gốc của dự án và chạy:

```bash
# Khởi động toàn bộ dịch vụ (build lại image nếu cần)
docker-compose up -d --build

# Kiểm tra log của các dịch vụ để đảm bảo chúng đang chạy
docker-compose logs -f
```

Lệnh trên sẽ tự động:
1. Chạy các dịch vụ hạ tầng: **Kafka**, **PostgreSQL**, **Redis**.
2. Tự động tạo topic Kafka và chạy các batch script tiền xử lý dữ liệu qua container `setup-jobs`.
3. Khởi động **FastAPI Backend** (port 8000).
4. Khởi động **Spark Streaming Job** để xử lý dữ liệu realtime.
5. Khởi động **Streamlit Dashboard** (port 8501).

---

## 2. Truy cập các Dịch vụ

Khi hệ thống đã chạy lên (khoảng 30 giây đến 1 phút để tải xong các thư viện Spark), bạn có thể truy cập:

- **Dashboard Giao diện**: [http://localhost:8501](http://localhost:8501)
- **API Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Kafka UI** (Theo dõi dòng sự kiện): [http://localhost:8989](http://localhost:8989)

---

## 3. Quản lý Hệ thống

### Dừng hệ thống
```bash
docker-compose down
```

### Xóa toàn bộ dữ liệu (Database, Kafka, Checkpoints)
Nếu bạn muốn reset lại toàn bộ từ đầu (Clean state):
```bash
docker-compose down -v
rm -rf ./spark-checkpoints
```

### Tiền xử lý dữ liệu (Cực kỳ quan trọng)
*Lưu ý:* Ma trận liên kết sản phẩm (`CovisitationMatrix`) là cần thiết để AI gợi ý hoạt động tốt. Việc build matrix tiêu tốn khá nhiều RAM nên không được đưa vào tự động khởi chạy. Bạn cần tự chạy tập lệnh sau ở local của mình để xuất dữ liệu ra thư mục `datasets/processed/`:
```bash
python src/trainer/preprocess/CovisitationMatrixBuilder.py
```

---

## Phụ lục: Kiến trúc Container
- `kafka`: Broker Message Queue
- `postgres`: Lưu trữ Database thống kê
- `redis`: Session cache cho User
- `api`: FastAPI Backend
- `dashboard`: Giao diện Streamlit
- `spark-streaming`: Job PySpark xử lý realtime
- `setup-jobs`: Script tạo dữ liệu ban đầu (chạy xong tự tắt)
