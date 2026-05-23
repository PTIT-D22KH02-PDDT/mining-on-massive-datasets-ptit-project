# Improvement Proposal v3 — OTTO Recommender Pipeline

**Date:** 2026-05-20

**Scope:** Infrastructure, Data Management, Dashboard Polish — những cải thiện còn lại sau khi đã hoàn thành Phase 1-5 từ `improvement_proposal_v2.md`.

**Bối cảnh:** Hệ thống đã ổn định về mặt correctness (8 bugs v1 đã fix) và reliability (circuit breaker, batch writes, structured logging, online evaluation). Đề xuất này tập trung vào **production readiness** và **data management best practices**.

---

## Phase 6: Data Retention & Database Optimization

### 6.1 Data Retention Policy — Cleanup Old Data

**Files:** `postgres-init/01_create_tables.sql`, script cleanup mới

**Vấn đề:**

Các bảng `predictions_log`, `collected_events`, `spark_metrics` grow không giới hạn:

| Bảng | Growth rate | Sau 1 ngày (100 req/s) | Sau 30 ngày |
|------|-------------|------------------------|-------------|
| `predictions_log` | 1 row/request | ~8.6M rows | ~260M rows |
| `collected_events` | 1 row/event | ~8.6M rows | ~260M rows |
| `spark_metrics` | 1 row/batch/query | ~50K rows (5 queries, 2s batch) | ~1.5M rows |

Với PostgreSQL, table > 100M rows:
- Query chậm hơn (sequential scan trên table lớn)
- Vacuum/autovacework nặng hơn
- Backup/restore lâu hơn
- Disk usage tăng không giới hạn

**Tại sao cần cải thiện:**

Trong production enterprise:
- Data retention policy là **bắt buộc** (GDPR, compliance, cost management)
- Hot data (7-30 ngày gần nhất) được giữ để query
- Cold data được archive hoặc xóa
- Table size được monitor và alert khi vượt threshold

**Cách cải thiện:**

Option 1: Partitioning + DROP partition (recommended cho production)

```sql
-- Partition predictions_log theo ngày
CREATE TABLE predictions_log (
    id BIGINT,
    session_id BIGINT NOT NULL,
    model_used VARCHAR(255),
    session_length INT,
    predicted_clicks INT[],
    predicted_carts INT[],
    predicted_orders INT[],
    latency_ms FLOAT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
) PARTITION BY RANGE (created_at);

-- Tạo partition cho mỗi ngày
CREATE TABLE predictions_log_2026_05_20 PARTITION OF predictions_log
    FOR VALUES FROM ('2026-05-20') TO ('2026-05-21');

-- Cleanup: DROP partition cũ (instant, không cần DELETE)
DROP TABLE predictions_log_2026_04_20;  -- Xóa data > 30 ngày
```

Option 2: Periodic DELETE (đơn giản hơn, phù hợp project)

```sql
-- Cleanup script chạy hàng ngày
DELETE FROM predictions_log WHERE created_at < NOW() - INTERVAL '30 days';
DELETE FROM collected_events WHERE created_at < NOW() - INTERVAL '30 days';
DELETE FROM spark_metrics WHERE timestamp < NOW() - INTERVAL '7 days';
DELETE FROM online_hits WHERE timestamp < NOW() - INTERVAL '30 days';
DELETE FROM online_metrics WHERE created_at < NOW() - INTERVAL '30 days';

-- Vacuum để reclaim space
VACUUM predictions_log;
VACUUM collected_events;
VACUUM spark_metrics;
```

Cron job hoặc systemd timer:
```bash
# /etc/cron.daily/otto-cleanup.sh
psql -U otto -d otto_recommender -c "
DELETE FROM predictions_log WHERE created_at < NOW() - INTERVAL '30 days';
DELETE FROM collected_events WHERE created_at < NOW() - INTERVAL '30 days';
DELETE FROM spark_metrics WHERE timestamp < NOW() - INTERVAL '7 days';
VACUUM predictions_log;
VACUUM collected_events;
VACUUM spark_metrics;
"
```

**Tác động:**

