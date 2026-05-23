# Bug Report v2 — OTTO Recommender Pipeline

**Date:** 2026-05-20
**Version:** v2

**Scope:** Bugs còn lại sau khi đã fix toàn bộ 8 bugs từ `bug_report_v1.md` và implement Phase 1-5 từ `improvement_proposal_v2.md`.

---

## 1. [CRITICAL] Missing `conn.commit()` Trong `write_stats_items_from_rows`

**File:** `src/streaming/spark_streaming_job.py:197-232`

### Mô tả

Hàm `write_stats_items_from_rows` thực hiện bulk UPSERT vào bảng `stats_items` nhưng **thiếu `conn.commit()`**. Kết quả: tất cả dữ liệu item insights (click-to-cart rate, click-to-order rate, cart-to-order rate per item) bị rollback khi connection đóng → bảng `stats_items` luôn rỗng → tab "Item Insights" trên dashboard không bao giờ có data.

### Root cause

So sánh với các hàm write khác trong cùng file:

| Hàm | Có `conn.commit()`? | Status |
|-----|---------------------|--------|
| `write_stats_hourly_from_rows` | ✅ (line 139) | OK |
| `write_anomaly_logs_from_rows` | ✅ (line 160) | OK |
| `write_popular_items_from_rows` | ✅ (line 186) | OK |
| `write_stats_items_from_rows` | ❌ | **BUG** |
| `write_advanced_funnel_from_rows` | ✅ (line 264) | OK |
| `write_stats_sessions_from_rows` | ✅ (line 297) | OK |

Hàm `write_stats_items_from_rows` có `try/finally` với `conn.close()` trong `finally`, nhưng thiếu `conn.commit()` trong `try` block. PostgreSQL với `autocommit=False` (mặc định của psycopg2) sẽ rollback toàn bộ transaction khi connection đóng.

### Cách sửa

Thêm `conn.commit()` trước khi vào `finally`:

```python
def write_stats_items_from_rows(rows):
    if not rows:
        return
    conn = psycopg2.connect(...)
    try:
        # ... bulk UPSERT logic ...
        logger.info(f"stats_items: OK ({len(values)} rows)")
        conn.commit()  # <-- THÊM DÒNG NÀY
    except Exception as e:
        logger.error(f"Error write_stats_items: {e}")
    finally:
        conn.close()
```

### Tác động

- **Trước:** Tab "Item Insights" dashboard luôn hiển thị "No item insights data yet"
- **Sau:** Dashboard hiển thị được hidden gems, conversion scatter, popularity vs conversion bubble chart
- Đây là tính năng mới được thêm trong Phase 5.4 nhưng chưa bao giờ hoạt động do bug này

---

## 2. [CRITICAL] `startingOffsets: "latest"` — Mất Events Khi Restart

**File:** `src/streaming/spark_streaming_job.py:546`

### Mô tả

Streaming job cấu hình `startingOffsets: "latest"` → khi Spark streaming job khởi động (lần đầu hoặc sau restart), nó **chỉ đọc events mới đến từ thời điểm đó**, bỏ qua tất cả events đã có trong Kafka topic.

### Tại sao nghiêm trọng

Trong production pipeline:

1. API nhận events → publish vào Kafka topic `user-events`
2. Spark streaming job consume từ Kafka → aggregate → ghi PostgreSQL
3. Nếu Spark job crash hoặc cần restart (deploy, OOM, maintenance):
   - Events đã có trong Kafka topic **bị bỏ qua hoàn toàn**
   - Dashboard mất data trong khoảng thời gian Spark down
   - Metrics (stats_hourly, popular_items, stats_items, advanced_funnel) không được cập nhật

### So sánh với best practices

| Setting | Behavior | Use case |
|---------|----------|----------|
| `"earliest"` | Đọc từ đầu topic | Pipeline cần xử lý toàn bộ events |
| `"latest"` | Chỉ đọc events mới | Real-time monitoring, không quan tâm history |
| Checkpoint recovery | Resume từ vị trí đã xử lý | Production-grade pipeline |

### Cách sửa

```python
raw_df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS) \
    .option("subscribe", KAFKA_TOPIC) \
    .option("startingOffsets", "earliest") \  # <-- THAY ĐỔI
    .load()
```

Với checkpointing đã được cấu hình (`spark.sql.streaming.checkpointLocation`), Spark sẽ:
- Lần đầu chạy: đọc từ đầu topic (`earliest`)
- Sau restart: resume từ checkpoint (vị trí đã xử lý cuối cùng)

