# Improvement Proposal v5 — Spark Standalone Cluster (Multi-Worker)

**Date:** 2026-05-26

**Scope:** Chuyển đổi Spark từ `local[*]` (single-process, single-container) sang **Spark Standalone Cluster** với nhiều worker, nhằm tận dụng tài nguyên phân tán, tăng throughput cho streaming job, và rút ngắn thời gian batch processing.

**Bối cảnh:** Hiện tại tất cả Spark job đều chạy `local[*]` — driver và executor cùng nằm trong một JVM trên một container. Dù `spark-streaming` được allocate 8GB RAM / 4 CPUs, chỉ một process sử dụng được. Batch jobs (funnel_analysis, seed_popular_items) cũng chạy local, không tận dụng được tài nguyên nhàn rỗi từ các container khác.

---

## Hiện Trạng Spark Architecture

### Code Paths Tạo SparkSession (3 pattern khác nhau)

| Pattern | Files | Master | Source |
|---------|-------|--------|--------|
| **Direct builder** — hardcode config | `src/batch/funnel_analysis.py:51-57` | Không set → `local[*]` | Trực tiếp trong file |
| **Direct builder** — hardcode config | `src/batch/seed_popular_items.py:39-44` | Không set → `local[*]` | Trực tiếp trong file |
| **Direct builder** — hardcode config | `src/streaming/spark_streaming_job.py:731-741` | Không set → `local[*]` | Trực tiếp trong file |
| **Config-driven** — qua SparkService | `src/core/infra/spark.py:35-55` | `config.yml` → `local[*]` | `config/config.yml` |
| **Config-driven** (consumer) | `src/trainer/preprocess/DataProcessor.py` | SparkService inject | `config/config.yml` |
| **Config-driven** (consumer) | `src/trainer/preprocess/CovisitationMatrixBuilder.py` | SparkService inject | `config/config.yml` |
| **Config-driven** (consumer) | `src/trainer/eda/visualization.py` | SparkService inject | `config/config.yml` |

### Spark Config Hiện Tại

```yaml
# config/config.yml
spark:
  master: "${SPARK_MASTER:local[*]}"
  app_name: "mining-on-massive-datasets"
  config:
    spark.driver.memory: "4g"
    spark.executor.memory: "6g"
    spark.sql.shuffle.partitions: "60"
    spark.driver.maxResultSize: "2g"
    spark.memory.fraction: "0.8"
    spark.memory.storageFraction: "0.1"
    spark.local.dir: "/tmp/spark-temp"
```

Lưu ý: `config.yml` chỉ được áp dụng cho trainer/EDA code (qua SparkService). Batch jobs và streaming job **bỏ qua** config.yml hoàn toàn — tự hardcode riêng.

### Pipeline Infrastructure

```
┌─────────────────────────────────────────────────────────────┐
│                      docker-compose.yml                      │
├───────────────┬─────────────────────┬────────────────────────┤
│   Infra       │   App Services      │   Spark Services        │
│ ┌──────────┐  │ ┌────────┐          │ ┌──────────────────┐   │
│ │ Kafka    │  │ │ API    │          │ │ spark-streaming  │   │
│ │ 4c/4g    │  │ │ 2c/2g  │          │ │ 4c/8g            │   │
│ └──────────┘  │ └────────┘          │ │ local[*]         │   │
│ ┌──────────┐  │ ┌────────┐          │ └──────────────────┘   │
│ │ Postgres │  │ │Dashboard│         │ ┌──────────────────┐   │
│ │ 1c/2g    │  │ │ 1c/1g   │         │ │ setup-jobs       │   │
│ └──────────┘  │ └────────┘          │ │ batch scripts    │   │
│ ┌──────────┐  │                      │ │ local[*]         │   │
│ │ Redis    │  │                      │ └──────────────────┘   │
│ └──────────┘  │                      │                        │
└───────────────┴─────────────────────┴────────────────────────┘
```

### Dataset