| | Trước | Sau |
|---|-------|-----|
| Table size | Grow vô hạn | Giới hạn 30 ngày |
| Query speed | Chậm dần theo thời gian | Ổn định |
| Disk usage | Tăng liên tục | Ổn định |
| Backup time | Tăng dần | Ổn định |

---

### 6.2 Additional Indexes Cho Query Patterns

**File:** `postgres-init/01_create_tables.sql`

**Vấn đề:**

Current indexes:
```sql
idx_collected_events_session ON collected_events(session_id)
idx_predictions_log_session ON predictions_log(session_id)
idx_spark_metrics_timestamp ON spark_metrics(timestamp)
```

Missing indexes cho các query patterns phổ biến:

| Query | Column | Impact khi thiếu index |
|-------|--------|----------------------|
| `get_latency_history()` | `predictions_log(created_at DESC)` | Sequential scan trên toàn table |
| `get_model_usage()` | `predictions_log(model_used, created_at)` | Sequential scan + sort |
| `get_hourly_stats()` | `stats_hourly(window_start DESC)` | Sequential scan |
| `get_online_metrics_trend()` | `online_metrics(metric_name, created_at)` | Sequential scan + sort |
| Cleanup job | `predictions_log(created_at)`, `collected_events(created_at)` | Sequential scan để DELETE |

**Cách cải thiện:**

```sql
-- Cho latency history và cleanup
CREATE INDEX IF NOT EXISTS idx_predictions_log_created_at 
    ON predictions_log(created_at DESC);

-- Cho model usage breakdown
CREATE INDEX IF NOT EXISTS idx_predictions_log_model_used 
    ON predictions_log(model_used, created_at DESC);

-- Cho hourly stats query
CREATE INDEX IF NOT EXISTS idx_stats_hourly_window_start 
    ON stats_hourly(window_start DESC);

-- Cho online metrics trend
CREATE INDEX IF NOT EXISTS idx_online_metrics_created_at 
    ON online_metrics(metric_name, created_at DESC);

-- Cho cleanup job
CREATE INDEX IF NOT EXISTS idx_collected_events_created_at 
    ON collected_events(created_at DESC);

-- Cho online_hits cleanup
CREATE INDEX IF NOT EXISTS idx_online_hits_timestamp 
    ON online_hits(timestamp DESC);
```

**Tác động:**

- Query speed cải thiện 10-100x cho các bảng lớn
- Cleanup job chạy nhanh hơn (index scan thay vì sequential scan)
- Dashboard load nhanh hơn

---

## Phase 7: Docker & Infrastructure Optimization

### 7.1 Docker Health Checks

**File:** `docker-compose.yml`

**Vấn đề:**

Docker Compose hiện tại không có health checks cho bất kỳ service nào. Khi một service crash:
- Docker không biết → không restart tự động
- Các service phụ thuộc vẫn cố connect → cascade failure
- Không có visibility vào service health từ Docker perspective

**Tại sao cần cải thiện:**

Trong production enterprise:
- Health checks là **bắt buộc** cho tất cả services
- Docker/Kubernetes dùng health checks để:
  - Auto-restart unhealthy containers
  - Route traffic chỉ đến healthy instances
  - Alert khi service degraded
- Liveness probe + readiness probe pattern

**Cách cải thiện:**

```yaml
services:
  postgres:
    image: postgres:16-alpine
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U otto -d otto_recommender"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s

  redis:
    image: redis:7-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s

  kafka:
    image: docker.io/apache/kafka:4.1.1
    healthcheck:
      test: ["CMD-SHELL", "kafka-topics.sh --bootstrap-server localhost:9092 --list"]
      interval: 15s
      timeout: 10s
      retries: 5
      start_period: 60s

  api:
    build: .
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8000/api/health || exit 1"]
      interval: 15s
      timeout: 5s
      retries: 3
      start_period: 30s
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      kafka:
        condition: service_healthy
```

**Health check parameters:**

| Parameter | Meaning |
|-----------|---------|
| `interval` | Thời gian giữa 2 lần check |
| `timeout` | Thời gian tối đa cho 1 lần check |
| `retries` | Số lần fail trước khi mark unhealthy |
| `start_period` | Grace period cho service khởi động |

**Tác động:**

- Auto-restart khi service crash
- Dependencies khởi động đúng thứ tự (healthy dependencies trước)
- Docker dashboard hiển thị service health
- Dễ debug khi có incident