### Tác động

- **Trước:** Restart Spark → mất events → dashboard gap data
- **Sau:** Restart Spark → resume từ checkpoint → không mất events
- Phù hợp với production-grade pipeline

---

## 3. [CRITICAL] `reload=True` Trong Production

**File:** `src/api/main.py:615`

### Mô tả

```python
uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True)
```

Uvicorn `reload=True` có các vấn đề:

1. **File watcher trong Docker không hoạt động đúng** — Docker container mount volume khác với local filesystem, file watcher có thể không detect changes hoặc detect sai
2. **Lifespan manager conflict** — Reload mode tạo multiple app instances, lifespan `asynccontextmanager` có thể chạy nhiều lần gây resource leak (Redis connections, Kafka producers không được cleanup đúng)
3. **Performance overhead** — File watcher scan filesystem liên tục, tăng CPU usage không cần thiết
4. **Security risk** — Trong production, reload mode cho phép code changes mà không cần rebuild/redeploy → bypass CI/CD pipeline

### Cách sửa

```python
reload = os.getenv("RELOAD", "false").lower() == "true"
uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=reload)
```

Hoặc đơn giản hơn:

```python
uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=False)
```

Trong Docker, nếu muốn hot-reload khi dev, dùng `docker-compose.dev.yml` với volume mount và restart policy.

### Tác động

- **Trước:** API có thể bị memory leak, lifespan chạy nhiều lần, CPU cao hơn cần thiết
- **Sau:** API ổn định, resource cleanup đúng, performance tốt hơn
- Dev vẫn có thể enable reload qua env var `RELOAD=true` khi cần

---

## 4. [HIGH] `MetricsListener` Connection Leak

**File:** `src/streaming/spark_streaming_job.py:52-86`

### Mô tả

```python
class MetricsListener(StreamingQueryListener):
    def onQueryProgress(self, event):
        try:
            conn = psycopg2.connect(...)
            with conn.cursor() as cur:
                cur.execute("INSERT INTO spark_metrics ...")
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error logging metrics: {e}")
```

Nếu `conn.commit()` throw exception (DB down, network error, constraint violation), `conn.close()` **không được gọi** → connection leak.

Với Spark streaming, `onQueryProgress` được gọi mỗi micro-batch (có thể mỗi 1-5 giây). Mỗi lần leak 1 connection → sau 1 giờ có thể leak 720-3600 connections → PostgreSQL `max_connections` (thường 100) bị vượt → toàn bộ hệ thống không thể connect DB.

### Cách sửa

```python
def onQueryProgress(self, event):
    conn = None
    try:
        conn = psycopg2.connect(...)
        with conn.cursor() as cur:
            cur.execute("INSERT INTO spark_metrics ...")
        conn.commit()
    except Exception as e:
        print(f"Error logging metrics: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
```

### Tác động

- **Trước:** Connection leak khi DB error → PostgreSQL overload sau vài giờ
- **Sau:** Connection luôn được đóng, rollback khi error → hệ thống ổn định lâu dài
- Pattern này áp dụng cho TẤT CẢ các hàm write trong streaming job

---

## 5. [MEDIUM] Batch Jobs Vẫn Đọc JSONL Thay Vì Parquet

**Files:** `src/batch/funnel_analysis.py:24`, `src/batch/seed_popular_items.py:22`

### Mô tả

Cả 2 batch jobs đọc từ `datasets/otto-recommender-system/test.jsonl` (384MB, JSONL format) thay vì `datasets/otto/train_sessions.parquet` (882MB, Parquet format, 10.5M sessions).

### Tại sao nên cải thiện

| | JSONL | Parquet |
|---|-------|---------|
| Size (disk) | 384MB (test only) | 882MB (full train) |
| Schema | Phải define manually | Embedded, typed |
| Read speed | Chậm (parse JSON từng dòng) | Nhanh (columnar, compressed) |
| Data volume | 1.67M sessions (test) | 10.5M sessions (train) |
| Compression | Không | ZSTD level 3 |

Parquet format:
- Columnar storage → Spark chỉ đọc columns cần thiết
- Type information embedded → không cần define schema manually
- Compressed → I/O ít hơn
- Splitable → Spark parallelize tốt hơn

### Cách sửa