| File | Size |
|------|------|
| `datasets/otto/train_sessions.parquet` | 882 MB |
| `datasets/otto/val_sessions.parquet` | 118 MB |
| `datasets/otto-recommender-system/train_sessions.parquet` | 882 MB |
| `datasets/otto-recommender-system/test.jsonl` | 384 MB |
| **Total** | **~2.3 GB** |

### Vấn Đề Với Local Mode

1. **CPU không tận dụng hết**: `spark-streaming` container có 4 CPUs, chạy local mode dùng 1 JVM → giới hạn bởi single-process scheduling
2. **Memory contention**: Driver và executor chia sẻ heap → cần `spark.memory.fraction: 0.8` để phân chia. Trong cluster mode, driver và executor có heap riêng
3. **Không scale được**: Muốn mở rộng, phải tăng resources container + restart. Không thể thêm worker mà không sửa deploy
4. **Fault tolerance thấp**: Nếu container die, Spark context mất hoàn toàn (streaming checkpoint vẫn còn nhưng cần restart)
5. **Batch jobs cạnh tranh**: Khi setup-jobs chạy funnel_analysis (dùng Spark), nó chiếm CPU từ spark-streaming (trên cùng host)

---

## Target Architecture: Spark Standalone Cluster

```
┌──────────────────────────────────────────────────────────────────────┐
│                        docker-compose.yml                            │
├───────────────┬─────────────────────┬────────────────────────────────┤
│   Infra       │   App Services      │   Spark Cluster                │
│ ┌──────────┐  │ ┌────────┐          │ ┌────────────────────────┐    │
│ │ Kafka    │  │ │ API    │          │ │ spark-master           │    │
│ │ 4c/4g    │  │ │ 2c/2g  │          │ │ port 7077 (RPC)        │    │
│ └──────────┘  │ └────────┘          │ │ port 8080 (Web UI)     │    │
│ ┌──────────┐  │ ┌────────┐          │ └───────────┬────────────┘    │
│ │ Postgres │  │ │Dashboard│         │      spark://spark-master:7077│
│ │ 1c/2g    │  │ │ 1c/1g   │          │             │                  │
│ └──────────┘  │ └────────┘          │  ┌──────────┼──────────┐     │
│ ┌──────────┐  │                      │  ▼          ▼          ▼     │
│ │ Redis    │  │                      │ ┌────────┐ ┌────────┐       │
│ └──────────┘  │                      │ │Worker 1│ │Worker 2│       │
│               │  ┌────────────────┐  │ │4g/2c   │ │4g/2c   │       │
│               │  │ spark-streaming│  │ └────┬───┘ └────┬───┘       │
│               │  │ (driver)       │  │      │          │            │
│               │  │ SPARK_MASTER=  │  │      └──────┬───┘            │
│               │  │ spark://master:│  │             ▼                 │
│               │  │ 7077           │  │    ┌──────────────┐          │
│               │  └────────────────┘  │    │ Shared Volumes│          │
│               │  ┌────────────────┐  │    │ - datasets/  │          │
│               │  │ setup-jobs     │  │    │ - checkpoints│          │
│               │  │ (driver)       │  │    └──────────────┘          │
│               │  │ SPARK_MASTER=  │  │                               │
│               │  │ spark://master:│  │                               │
│               │  │ 7077           │  │                               │
│               │  └────────────────┘  │                               │
└───────────────┴─────────────────────┴────────────────────────────────┘
```

### Luồng Hoạt Động

1. **spark-master** — Service chạy Spark Master, quản lý tài nguyên cluster
2. **spark-worker-1, spark-worker-2** — Service chạy Spark Worker, nhận task từ master
3. **spark-streaming** (driver) — Kết nối tới `spark://spark-master:7077`, submit job. Driver chạy trong container, executors chạy trên workers
4. **setup-jobs** (driver) — Tương tự, batch job chạy trên cluster
5. **Data access** — Cả workers và driver mount cùng volumes: `./datasets` (đọc parquet), `./spark-checkpoints` (streaming checkpoint)
6. **Postgres writes** — Executors trên workers ghi trực tiếp tới Postgres qua JDBC (giống hiện tại)
7. **Kafka streaming** — Executors trên workers đọc từ Kafka topic `user-events` trực tiếp

