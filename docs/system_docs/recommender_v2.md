# System Architecture v2 — So sánh thay đổi so với v1

> Project: Mining on Massive Datasets — PTIT
> Dataset: OTTO Recommender System (e-commerce session-based)
> Mục đích: Ghi lại toàn bộ khác biệt giữa kiến trúc v1 (sync, inline compute) và v2 (async-native, Read-Path/Write-Path separation)

---

## 1. Tổng quan thay đổi kiến trúc

### 1.1. Vấn đề của v1

v1 thiết kế với các `async def` endpoint nhưng bên trong gọi synchronous library (`redis.Redis`, `requests`). Khi một request gọi SASRec remote (~50-200ms), toàn bộ event loop bị block — các request khác phải chờ. Đây là anti-pattern trong FastAPI async.

### 1.2. Giải pháp của v2

Chuyển toàn bộ runtime library sang async-native:
- `redis.Redis` → `redis.asyncio.Redis`
- `requests` / `urllib.request` → `httpx.AsyncClient`

Và tách luồng xử lý thành **Read-Path / Write-Path**:

```
Read-Path (inline, < 5ms):
  Cache HIT → trả về ngay
  Cache MISS → covisitation từ Redis → trả về ngay

Write-Path (background, 50-200ms):
  Push event vào asyncio.Queue → Worker đọc queue
  → Gọi SASRec remote (async, non-blocking)
  → Store kết quả vào Redis cache cho request sau
```

---

## 2. Thay đổi chi tiết từng thành phần

### 2.1. `session_manager.py` — từ sync sang hybrid async

| Khía cạnh | v1 | v2 |
|-----------|----|----|
| **Redis client** | `redis.Redis` (sync) | `redis.asyncio.Redis` (async runtime) |
| **Runtime methods** | `def` → blocking | `async def` → non-blocking |
| **Bulk load** | N/A | Spark + sync `redis.Redis` bên trong `foreachPartition` (giữ nguyên sync vì Spark không hỗ trợ async) |
| **Covisitation multi-AID** | Không có | Thêm `get_covisitation_recommendations()` dùng pipeline (1 round-trip), weighted scoring, exclude clicked |
| **Pipeline usage** | Không | `append_event` + `get_covisitation_recommendations` dùng pipeline |

**Chi tiết methods chuyển async:**

| Method | v1 | v2 |
|--------|----|----|
| `append_event` | `def` → sync rpush | `async def` → `await pipe.execute()` |
| `get_session` | `def` → sync lrange | `async def` → `await self.redis.lrange()` |
| `get_session_aids` | `def` | `async def` |
| `store_recommendations` | `def` → sync setex | `async def` → `await self.redis.setex()` |
| `get_last_recommendations` | `def` → sync get | `async def` → `await self.redis.get()` |
| `get_active_session_count` | `def` → sync scan | `async def` → `await self.redis.scan()` |
| `get_covisitation` | Không có (mới) | `async def` → `await self.redis.lrange()` |
| `get_covisitation_recommendations` | Không có (mới) | `async def` → `await pipe.execute()` |
| `load_covisitation_matrix` | Không có (mới) | `def` (sync) — Spark + sync Redis pipeline |

**Lưu ý:** Dòng `redis_sync.Redis.ping()` trong `__init__` (v1) đã bị xoá vì gọi instance method trên class → `TypeError`.

---

### 2.2. `sasrec_recommender.py` — từ sync requests sang async httpx

| Khía cạnh | v1 | v2 |
|-----------|----|----|
| **HTTP client** | `requests` (sync) hoặc `urllib.request` | `httpx.AsyncClient(timeout=10)` |
| **Methods** | `def` → blocking | `async def` → non-blocking |
| **Request body** | Không rõ | `{"click_sequence": ..., "k": ..., "exclude_clicked": true}` |
| **Response parsing** | Không rõ | `resp.json()["top_aids"]` |
| **Cleanup** | Không | `async def aclose()` |
| **Split strategy** | Có thể khác | `orders=[0:5], carts=[5:10], clicks=[10:top_k]` |

**Lưu ý:** Class này **chỉ hỗ trợ remote mode** — không có local model. Mọi predict đều là HTTP POST đến remote URL.

