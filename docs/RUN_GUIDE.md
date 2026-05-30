# Hướng dẫn Vận hành Hệ thống OTTO Recommender

---

## Yêu cầu

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) đã cài đặt
- RAM tối thiểu **12GB** (khuyến nghị 16GB)
- Dung lượng ổ cứng trống **5GB+**

> Docker Desktop cho Windows cần WSL 2 hoặc Hyper-V. Khuyến nghị dùng WSL 2.

---

## 1. Chuẩn bị

### Clone repo

```bash
git clone https://github.com/duongvct/mining-on-massive-datasets-ptit-project.git
cd mining-on-massive-datasets-ptit-project
```

### Cấu hình `.env`

Kiểm tra file `.env` tại gốc project. Đảm bảo nội dung đúng:

```env
DOCKER_USERNAME=vucongtuanduong
DOCKER_TAG=latest

POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=otto_recommender
POSTGRES_USER=otto
POSTGRES_PASSWORD=otto123

REDIS_HOST=localhost
REDIS_PORT=6379

KAFKA_BOOTSTRAP_SERVERS=localhost:29092
KAFKA_HOST_EXTERNAL=localhost
KAFKA_PORT_EXTERNAL=29092

SASREC_REMOTE_URL=https://nam-bizarre-perfect-cost.trycloudflare.com

SPARK_MASTER_URL=local[*]
```

> Nếu muốn tắt PostgreSQL (chạy local không cần PG), thêm vào `.env`:
> ```
> POSTGRES_ENABLED=false
> ```

---

## 2. Build Docker Images

```bash
docker compose -f docker-compose.dev.yml build
```

> Lần đầu build sẽ mất 5-10 phút (tải base image + cài dependencies).

---

## 3. Start Infrastructure

Chỉ start các service cơ bản trước (Redis, Kafka, PostgreSQL):

```bash
docker compose -f docker-compose.dev.yml up -d redis kafka postgres
```

Kiểm tra tất cả services đã healthy:

```bash
docker compose -f docker-compose.dev.yml ps
```

Đợi đến khi tất cả hiển thị `healthy` hoặc `running` (~30 giây).

---

## 4. Load Covisitation Matrix vào Redis

Ma trận liên kết sản phẩm (covisitation matrix) là dữ liệu cần thiết để hệ thống gợi ý hoạt động. File parquet đã có sẵn trong `datasets/co_visited_unified.parquet/`.

Load vào Redis:

```bash
docker compose -f docker-compose.dev.yml --profile setup run --rm setup-matrix
```

> Lần đầu: mất 5-15 phút.
> Các lần sau: tự skip nếu Redis đã có dữ liệu.

Kiểm tra số keys đã load:

```bash
docker compose exec redis redis-cli DBSIZE
```

> Kết quả mong đợi: ~1,788,153 keys.

---

## 5. Chạy Setup Jobs (chỉ lần đầu tiên)

Tạo Kafka topics, seed popular items vào PostgreSQL:

```bash
docker compose -f docker-compose.dev.yml --profile setup run --rm setup-jobs
```

> Chạy 1 lần duy nhất. Bỏ qua bước này nếu đã chạy trước đó.

---

## 6. Start Toàn bộ Hệ thống

```bash
docker compose -f docker-compose.dev.yml up -d
```

Kiểm tra trạng thái:

```bash
docker compose -f docker-compose.dev.yml ps
```

Xem log real-time:

```bash
docker compose -f docker-compose.dev.yml logs -f api
docker compose -f docker-compose.dev.yml logs -f dashboard
```

---

## 7. Truy cập

| Service | URL | Mô tả |
|---------|-----|-------|
| Dashboard | http://localhost:8501 | Giao diện Streamlit |
| API | http://localhost:8000 | FastAPI server |
| API Docs | http://localhost:8000/docs | Swagger UI |
| Kafka UI | http://localhost:8989 | Quản lý Kafka |
| Spark Master | http://localhost:8080 | Spark cluster UI |

---

## 8. Test API

### Gửi event test (CMD)