---

## Phase 1: Spark Worker Image

### 1.1 Tạo Dockerfile.spark-worker

**File mới:** `Dockerfile.spark-worker`

**Vấn đề:** Image `bitnami/spark:3.5` chỉ có JVM + Spark (Scala), không có Python. Workers cần Python + pyspark để chạy Python UDFs và code từ driver.

```dockerfile
FROM bitnami/spark:3.5

USER root

# Install Python 3 + pip + pyspark + psycopg2 (cho JDBC writes từ executors)
RUN install_packages python3 python3-pip && \
    pip3 install pyspark==3.5.0 psycopg2-binary

ENV PYSPARK_PYTHON=python3

USER 1001
```

**Tại sao cần psycopg2-binary trên worker:**
- `spark_streaming_job.py` dùng `foreachBatch` — foreachBatch chạy trên driver, không cần psycopg2 trên worker
- Nhưng các batch job (`funnel_analysis.py`, `seed_popular_items.py`) ghi JDBC trực tiếp — executors cần JDBC driver (có sẵn qua `spark.jars.packages`) và Python lib cho bất kỳ UDF nào

---

## Phase 2: Spark Cluster Services (docker-compose.yml)

### 2.1 Thêm Spark Master

```yaml
spark-master:
  image: bitnami/spark:3.5
  container_name: spark-master
  ports:
    - "7077:7077"    # Spark master RPC
    - "8080:8080"    # Spark Web UI
  environment:
    - SPARK_MODE=master
    - SPARK_RPC_AUTHENTICATION_ENABLED=no
    - SPARK_RPC_ENCRYPTION_ENABLED=no
    - SPARK_LOCAL_STORAGE_ENCRYPTION_ENABLED=no
    - SPARK_SSL_ENABLED=no
  volumes:
    - ./datasets:/opt/app/datasets:ro
    - ./spark-checkpoints:/tmp/spark-checkpoints
  networks:
    - spark-net
```

### 2.2 Thêm Spark Workers (2 replicas)

```yaml
spark-worker-1:
  build:
    context: .
    dockerfile: Dockerfile.spark-worker
  container_name: spark-worker-1
  depends_on:
    - spark-master
  environment:
    - SPARK_MODE=worker
    - SPARK_MASTER_URL=spark://spark-master:7077
    - SPARK_WORKER_MEMORY=4G
    - SPARK_WORKER_CORES=2
  volumes:
    - ./datasets:/opt/app/datasets:ro
    - ./spark-checkpoints:/tmp/spark-checkpoints
  networks:
    - spark-net
  deploy:
    resources:
      limits:
        cpus: '2.0'
        memory: 4g

spark-worker-2:
  build:
    context: .
    dockerfile: Dockerfile.spark-worker
  container_name: spark-worker-2
  depends_on:
    - spark-master
  environment:
    - SPARK_MODE=worker
    - SPARK_MASTER_URL=spark://spark-master:7077
    - SPARK_WORKER_MEMORY=4G
    - SPARK_WORKER_CORES=2
  volumes:
    - ./datasets:/opt/app/datasets:ro
    - ./spark-checkpoints:/tmp/spark-checkpoints
  networks:
    - spark-net
  deploy:
    resources:
      limits:
        cpus: '2.0'
        memory: 4g
```

**Tổng tài nguyên cluster:**
| Component | RAM | CPU |
|-----------|-----|-----|
| Spark Master | container default | — |
| Worker 1 | 4 GB | 2 cores |
| Worker 2 | 4 GB | 2 cores |
| **Total executor resources** | **8 GB** | **4 cores** |

So với hiện tại (spark-streaming 8G/4c local): RAM executor tăng từ 0 (local mode) lên 8 GB, CPU executor tăng từ 4 lên 4+ (driver riêng).

### 2.3 Set Env Cho Driver Containers