---

### 2.3. `main.py` — thay đổi lớn nhất

#### 2.3.1. Luồng `/api/event` — tách Read-Path / Write-Path

```
v1 (inline compute):
  POST /api/event
    → append_event (sync)
    → check cache (session_length % 3 == 0 OR cart/order)
    → nếu cache MISS:
        session < 3  → ColdStart (DB query)
        3-9          → CovisitationRecommender (in-memory Pandas)
        >= 10        → SASRec (HTTP sync, block event loop)
    → store_recommendations
    → Kafka publish (fire-and-forget)
    → Redis buffer event + prediction
    → Online hit check + metrics
    → return response

v2 (Read-Path / Write-Path separation):
  POST /api/event
    → await append_event (async Redis)
    → await get_last_recommendations (async Redis)
    → nếu cache HIT:
        return "cached"
    → nếu cache MISS:
        await get_session_aids (async Redis)
        await get_covisitation_recommendations (async Redis, pipeline)
        return "covisitation_redis"
    → nếu session_length >= 5:
        push event vào background_queue (asyncio.Queue)
    → return response (KHÔNG có side effects)

  Background Worker (riêng):
    → await get_session_aids (async Redis)
    → await call_sasrec_with_fallback (async httpx)
    → await store_recommendations (async Redis)
```

#### 2.3.2. Bảng thay đổi từng bước

| Bước | v1 | v2 |
|------|----|----|
| **Import SASRecRecommender** | Commented | Uncommented |
| **SessionManager** | sync redis | async redis.asyncio |
| **Cache check condition** | `session_length % 3 == 0` hoặc `type in [carts, orders]` hoặc `not cached_recs` | **Luôn** dùng cache nếu HIT. Không có forced recompute. |
| **Cold Start (< 3 events)** | `cold_start.recommend()` → DB query popular items | **KHÔNG DÙNG** — dùng covisitation Redis cho mọi session length |
| **Covisitation (3-9 events)** | `CovisitationRecommender.recommend_multi_objective()` → in-memory Pandas | `session_mgr.get_covisitation_recommendations()` → Redis pipeline |
| **SASRec (>= 10 events)** | Inline trong endpoint → block event loop 50-200ms | **Background worker** — endpoint trả về ngay, worker tính sau |
| **Session threshold** | 3 và 10 events | **5 events** (cho background queue push) |
| **Store recommendations** | Sync → ngay sau khi compute | `await` trong background worker |
| **Kafka publish** | Fire-and-forget `put_nowait()` | **Commented out** |
| **Redis buffer event/prediction** | `rpush/ltrim/expire` | **Commented out** |
| **Online hit tracking** | `rpush buffer:online_hits`, tính recall/ndcg/mrr | **Commented out** |
| **Database init** | `Database(...)` trong lifespan | **Commented out** |
| **Flush DB buffers task** | `asyncio.create_task(flush_db_buffers_task())` | **Commented out** |
| **Refresh ranks task** | `asyncio.create_task(refresh_ranks_task())` | **Commented out** |
| **ColdStartRecommender init** | `cold_start = ColdStartRecommender(db)` | **Commented out** (cold_start giữ None) |

#### 2.3.3. `call_sasrec_with_fallback` — chuyển async

```python
# v1 (sync):
def call_sasrec_with_fallback(...):
    def _call():
        result = sasrec.recommend_multi_objective(...)  # sync, blocking
    return sasrec_breaker.call(_call)

# v2 (async):
async def call_sasrec_with_fallback(...):
    async def _call():
        result = await sasrec.recommend_multi_objective(...)  # async, non-blocking
    return await sasrec_breaker.call(_call)  # await coroutine từ breaker
```

**Lưu ý về Circuit Breaker:** `pybreaker.CircuitBreaker.call()` là sync, không hiểu async function. Khi gọi `_call()` (async def), nó trả về coroutine object — breaker tưởng "success". Exception chỉ xảy ra khi coroutine được awaited (bên ngoài breaker). Kết quả: **breaker không bao giờ mở mạch**, fallback hoạt động qua try/except trong `_call` + worker. Đây là dead code, cần thay thế bằng async-compatible circuit breaker.