```bash
curl -X POST http://localhost:8000/api/event -H "Content-Type: application/json" -d "{\"session_id\": 12345, \"aid\": 100, \"type\": \"clicks\"}"
```

### Gửi event test (PowerShell)

```powershell
Invoke-RestMethod -Uri http://localhost:8000/api/event -Method POST -ContentType "application/json" -Body '{"session_id": 12345, "aid": 100, "type": "clicks"}'
```

### Kiểm tra health

```bash
curl http://localhost:8000/api/health
```

---

## 9. Dừng hệ thống

```bash
docker compose -f docker-compose.dev.yml down
```

Xóa toàn bộ dữ liệu (reset sạch):

```bash
docker compose -f docker-compose.dev.yml down -v
```

---

## 10. Chạy Local (không dùng Docker)

Nếu muốn chạy API hoặc Streaming trực tiếp trên máy (không qua Docker):

### Cài dependencies

```bash
uv sync --all-extras
```

### Chạy API

```bash
uv run --extra api python src/api/main.py
```

### Chạy Spark Streaming

```bash
uv run --extra spark python src/streaming/spark_streaming_job.py
```

### Chạy Simulator

```bash
uv run src/simulator/client.py
```

> Khi chạy local, đảm bảo Redis, Kafka, PostgreSQL đã chạy (qua Docker hoặc cài trực tiếp).

---

## Troubleshooting

### API không start được

```bash
docker compose -f docker-compose.dev.yml logs api
```

Nguyên nhân phổ biến:
- Redis chưa chạy → `docker compose up -d redis`
- PostgreSQL chưa chạy → `docker compose up -d postgres`
- Thiếu image → chạy lại `docker compose -f docker-compose.dev.yml build api`

### Dashboard timeout (lỗi `API stats request timeout`)

API `/api/stats` mất quá lâu vì Redis scan chậm với nhiều keys. Kiểm tra API có chạy không:

```bash
curl http://localhost:8000/api/health
```

Nếu API ok mà vẫn timeout, rebuild API image:

```bash
docker compose -f docker-compose.dev.yml build api
docker compose -f docker-compose.dev.yml up -d api
```

### Redis không có covisitation keys

```bash
docker compose exec redis redis-cli DBSIZE
```

Nếu số keys < 1000, chạy lại:

```bash
docker compose -f docker-compose.dev.yml --profile setup run --rm setup-matrix
```

### Không đủ memory

Giảm RAM cho Spark workers trong `docker-compose.yml`:
- `spark-worker-1`: `memory: 4g` → `memory: 2g`
- `spark-worker-2`: `memory: 4g` → `memory: 2g`

### Spark Streaming không kết nối Kafka

```bash
docker compose -f docker-compose.dev.yml logs spark-streaming
```

Đảm bảo Kafka đã healthy trước khi start spark-streaming.

---

## Phụ lục: Kiến trúc Container

```
                    +------------------+
                    |     Dashboard    |  :8501 (Streamlit)
                    +--------+---------+
                             |
                    +--------+---------+
                    |       API        |  :8000 (FastAPI)
                    +--+------+------+--+
                       |      |      |
              +--------+  +---+---+  +--------+
              |           |       |           |
        +-----+----+ +---+---+ +-+--------+ +---+------+
        |   Redis  | | Kafka | | Postgres | | SASRec   |
        |   :6379  | | :9092 | | :5432    | | (remote) |
        +----------+ +-------+ +----------+ +----------+
```

| Container | Vai trò |
|-----------|---------|
| `redis` | Session storage + Covisitation matrix (1.7M+ keys) |
| `kafka` | Message queue cho user events |
| `postgres` | Persistent storage (predictions, events, metrics) |
| `api` | FastAPI backend server |
| `dashboard` | Giao diện Streamlit monitoring |
| `spark-streaming` | Real-time processing pipeline |
| `setup-matrix` | One-shot: load covisitation matrix vào Redis |
| `setup-jobs` | One-shot: tạo Kafka topics + seed data |
| `spark-master` | Spark cluster master node |
| `spark-worker-1/2` | Spark cluster worker nodes |