```yaml
spark-streaming:
  environment:
    - SPARK_MASTER_URL=spark://spark-master:7077
    - SPARK_DRIVER_MEMORY=2g
    - SPARK_EXECUTOR_MEMORY=4g

setup-jobs:
  environment:
    - SPARK_MASTER_URL=spark://spark-master:7077
    - SPARK_DRIVER_MEMORY=2g
    - SPARK_EXECUTOR_MEMORY=4g
```

---

## Phase 3: Đồng Bộ SparkSession Code

### 3.1 Vấn Đề Hiện Tại

3 pattern tạo SparkSession khác nhau, nhiều file hardcode config không đọc env:

| File | Dòng | Master hiện tại | Code |
|------|------|-----------------|------|
| `funnel_analysis.py` | 51-57 | `local[*]` (implicit) | `SparkSession.builder.appName(...).config("spark.jars.packages", ...).config("spark.driver.memory", "4g").getOrCreate()` |
| `seed_popular_items.py` | 39-44 | `local[*]` (implicit) | Giống funnel analysis |
| `spark_streaming_job.py` | 731-741 | `local[*]` (implicit) | `.config("spark.sql.streaming.checkpointLocation", ...).config("spark.jars.packages", ...)` |
| `spark.py` (SparkService) | 35-55 | `config.yml` → env | `builder.master(sc.get("master", "local[*]"))` |

### 3.2 Giải Pháp

**Nguyên tắc:** Tất cả SparkSession đọc `spark.master` từ env `SPARK_MASTER_URL`, fallback `local[*]`.

**a) SparkService (`src/core/infra/spark.py`) — sửa nhẹ:**

```python
def _start_spark(app_name: str | None = None):
    sc = _spark_cfg()
    master = os.getenv("SPARK_MASTER_URL") or sc.get("master", "local[*]")
    name = app_name or sc.get("app_name", "pyspark-app")
    builder = SparkSession.builder.master(master).appName(name)
    ...
```

Component này đã gần đúng — chỉ cần ưu tiên `os.getenv("SPARK_MASTER_URL")` trước config.yml.

**b) Batch job `funnel_analysis.py` — thêm master URL:**

```python
# Dòng 51-57 hiện tại:
spark = (
    SparkSession.builder.appName("OTTO-Funnel-Analysis")
    .config("spark.jars.packages", "org.postgresql:postgresql:42.7.1")
    .config("spark.driver.memory", "4g")
    .config("spark.sql.session.timeZone", "GMT+7")
    .getOrCreate()
)

# Sửa thành:
import os
spark = (
    SparkSession.builder.appName("OTTO-Funnel-Analysis")
    .master(os.getenv("SPARK_MASTER_URL", "local[*]"))
    .config("spark.jars.packages", "org.postgresql:postgresql:42.7.1")
    .config("spark.driver.memory", os.getenv("SPARK_DRIVER_MEMORY", "4g"))
    .config("spark.sql.session.timeZone", "GMT+7")
    .getOrCreate()
)
```

**c) Batch job `seed_popular_items.py` — tương tự:**

```python
import os
spark = (
    SparkSession.builder.appName("OTTO-Seed-Popular-Items")
    .master(os.getenv("SPARK_MASTER_URL", "local[*]"))
    .config("spark.jars.packages", "org.postgresql:postgresql:42.7.1")
    .config("spark.driver.memory", os.getenv("SPARK_DRIVER_MEMORY", "4g"))
    .getOrCreate()
)
```

**d) Streaming job `spark_streaming_job.py` — thêm master URL:**

```python
import os
spark = (
    SparkSession.builder.appName("OTTO-Streaming-Processor")
    .master(os.getenv("SPARK_MASTER_URL", "local[*]"))
    .config("spark.sql.streaming.checkpointLocation", CHECKPOINT_LOCATION)
    .config("spark.sql.streaming.minBatchesToRetain", 10)
    .config("spark.jars.packages",
        "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.postgresql:postgresql:42.7.1")
    .config("spark.sql.session.timeZone", "UTC")
    .getOrCreate()
)
```