#### 2.3.4. Background Worker (mới)

```python
async def background_recompute_worker():
    while True:
        event = await background_queue.get()     # async wait
        session_aids = await session_mgr.get_session_aids()
        
        if session_length >= 5:
            try:
                recs = await call_sasrec_with_fallback(...)  # async HTTP
            except:
                recs = await session_mgr.get_covisitation_recommendations(...)
        else:
            recs = await session_mgr.get_covisitation_recommendations(...)
        
        await session_mgr.store_recommendations(...)  # async Redis
```

#### 2.3.5. Các endpoint khác — async issues chưa fix

| Endpoint | v1 | v2 | Trạng thái |
|----------|----|----|-----------|
| `/api/session/{id}` | Gọi sync `get_session()` | Gọi sync (thiếu `await`) | **CHƯA SỬA** — sẽ crash |
| `/api/recommend/{id}` | Gọi sync `get_session_aids()`, `get_covisitation_recommendations()`, `call_sasrec_with_fallback()`, `cold_start.recommend_empty_session()` | Gọi sync (thiếu `await`) | **CHƯA SỬA** — sẽ crash |
| `/api/stats` | Gọi sync `get_active_session_count()` | Gọi sync (thiếu `await`) | **CHƯA SỬA** — sẽ crash |
| `/api/health` | `r.ping()`, `r.info()`, `r.dbsize()` sync | Gọi sync (thiếu `await`) | **CHƯA SỬA** — sẽ crash + `db` là None |
| `/api/popular/{type}` | `db.get_popular_items_with_counts()` sync | Gọi sync | OK (sync method) |

---

### 2.4. `covisitation_recommender.py` — không còn dùng

| Khía cạnh | v1 | v2 |
|-----------|----|----|
| **Trạng thái** | Được dùng trong luồng event (3-9 events) | **KHÔNG CÒN DÙNG** trong bất kỳ luồng nào |
| **Cơ chế** | Load 3 Parquet files vào Pandas DataFrame in-memory | Thay thế bởi `session_manager.get_covisitation_recommendations()` (Redis-based) |
| **Lý do** | Tốn RAM, blocking, không scale | Redis pipeline: 1 round-trip, shared memory, TTL tự động |

File vẫn tồn tại nhưng **dead code** — không được import hay gọi trong bất kỳ luồng xử lý nào.

---

### 2.5. `cold_start.py` — chỉ dùng trong `/api/recommend`

| Khía cạnh | v1 | v2 |
|-----------|----|----|
| **Trong `/api/event`** | Dùng cho session < 3 events | **KHÔNG DÙNG** — covisitation Redis cho mọi session |
| **Trong `/api/recommend`** | Dùng cho session_length == 0 | Vẫn dùng (sync, không đổi) |
| **Init trong lifespan** | `cold_start = ColdStartRecommender(db)` | **Commented out** — `cold_start` giữ `None` |
| **Kết quả** | Hoạt động bình thường | `/api/recommend` sẽ crash nếu gọi `cold_start.recommend_empty_session()` |

---

### 2.6. `db.py` — không có init trong lifespan

| Khía cạnh | v1 | v2 |
|-----------|----|----|
| **Khởi tạo** | `Database(...)` trong lifespan với PG config | **Commented out** |
| **Giá trị global** | `db` instance | `None` |
| **Hậu quả** | Mọi endpoint gọi `db.*` đều crash | `/api/stats`, `/api/health`, `/api/popular` đều crash nếu gọi |
| **Sync/Async** | Sync (psycopg2) | Giữ nguyên sync |

---

### 2.7. `simulator/client.py` — thêm interactive mode

| Tính năng | v1 | v2 |
|-----------|----|----|
| **File-based replay** | Có | Có (giữ nguyên) |
| **Interactive mode** | Không | **Thêm mới** — `--interactive` flag |
| **Health check** | Bắt buộc | Bắt buộc (chưa có `--skip-health`) |
| **Concurrency** | `asyncio.Semaphore` | Giữ nguyên |

---

## 3. So sánh kiến trúc tổng thể