---

### 7.2 Resource Limits Cho Services

**File:** `docker-compose.yml`

**Vấn đề:**

Postgres và Redis đã có resource limits, nhưng API và Dashboard thì không:

```yaml
# Đã có:
postgres:
  deploy:
    resources:
      limits:
        cpus: '1.0'
        memory: 2g

redis:
  deploy:
    resources:
      limits:
        cpus: '0.5'
        memory: 1.5g

# Chưa có:
api:        # Không có limits
dashboard:  # Không có limits
spark-streaming:  # Không có limits
```

Khi không có limits:
- Service có thể consume toàn bộ CPU/memory của host
- OOM killer có thể kill services quan trọng (Postgres)
- Không thể capacity planning

**Cách cải thiện:**

```yaml
api:
  deploy:
    resources:
      limits:
        cpus: '2.0'
        memory: 2g
      reservations:
        cpus: '0.5'
        memory: 512m

dashboard:
  deploy:
    resources:
      limits:
        cpus: '1.0'
        memory: 1g
      reservations:
        cpus: '0.25'
        memory: 256m

spark-streaming:
  deploy:
    resources:
      limits:
        cpus: '4.0'
        memory: 8g
      reservations:
        cpus: '1.0'
        memory: 2g
```

**Resource allocation strategy:**

| Service | CPU limit | Memory limit | Reasoning |
|---------|-----------|--------------|-----------|
| API | 2.0 | 2GB | Handle concurrent requests, circuit breaker, Redis buffers |
| Dashboard | 1.0 | 1GB | Streamlit + Plotly rendering |
| Spark Streaming | 4.0 | 8GB | Spark driver + executors, JVM overhead |
| Postgres | 1.0 | 2GB | Database operations |
| Redis | 0.5 | 1.5GB | In-memory cache, session storage |
| Kafka | 2.0 | 2GB | Message broker |

**Tác động:**

- Không service nào chiếm hết resource của host
- OOM protection cho services quan trọng
- Capacity planning dễ dàng hơn
- Predictable performance

---

### 7.3 Multi-Stage Docker Builds

**File:** `Dockerfile` (hiện tại), proposal trong `improvement_proposal_v1.md`

**Vấn đề:**

Dockerfile hiện tại build 1 image chung cho tất cả services:

```dockerfile
FROM python:3.12-slim
# Install Java (cho Spark)
# Install ALL dependencies (cho API + Dashboard + Spark)
# Copy ALL source code
```

Result:
- Image size: ~1.5-2GB
- API image chứa Java (không cần thiết)
- Dashboard image chứa Java + Spark dependencies (không cần thiết)
- Pull/push chậm, deploy lâu

**Proposal đã có trong `improvement_proposal_v1.md`:**

Tách thành 4 Dockerfiles:

| Image | Base | Java | Size ước tính |
|-------|------|------|---------------|
| api | python:3.12-alpine | Không | ~150-200MB |
| dashboard | python:3.12-alpine | Không | ~200-250MB |
| spark-streaming | python:3.12-alpine + JRE | Có | ~280-350MB |
| setup | python:3.12-alpine + JRE | Có | ~280-350MB |

**Tổng:** ~1GB thay vì ~1.5-2GB (giảm 33-50%)

**Cách thực hiện:**

Xem chi tiết trong `docs/improvement_proposal/improvement_proposal_v1.md`.

**Tác động:**

- Image size giảm 33-50%
- Pull/push nhanh hơn
- Deploy nhanh hơn
- Security surface nhỏ hơn (API không có Java)

---

## Phase 8: Dashboard Polish

### 8.1 Lazy-Load Per Tab

**File:** `streamlit_app.py`

**Vấn đề:**

```python
# Line 73: Global Data Fetching
stats = get_stats()
```

`get_stats()` fetch TOÀN BỘ data từ API (tất cả metrics, predictions, anomalies, spark metrics, online metrics, item insights...) → response lớn (~1-5MB JSON), chậm (2-5s).

Mỗi tab chỉ cần subset:

| Tab | Data cần thiết |
|-----|----------------|
| Dashboard Overview | active_sessions, prediction_stats, model_usage, event_distribution, hit_rate_stats |
| Advanced Analytics | funnel_stats, advanced_funnel, hourly_stats, session_distribution, hit_rate_stats |
| Anomaly Detection | anomaly_logs |
| Recommendation Demo | Không cần stats |
| Spark Performance | spark_metrics |
| Model Evaluation | online_metrics_summary, online_metrics_trend |
| Item Insights | item_insights |

**Tại sao cần cải thiện:**

Trong production dashboard:
- Lazy-load là standard pattern (React, Angular, Vue đều dùng)
- Giảm API load (không phải compute data không cần thiết)
- Giảm network bandwidth
- Dashboard responsive hơn
- Mỗi tab load độc lập → tab này chậm không ảnh hưởng tab khác

**Cách cải thiện:**

```python
# Thay vì fetch toàn bộ ở đầu:
# stats = get_stats()

# Fetch per tab khi cần:
def get_tab_data(tab_name):
    """Fetch only data needed for specific tab."""
    endpoints = {
        "overview": "/api/stats",  # Có thể tạo endpoint riêng sau
        "analytics": "/api/stats",
        "anomaly": "/api/stats",
        "spark": "/api/stats",
        "evaluation": "/api/stats",
        "items": "/api/stats",
    }
    # Ideal: tạo các endpoint riêng cho mỗi tab
    # GET /api/stats/overview, GET /api/stats/spark, etc.
    return get_stats()  # Tạm thời dùng chung, optimize sau
```

Ideal long-term: tạo các endpoint riêng trong API:

```python
@app.get("/api/stats/overview")
async def get_overview_stats():
    return {
        "active_sessions": session_mgr.get_active_session_count(),
        "prediction_stats": db.get_prediction_stats(),
        "model_usage": db.get_model_usage(),
        "event_distribution": db.get_event_distribution(),
        "hit_rate_stats": db.get_hit_rate_stats(),
    }

@app.get("/api/stats/spark")
async def get_spark_stats():
    return {"spark_metrics": db.get_spark_metrics()}
```

**Tác động:**

- Dashboard load nhanh hơn (chỉ fetch data cần thiết)
- API load giảm (không phải compute data không cần thiết)
- Tab switching mượt hơn
- Scalable khi thêm nhiều tabs

---

### 8.2 Data Freshness Indicator

**File:** `streamlit_app.py`

**Vấn đề:**

Dashboard auto-refresh mỗi 5 giây nhưng không hiển thị "last updated" timestamp → user không biết data có fresh hay không, đặc biệt khi API down hoặc streaming job chậm.

**Cách cải thiện:**

```python
import time

# Global state
if "last_updated" not in st.session_state:
    st.session_state.last_updated = None

def get_stats():
    try:
        resp = requests.get(f"{API_URL}/api/stats", timeout=2)
        st.session_state.last_updated = datetime.now()
        return resp.json()
    except:
        return None

# Display freshness indicator
if st.session_state.last_updated:
    ago = (datetime.now() - st.session_state.last_updated).total_seconds()
    if ago < 10:
        st.sidebar.success(f"🟢 Data fresh ({ago:.0f}s ago)")
    elif ago < 30:
        st.sidebar.warning(f"🟡 Data stale ({ago:.0f}s ago)")
    else:
        st.sidebar.error(f"🔴 Data outdated ({ago:.0f}s ago)")
```

**Tác động:**

- User biết được data có fresh hay không
- Dễ debug khi streaming job chậm hoặc API down
- Professional hơn

---

### 8.3 Better Error Handling Trong Dashboard

**File:** `streamlit_app.py`

**Vấn đề:**

```python
def get_stats():
    try:
        resp = requests.get(f"{API_URL}/api/stats", timeout=2)
        return resp.json()
    except:  # <-- Bare except, không log gì
        return None
```

Bare `except:` catch tất cả exceptions (bao gồm KeyboardInterrupt, SystemExit) và không log error → không thể debug khi có vấn đề.

**Cách cải thiện:**