### 3.3 Cập Nhật config.yml

```yaml
spark:
  master: "${SPARK_MASTER_URL:local[*]}"
  app_name: "mining-on-massive-datasets"
  config:
    spark.driver.memory: "${SPARK_DRIVER_MEMORY:2g}"
    spark.executor.memory: "${SPARK_EXECUTOR_MEMORY:4g}"
    spark.sql.shuffle.partitions: "12"     # 4 executor cores × 3 = 12
    spark.driver.maxResultSize: "2g"
    spark.memory.fraction: "0.8"
    spark.memory.storageFraction: "0.1"
    spark.local.dir: "/tmp/spark-temp"
```

Thay đổi quan trọng:
- `spark.master` đọc env `SPARK_MASTER_URL` thay vì `SPARK_MASTER`
- `spark.sql.shuffle.partitions: 60 → 12`: Với 2 worker × 2 cores = 4 executor cores, 12 partitions là đủ. Công thức: `executor_cores × 3` (hệ số an toàn)
- `spark.driver.memory: 4g → 2g`: Driver chỉ chạy scheduling + foreachBatch, không cần 4g
- `spark.executor.memory: 6g → 4g`: Phù hợp với worker memory limit 4g

---

## Phase 4: Data Access & Shared Storage

### 4.1 Vấn Đề

Trong cluster mode, executors chạy trên worker containers (máy khác với driver). Nếu worker không có access tới parquet files và checkpoint directory, job sẽ fail với lỗi "File not found".

### 4.2 Shared Volumes (docker-compose mount)

Cả `spark-master`, `spark-worker-*`, `spark-streaming`, và `setup-jobs` đều mount:

```yaml
volumes:
  - ./datasets:/opt/app/datasets:ro    # Read-only cho parquet files
  - ./spark-checkpoints:/tmp/spark-checkpoints  # Read-write cho streaming checkpoints
```

**Yêu cầu:** Thư mục `spark-checkpoints/` phải tồn tại trước khi spark-streaming start.

### 4.3 Checkpoint Compatibility

**Rủi ro cao:** Checkpoint từ `local[*]` mode **không tương thích** với cluster mode. Cấu trúc checkpoint chứa metadata về SparkSession config, bao gồm master URL.

**Giải pháp:**
- Khi chuyển từ local → cluster, **xóa** `spark-checkpoints/` cũ
- Hoặc dùng checkpoint path khác (thêm biến env `SPARK_CHECKPOINT_DIR`)

```python
# spark_streaming_job.py
CHECKPOINT_LOCATION = os.getenv("SPARK_CHECKPOINT_DIR", "/tmp/spark-checkpoints/otto-streaming")
```

Có thể set trong docker-compose:
```yaml
spark-streaming:
  environment:
    - SPARK_CHECKPOINT_DIR=/tmp/spark-checkpoints/otto-streaming-cluster
```

### 4.4 Data Locality Consideration

Với Spark cluster, executor sẽ đọc parquet từ shared volume (qua Docker mount). Trên single machine (Docker Desktop hoặc single host), đây là local disk nên không có network overhead. Trên multi-host Docker Swarm, cần NFS hoặc giải pháp shared storage khác — nằm ngoài scope hiện tại.

---

## Phase 5: Partition & Resource Tuning

### 5.1 Shuffle Partitions

| Config | Giá trị cũ | Giá trị mới | Lý do |
|--------|-----------|-------------|-------|
| `spark.sql.shuffle.partitions` | 60 | 12 | 4 executor cores × 3 = 12 |
| `spark.executor.cores` | (default: 1) | 2 | Worker có 2 CPUs |
| `spark.executor.instances` | (default: 1 per worker) | 1 per worker | Giữ 1 executor/worker, tránh overhead |
| `spark.default.parallelism` | (default: từ shuffle) | 12 | Ngang với shuffle partitions |

### 5.2 Memory Tuning