```
v1 (Inline Compute):
+------------------+     +------------------+     +------------------+
|    FastAPI       | --> |  Model Selection | --> |  SASRec (sync)   |
|  (async def)     |     |  (inline)        |     |  (block event    |
|                  |     |                  |     |   loop 50-200ms) |
+------------------+     +------------------+     +------------------+
         |                                                  |
         v                                                  v
  +------------------+                          +------------------+
  |  Redis (sync)    |                          |  Side Effects    |
  |  session + cache |                          |  Kafka + Buffer  |
  +------------------+                          +------------------+

v2 (Read-Path / Write-Path):
+------------------+     +------------------+     +------------------+
|    FastAPI       | --> |  Read-Path       |     |  Covisitation    |
|  (async def)     |     |  (inline, async) | --> |  Redis (async)   |
|  Event Handler   |     |  Cache HIT/MISS  |     |  < 5ms           |
+------------------+     +------------------+     +------------------+
         |
         | (nếu session >= 5)
         v
  +------------------+     +------------------+     +------------------+
  |  asyncio.Queue   | --> |  Background      | --> |  SASRec (async)  |
  |  (non-blocking)  |     |  Worker          |     |  httpx, non-     |
  |                  |     |  (riêng biệt)    |     |  blocking        |
  +------------------+     +------------------+     +------------------+
                                                           |
                                                           v
                                                  +------------------+
                                                  |  Redis Cache     |
                                                  |  recs:{id}       |
                                                  +------------------+
```

---

## 4. Tác động đến Performance

| Metric | v1 | v2 | Ghi chú |
|--------|----|----|---------|
| **Event endpoint latency** | 0.5-200ms (tuỳ model) | **0.5-5ms** (luôn nhanh) | Vì không gọi SASRec inline |
| **SASRec latency** | Block event loop | **Background** — không ảnh hưởng endpoint | Worker chạy song song |
| **Redis calls** | Sync → block | **Async** → non-blocking | I/O không chặn event loop |
| **Cache HIT ratio** | ~66% (mỗi 3 event recompute) | **Phụ thuộc** | Cache chỉ được tính khi worker hoàn thành |
| **Cache freshness** | Recompute mỗi 3 event hoặc cart/order | **Chậm hơn** | Worker chỉ chạy khi session >= 5, không forced recompute cho cart/order |
| **Concurrency** | Bị giới hạn bởi sync I/O | **Cao hơn** | Async-native cho phép xử lý nhiều request đồng thời |

---

## 5. Async/Sync Boundary Issues

| Vị trí | Vấn đề | Mức độ |
|--------|--------|--------|
| `main.py:349` | `await session_mgr.redis.scan(...)[1]` — await precedence sai → `coroutine[1]` | **CRASH** |
| `main.py:611` | `session_mgr.get_session(session_id)` — thiếu `await` | **CRASH** nếu gọi |
| `main.py:617,625,629,632` | `get_session_aids`, `get_covisitation_recommendations`, `call_sasrec_with_fallback` — thiếu `await` | **CRASH** nếu gọi |
| `main.py:645` | `session_mgr.get_active_session_count()` — thiếu `await` | **CRASH** nếu gọi |
| `main.py:679-684` | `r.ping()`, `r.info()`, `r.dbsize()` — thiếu `await` | **CRASH** nếu gọi health |
| `main.py:694` | `db.cursor()` — `db` là `None` | **CRASH** nếu gọi health |
| `main.py:114` | `sasrec_breaker.call(_call)` — breaker sync, async `_call` trả coroutine | **Logic sai** (breaker không mở) |
| `session_manager.py:29` (v1) | `redis_sync.Redis.ping()` — class method | **CRASH** (đã xoá trong v2) |
| `db.py` (toàn bộ) | Sync psycopg2 gọi từ async context | Block event loop |

---

## 6. So sánh Cache Invalidation

```
v1 (Inline):
  Event POST
    → append_event → session_length = 5
    → session_length % 3 != 0 → cache HIT → return "cached" (cũ)
    → KHÔNG recompute dù đã có event mới

  Vấn đề: Recommendations không được cập nhật ngay.
  Chỉ recompute khi session_length % 3 == 0 hoặc type là carts/orders.

v2 (Background):
  Event POST
    → append_event → session_length = 5
    → cache HIT → return "cached" (cũ)
    → push queue → worker chạy → await store_recommendations (mới)
    → Request tiếp theo → cache HIT (mới)

  Luồng: cache luôn cũ cho request hiện tại,
  request sau mới có kết quả mới.
```