```python
import logging

logger = logging.getLogger(__name__)

def get_stats():
    try:
        resp = requests.get(f"{API_URL}/api/stats", timeout=5)
        resp.raise_for_status()  # Check HTTP status code
        return resp.json()
    except requests.exceptions.Timeout:
        logger.error("API request timeout")
        st.error("⏱️ API request timeout — check if API is running")
        return None
    except requests.exceptions.ConnectionError:
        logger.error("Cannot connect to API")
        st.error("🔌 Cannot connect to API — check if API is running")
        return None
    except requests.exceptions.HTTPError as e:
        logger.error(f"API HTTP error: {e}")
        st.error(f"❌ API error: {e.response.status_code}")
        return None
    except json.JSONDecodeError:
        logger.error("Invalid JSON response from API")
        st.error("📄 Invalid response from API")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching stats: {e}")
        st.error(f"⚠️ Unexpected error: {type(e).__name__}")
        return None
```

**Tác động:**

- User-friendly error messages
- Dễ debug với logging chi tiết
- Không catch exceptions nguy hiểm (KeyboardInterrupt, SystemExit)

---

## Phase 9: Redis Buffer TTL

### 9.1 TTL Cho Buffer Keys

**Files:** `src/api/main.py`, `src/api/session_manager.py`

**Vấn đề:**

API buffer events vào Redis lists trước khi flush vào PostgreSQL:

```python
REDIS_EVENT_BUFFER = "buffer:collected_events"
REDIS_PREDICTION_BUFFER = "buffer:predictions"
# ...
session_mgr.redis.rpush(REDIS_EVENT_BUFFER, event_data)
```

Nếu flush task fail liên tục (DB down, network error), buffer keys grow vô hạn → Redis memory overflow → OOM → toàn bộ hệ thống crash (Redis dùng cho session management + caching).

**Tại sao cần cải thiện:**

Trong production:
- Buffer phải có TTL hoặc max length
- Khi buffer đầy, events cũ phải bị drop (hoặc alert)
- Redis memory phải được monitor

**Cách cải thiện:**

Option 1: TTL cho buffer keys

```python
BUFFER_TTL_SECONDS = 3600  # 1 hour

def buffer_with_ttl(key, data):
    """Push to buffer and set TTL."""
    session_mgr.redis.rpush(key, data)
    session_mgr.redis.expire(key, BUFFER_TTL_SECONDS)
```

Option 2: Max length (LTRIM)

```python
MAX_BUFFER_SIZE = 10000

def buffer_with_limit(key, data):
    """Push to buffer and trim if too large."""
    session_mgr.redis.rpush(key, data)
    session_mgr.redis.ltrim(key, -MAX_BUFFER_SIZE, -1)  # Keep last N items
```

Option 3: Both (recommended)

```python
BUFFER_TTL_SECONDS = 3600
MAX_BUFFER_SIZE = 10000

def buffer_event(key, data):
    session_mgr.redis.rpush(key, data)
    session_mgr.redis.ltrim(key, -MAX_BUFFER_SIZE, -1)
    session_mgr.redis.expire(key, BUFFER_TTL_SECONDS)
```

**Tác động:**

- Redis memory được giới hạn
- Không OOM khi DB down lâu
- Events cũ tự động drop khi buffer đầy (graceful degradation)
- Hệ thống ổn định hơn

---

## Tổng Kết

| Phase | Impact | Effort | Priority |
|-------|--------|--------|----------|
| 6.1 Data retention policy | Cao (disk stability) | Thấp (SQL script) | Cao |
| 6.2 Additional indexes | Cao (query speed) | Thấp (SQL) | Cao |
| 7.1 Docker health checks | Cao (auto-recovery) | Thấp (compose config) | Cao |
| 7.2 Resource limits | Trung bình (stability) | Thấp (compose config) | Trung bình |
| 7.3 Multi-stage Docker | Trung bình (image size) | Trung bình (4 Dockerfiles) | Trung bình |
| 8.1 Lazy-load per tab | Trung bình (UX) | Trung bình (API changes) | Trung bình |
| 8.2 Data freshness | Thấp (UX) | Thấp | Thấp |
| 8.3 Better error handling | Trung bình (debug) | Thấp | Trung bình |
| 9.1 Redis buffer TTL | Cao (stability) | Thấp | Cao |

---

## Tham Khảo