```
Worker 4GB RAM:
├── Spark overhead (0.4 * executorMemory)   = 1.6 GB
├── spark.executor.memory (user memory)      = 4.0 GB
├── spark.memory.offHeap.enabled = false
└── spark.memory.fraction = 0.8
    ├── spark.memory.storageFraction = 0.1  (0.32 GB storage)
    └── execution memory                      (2.88 GB execution)
```

Với dataset 2.3 GB, execution memory 2.88 GB/executor × 2 executors = 5.76 GB total, đủ cho hầu hết shuffle operations.

### 5.3 Streaming Specific Tuning

```yaml
# docker-compose — spark-streaming environment
- SPARK_MASTER_URL=spark://spark-master:7077
- SPARK_DRIVER_MEMORY=2g
- SPARK_EXECUTOR_MEMORY=4g
- SPARK_SQL_SHUFFLE_PARTITIONS=12
- SPARK_SQL_STREAMING_MINBATCHESTORETAIN=10
- SPARK_SQL_STREAMING_MAXOFFSETSPERTRIGGER=5000
# Trigger interval (code change từ v4)
# .trigger(processingTime="10 seconds")
```

---

## Phase 6: Dockerfile & Makefile Updates

### 6.1 Dockerfile.spark-worker

**File mới, đã mô tả ở Phase 1.1.** Đặt tại `Dockerfile.spark-worker`.

### 6.2 Base Image Cho Driver Containers (Optional)

Nếu muốn tránh duplicate Java installation, có thể tạo `Dockerfile.spark-base`:

```dockerfile
FROM python:3.12-alpine

RUN apk add --no-cache openjdk21-jre-headless bash && \
    pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --extra spark

ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk
ENV PYSPARK_PYTHON=python3
ENV PATH="/opt/app/.venv/bin:$JAVA_HOME/bin:$PATH"
```

Sau đó `Dockerfile.streaming` và `Dockerfile.setup` kế thừa:

```dockerfile
FROM otto/otto-spark-base:latest
COPY src/ src/
COPY config/ config/
CMD ["python3", "src/streaming/spark_streaming_job.py"]
```

Hiện tại `Dockerfile.streaming` và `Dockerfile.setup` đã tự cài Java, việc tách base là optional optimization.

### 6.3 Cập Nhật Makefile

```makefile
build-spark-worker:
	docker build -f Dockerfile.spark-worker \
		-t $(DOCKER_USERNAME)/otto-spark-worker:$(TAG) .

# Nếu tách base:
build-spark-base:
	docker build -f Dockerfile.spark-base \
		-t $(DOCKER_USERNAME)/otto-spark-base:$(TAG) .

build-streaming:
	docker build -f Dockerfile.streaming \
		-t $(DOCKER_USERNAME)/otto-spark-streaming:$(TAG) .

build: build-api build-streaming build-dashboard build-setup build-spark-worker

push: build-push-spark-worker

build-push-spark-worker: build-spark-worker
	docker push $(DOCKER_USERNAME)/otto-spark-worker:$(TAG)
```

---

## Phase 7: Deploy & Verification Steps

### 7.1 Build & Deploy

```bash
# 1. Build images
make build

# 2. Start cluster trước
docker compose up -d spark-master spark-worker-1 spark-worker-2

# 3. Kiểm tra Web UI
open http://localhost:8080   # Phải thấy 2 workers, 8 GB memory, 4 cores total

# 4. Start toàn bộ
docker compose up -d
```

### 7.2 Verification Checklist

| Step | Check | Command |
|------|-------|---------|
| 1 | Spark Master Web UI accessible | `curl -s http://localhost:8080 \| grep -o "Alive Workers: [0-9]*"` → "Alive Workers: 2" |
| 2 | Workers registered | `curl -s http://localhost:8080/json/ \| jq '.workers \| length'` → 2 |
| 3 | Spark streaming connected | `docker logs spark-streaming 2>&1 \| grep "Connected to Spark Master"` → success |
| 4 | Executors running | `docker logs spark-streaming 2>&1 \| grep "executor added"` → có executor logs |
| 5 | Streaming checkpoint | `docker logs spark-streaming 2>&1 \| grep "checkpoint"` → không lỗi |
| 6 | Funnel analysis (setup-jobs) | `docker logs otto-setup-jobs 2>&1 \| grep -i "error\|exception"` → không lỗi |