```python
# funnel_analysis.py
DATA_PATH = str(root_dir / "datasets" / "otto" / "train_sessions.parquet")

# Load trực tiếp, không cần define schema
raw_df = spark.read.parquet(DATA_PATH)

# Flatten events (schema đã có sẵn)
events_df = raw_df.select(
    col("session").alias("session_id"),
    explode("events").alias("event")
).select(
    "session_id",
    col("event.aid").alias("aid"),
    col("event.ts").alias("ts"),
    col("event.type").alias("type")
)
```

### Tác động

- **Trước:** Phân tích trên 1.67M sessions (test data, không representative)
- **Sau:** Phân tích trên 10.5M sessions (full train data, representative hơn)
- Read speed nhanh hơn 2-3x với Parquet
- Không cần maintain schema definition riêng

---

## 6. [MEDIUM] `funnel_stats` Batch Job Dùng `truncate=true`

**File:** `src/batch/funnel_analysis.py:183`

### Mô tả

```python
funnel_stats_df.write \
    .option("truncate", "true") \
    .mode("overwrite") \
    .save()
```

`truncate=true` + `overwrite` → xóa toàn bộ dữ liệu cũ trong bảng trước khi ghi dữ liệu mới. Kết quả: không thể track funnel trend over time.

### Tại sao nên cải thiện

Trong production, funnel metrics được track theo thời gian để:
- Phát hiện degradation (conversion rate giảm dần)
- Đánh giá impact của changes (A/B test, model update)
- Báo cáo trend cho stakeholders

Với truncate, chỉ có 1 row mới nhất → không thể query historical data.

### Cách sửa

Chuyển sang append-only với `computed_at` timestamp:

```python
funnel_stats_df.write \
    .format("jdbc") \
    .option("url", PG_URL) \
    .option("dbtable", "funnel_stats") \
    .options(**PG_PROPERTIES) \
    .mode("append") \  # <-- THAY ĐỔI
    .save()
```

Dashboard query row mới nhất:
```sql
SELECT * FROM funnel_stats ORDER BY computed_at DESC LIMIT 1
```

Để track trend:
```sql
SELECT computed_at, click_to_cart_rate, cart_to_order_rate 
FROM funnel_stats ORDER BY computed_at
```

### Tác động

- **Trước:** Chỉ có 1 row, không track được trend
- **Sau:** Historical data đầy đủ, có thể visualize trend
- Cần thêm cleanup job để xóa data cũ (> 90 ngày) tránh table quá lớn

---

## 7. [LOW] Dead Code — `src/trainer/main.py`

**File:** `src/trainer/main.py`

### Mô tả

File chỉ chứa:
```python
def main():
    pass

if __name__ == '__main__':
    main()
```

Không làm gì cả, không được import từ đâu, không được gọi từ docker-compose.

### Cách sửa

Xóa file hoặc implement chức năng (nếu có plan cho trainer pipeline).

### Tác động

- Codebase sạch hơn, dễ navigate
- Giảm confusion cho người đọc codebase

---

## 8. [LOW] `requirements.txt` Empty

**File:** `requirements.txt` (0 bytes)

### Mô tả

File tồn tại nhưng rỗng. Dependencies được quản lý qua `pyproject.toml` (uv). File này có thể gây confusion cho ai đó chạy `pip install -r requirements.txt`.

### Cách sửa

Xóa file hoặc generate từ pyproject.toml:
```bash
uv export > requirements.txt
```

### Tác động

- Giảm confusion
- Hỗ trợ cả pip users (nếu cần)

---

## Tổng kết

| # | Mức | File | Lỗi |
|---|-----|------|-----|
| 1 | **Critical** | `spark_streaming_job.py` | Missing `conn.commit()` → item insights không được lưu |
| 2 | **Critical** | `spark_streaming_job.py` | `startingOffsets: "latest"` → mất events khi restart |
| 3 | **Critical** | `api/main.py` | `reload=True` trong production |
| 4 | **High** | `spark_streaming_job.py` | MetricsListener connection leak |
| 5 | Medium | `funnel_analysis.py`, `seed_popular_items.py` | Đọc JSONL thay vì Parquet |
| 6 | Medium | `funnel_analysis.py` | `truncate=true` mất history |
| 7 | Low | `trainer/main.py` | Dead code |
| 8 | Low | `requirements.txt` | Empty file |

---

## Changelog

| Version | Date | Description |
|---------|------|-------------|
| v1 | 2026-05-17 | Initial bug report (8 bugs, all fixed) |
| v2 | 2026-05-20 | Remaining bugs after Phase 1-5 implementation |