---

## 7. So sánh Covisitation Implementation

| Khía cạnh | v1 (`CovisitationRecommender`) | v2 (`session_manager.get_covisitation_recommendations`) |
|-----------|-------------------------------|--------------------------------------------------------|
| **Data source** | 3 Parquet files → Pandas DataFrame in-memory | Redis keys `covis:{aid}` (loaded từ parquet bằng Spark) |
| **Memory** | RAM API Server (~GB) | Redis RAM (shared, không ảnh hưởng API) |
| **Scoring** | Weight từ file parquet | Inverse-rank weighting: `1/(rank+1)` |
| **Multi-AID merge** | Groupby + sort | Counter + most_common |
| **Exclude clicked** | Có | Có |
| **Round-trips** | 0 (in-memory) | 1 (Redis pipeline) |
| **Latency** | ~0.1ms (của Pandas) | ~1-2ms (Redis network) |
| **Split strategy** | 3 loại: clicks/carts/orders matrix riêng | Top 1/3 → orders, giữa → carts, dưới → clicks |

---

## 8. Các thành phần bị loại bỏ / comment

| Thành phần | Lý do |
|------------|-------|
| **Kafka publishing** | Comment — không có Kafka infrastructure trong môi trường dev |
| **Redis buffer (event + prediction)** | Comment — không có DB flush (PostgreSQL không chạy) |
| **Online hit tracking + metrics** | Comment — dependency vào DB |
| **Database initialization** | Comment — không có PostgreSQL |
| **Flush DB buffers task** | Comment — không có DB |
| **Refresh ranks task** | Comment — không có DB + cold_start |
| **ColdStartRecommender init** | Comment — không dùng trong event flow |
| **CovisitationRecommender** | Dead code — thay bởi Redis-based covisitation |

---

## 9. Trạng thái hiện tại (chạy được)

**Hoạt động:**
- `/api/event` — **OK**. Read-Path/Write-Path hoạt động.
- Background worker — **OK**. Nhận queue, gọi SASRec async, cache kết quả.
- Redis session + cache — **OK**. Async, TTL tự động.
- Redis covisitation — **OK** nếu matrix đã load (dùng test script riêng).

**Chưa hoạt động (cần sửa async):**
- `/api/session/{id}` — thiếu await
- `/api/recommend/{id}` — thiếu await + cold_start là None
- `/api/stats` — thiếu await + db là None
- `/api/health` — thiếu await + db là None
- `/api/popular/{type}` — db là None

**Cần cải thiện:**
- `pybreaker.CircuitBreaker` không async-compatible — cần thay thế
- `CovisitationRecommender` (Pandas) dead code — có thể xoá
- Health check cần sửa để pass simulator

---

## 10. Kết luận

v2 chuyển từ kiến trúc **sync-inline** sang **async-native + background processing**:

| Khía cạnh | v1 | v2 |
|-----------|----|----|
| **Event loop** | Bị block bởi sync I/O | Non-blocking hoàn toàn |
| **Recommendation latency** | 50-200ms khi dùng SASRec | Luôn < 5ms (cache hoặc covisitation) |
| **SASRec compute** | Inline, block | Background worker, async |
| **Session management** | Sync Redis | Async Redis (redis.asyncio) |
| **HTTP client** | requests/urllib (sync) | httpx.AsyncClient |
| **Covisitation** | In-memory Pandas (RAM) | Redis-based (shared, async) |
| **Side effects** | Kafka + DB buffer + metrics | Tất cả comment, chỉ giữ recommend core |
| **Cache invalidation** | Phức tạp (%3 + type check) | Đơn giản (worker ghi đè khi có kết quả) |

**Trade-off chính:** v2 đánh đổi độ tươi của recommendations (luôn cũ cho request hiện tại) để lấy tốc độ response (luôn < 5ms) và không block event loop.