### 7.3 Rollback Plan

Nếu cluster mode gặp vấn đề:

1. **Immediate rollback**: Set env `SPARK_MASTER_URL=local[*]` trên spark-streaming và setup-jobs
2. **Dừng cluster**: `docker compose down spark-master spark-worker-1 spark-worker-2`
3. **Restart driver containers**: `docker compose up -d spark-streaming setup-jobs`
4. **Nếu checkpoint lỗi**: Xóa `spark-checkpoints/` → restart streaming (mất progress)

---

## Tác Dự Kiến

### Resource Utilization

| Resource | Local Mode (`local[*]`) | Cluster Mode (2 workers) |
|----------|------------------------|--------------------------|
| Spark driver CPU | 4 cores (1 container) | 2-4 cores (driver container) |
| Spark executor CPU | 0 (cùng JVM) | 4 cores (2 workers × 2) |
| Spark total RAM | 8 GB (1 container) | 8 GB workers + 2 GB driver = 10 GB |
| CPU contention với Kafka | Cao (streaming + setup cùng host) | Thấp (workers có thể trên host khác hoặc time-share) |

### Streaming Job Performance

| Metric | Local Mode | Cluster Mode (dự kiến) |
|--------|-----------|----------------------|
| Kafka consume rate | 1 executor (cùng driver) | 2 executors (parallel) |
| Micro-batch processing | Single JVM heap | Distributed heap |
| foreachBatch write | 1 driver process | 1 driver process (giống) |
| Checkpoint I/O | Local disk | Shared volume (giống) |

Lưu ý: `foreachBatch` luôn chạy trên driver, không phân tán được. Lợi ích chính của cluster là các transforms (groupBy, window, join) chạy distributed trên executors.

### Batch Job Performance (funnel_analysis, seed_popular_items)

| Job | Local | Cluster (dự kiến) |
|-----|-------|-------------------|
| funnel_analysis (882 MB parquet) | ~2-3 phút | ~1-2 phút (distributed scan) |
| seed_popular_items (882 MB) | ~1 phút | ~30-45 giây |

Lợi ích cho batch jobs rõ hơn vì chúng scan toàn bộ dataset. Với shuffle partitions giảm từ 60 → 12, I/O shuffle cũng giảm.

---

## Rủi Ro & Mitigation

| Rủi ro | Level | Mitigation |
|--------|-------|------------|
| **Checkpoint incompatible** | Critical | Xóa checkpoint cũ hoặc dùng path mới. Add env `SPARK_CHECKPOINT_DIR` để linh hoạt |
| **Worker không có Python lib** | High | `Dockerfile.spark-worker` cài pyspark + psycopg2-binary |
| **PySpark version mismatch** | Medium | pyspark==3.5.0 (pip) ↔ Spark 3.5 (bitnami image) — cùng major version, tương thích |
| **Worker không đọc được parquet** | Medium | Mount `datasets/` r/o trên worker containers |
| **Network shuffle overhead** | Low | Single host (Docker), network = local loopback. Với dataset 2.3GB, shuffle ~200-500 MB |
| **Kafka từ worker không reachable** | Low | Kafka trên cùng network `spark-net`, hostname `kafka:9092` resolvable |
| **Postgres writes từ worker** | Low | JDBC driver qua `spark.jars.packages`, Postgres trên cùng network |
| **Memory overhead lớn hơn local** | Medium | 8 GB workers + 2 GB driver = 10 GB (tăng 2 GB so với 8 GB local) |
| **Spark Master SPOF** | Low | Master chỉ scheduling, không có dữ liệu. Nếu master die, job fail. Có thể thêm ZooKeeper HA nếu cần (future) |