- `docs/bug_report/bug_report_v1.md` — 8 bugs ban đầu (đã fix)
- `docs/bug_report/bug_report_v2.md` — 8 bugs còn lại
- `docs/improvement_proposal/improvement_proposal_v1.md` — Docker optimization
- `docs/improvement_proposal/improvement_proposal_v2.md` — Phase 1-5 (đã done)
---

## Changelog

| Version | Date | Description |
|---------|------|-------------|
| v1 | 2026-05-17 | Docker optimization proposal |
| v2 | 2026-05-17 | Phase 1-5: Streaming, API, Anomaly, Dashboard, Evaluation |
| v3 | 2026-05-20 | Phase 6-9: Data retention, Infrastructure, Dashboard polish |

---

## Nhật ký Thực hiện - Phase 6 Hoàn thành (2026-05-21)

### Các File Đã Chỉnh sửa

| File | Loại Thay đổi | Mô tả |
|------|---------------|-------------|
| `postgres-init/01_create_tables.sql` | Đã sửa | Thêm 6 index mới để tăng hiệu suất truy vấn |
| `postgres-init/02_cleanup_old_data.sql` | Đã tạo | Script SQL để dọn dẹp dữ liệu định kỳ |
| `postgres-init/cleanup_data.sh` | Đã tạo | Script shell wrapper cho host-side cron |
| `src/api/main.py` | Đã sửa | Thêm TTL và giới hạn kích thước buffer Redis |
| `docker-compose.yml` | Đã sửa | Thêm service `cleanup` cho chạy theo lịch |

### 6.1 Triển khai Chính sách Giữ dữ liệu

**Vấn đề:** Các bảng `predictions_log`, `collected_events`, `spark_metrics` tăng không giới hạn, đạt 260M+ bản ghi sau 30 ngày.

**Giải pháp:**
1. Tạo `postgres-init/02_cleanup_old_data.sql` với các câu lệnh DELETE:
   - `predictions_log`: DELETE WHERE created_at < 30 ngày
   - `collected_events`: DELETE WHERE created_at < 30 ngày
   - `spark_metrics`: DELETE WHERE timestamp < 7 ngày
   - `online_hits`: DELETE WHERE timestamp < 30 ngày
   - `online_metrics`: DELETE WHERE created_at < 30 ngày
   - Kèm theo VACUUM để giải phóng dung lượng đĩa

2. Thêm bảo vệ buffer Redis trong `src/api/main.py`:
   ```python
   BUFFER_TTL_SECONDS = 3600  # TTL 1 giờ
   MAX_BUFFER_SIZE = 10000    # Tối đa 10k mục mỗi buffer
   ```
   Áp dụng cho tất cả buffer: `buffer:collected_events`, `buffer:predictions`, `buffer:online_hits`, `buffer:online_metrics`

3. Thêm service cron trong `docker-compose.yml`:
   - Sử dụng image `postgres:16-alpine` với `postgresql-client` đã cài đặt
   - Chạy hàng ngày lúc 2h sáng qua crontab: `0 2 * * *`
   - Kích hoạt qua cờ `--profile cleanup`

### 6.2 Triển khai Index Bổ sung

Thêm các index vào `postgres-init/01_create_tables.sql`:

| Tên Index | Bảng | Cột | Mục đích |
|-----------|------|-----|----------|
| `idx_predictions_log_created_at` | predictions_log | (created_at DESC) | Truy vấn lịch sử độ trễ, dọn dẹp |
| `idx_predictions_log_model_used` | predictions_log | (model_used, created_at DESC) | Phân tích sử dụng model |
| `idx_stats_hourly_window_start` | stats_hourly | (window_start DESC) | Truy vấn thống kê hàng giờ |
| `idx_online_metrics_created_at` | online_metrics | (metric_name, created_at DESC) | Truy vấn xu hướng metrics |
| `idx_collected_events_created_at` | collected_events | (created_at DESC) | Hiệu suất dọn dẹp |
| `idx_online_hits_timestamp` | online_hits | (timestamp DESC) | Hiệu suất dọn dẹp |

**Hiệu quả Dự kiến:**
- Tốc độ truy vấn nhanh hơn 10-100x cho các bảng lớn
- Công việc dọn dẹp chạy nhanh hơn (index scan thay vì sequential scan)