---

## Tổng Kết

### Files Thay Đổi / Thêm Mới

| File | Action | Mức độ |
|------|--------|--------|
| `Dockerfile.spark-worker` | **Thêm mới** | Phải có |
| `docker-compose.yml` | Sửa — thêm `spark-master`, `spark-worker-1`, `spark-worker-2` | Phải có |
| `docker-compose.yml` | Sửa — thêm env `SPARK_MASTER_URL` cho `spark-streaming`, `setup-jobs` | Phải có |
| `docker-compose.dev.yml` | Sửa — thêm master, worker services (dev override) | Nên có |
| `docker-compose-hub.yml` | Sửa — thêm master, worker services (hub) | Nên có |
| `src/batch/funnel_analysis.py` | Sửa — thêm `.master(os.getenv(...))` | Phải có |
| `src/batch/seed_popular_items.py` | Sửa — thêm `.master(os.getenv(...))` | Phải có |
| `src/streaming/spark_streaming_job.py` | Sửa — thêm `.master(os.getenv(...))` | Phải có |
| `src/core/infra/spark.py` | Sửa — ưu tiên env `SPARK_MASTER_URL` | Phải có |
| `config/config.yml` | Sửa — `SPARK_MASTER_URL`, `spark.sql.shuffle.partitions: 12` | Phải có |
| `Makefile` | Sửa — thêm `build-spark-worker` target | Nên có |
| `.env` | Sửa — thêm `SPARK_MASTER_URL=local[*]` (default cho dev) | Optional |

### Implementation Order

```
Phase 1: Dockerfile.spark-worker         (30 phút)
    ↓
Phase 2: docker-compose services         (30 phút)
    ↓
Phase 3: Code updates (SparkSession)     (30 phút)
    ↓
Phase 4: Config.yml + Makefile           (15 phút)
    ↓
Phase 5: Deploy & verify                 (30 phút)
    ↓
Phase 6: Run benchmark                   (15 phút)
```

**Tổng thời gian ước tính:** ~2.5 giờ

### Flowchart Quyết Định Cluster vs Local

```
SparkSession.builder.getOrCreate()
    │
    ├── SPARK_MASTER_URL set? ──yes──→ .master(SPARK_MASTER_URL)
    │                                      │
    │                                      ├── spark://... → Cluster mode
    │                                      └── local[*]    → Local mode (fallback)
    │
    └── no SPARK_MASTER_URL ────────────→ .master("local[*]")
                                           (giống behavior hiện tại)
```

Code xử lý:

```python
import os

MASTER_URL = os.getenv("SPARK_MASTER_URL", "local[*]")

# Mọi SparkSession.builder đều gọi:
spark = SparkSession.builder.master(MASTER_URL)...
```

Pattern này đảm bảo:
- **Dev không có cluster**: Chạy local như cũ (không cần start master/workers)
- **Deploy có cluster**: Chỉ cần set env `SPARK_MASTER_URL=spark://spark-master:7077`
- **Giống nhau giữa các file**: Mọi SparkSession đều đọc từ 1 nguồn

---

## Tham Khảo

- `config/config.yml` — Global spark configuration
- `src/core/infra/spark.py` — SparkService (config-driven pattern)
- `src/streaming/spark_streaming_job.py` — Spark streaming job (cần sửa)
- `src/batch/funnel_analysis.py` — Batch analytics job (cần sửa)
- `src/batch/seed_popular_items.py` — Popular items seeding (cần sửa)
- `docker-compose.yml` — Service definitions (cần thêm master/workers)
- `docs/improvement_proposal/improvement_proposal_v4.md` — Performance optimization (v4)
- `Dockerfile.spark-worker` — New file (worker image)
- `Makefile` — Build targets (cần sửa)
- Bitnami Spark image docs: https://hub.docker.com/r/bitnami/spark

---

## Changelog

| Version | Date | Description |
|---------|------|-------------|
| v5 | 2026-05-26 | Spark Standalone Cluster — multi-worker proposal |
