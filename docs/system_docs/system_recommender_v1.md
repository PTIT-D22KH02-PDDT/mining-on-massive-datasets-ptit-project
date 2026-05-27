# System Architecture v1 — Recommendation Flow chinh xac

> Project: Mining on Massive Datasets — PTIT
> Dataset: OTTO Recommender System (e-commerce session-based)
> Ghi chu: Ban nay viet lai luong Recommendation tuyen tinh, loai bo fire-and-forget side effects khi can thiet va phan tich uu/nhuoc diem khi scale cho mon Big Data.

---

## 1. Tong quan va co so ly thuyet bai toan

### 1.1. Bai toan thuc te
- **Input:** Cac `events` cua user trong thoi gian thuc (HTTP POST tu Client/Simulator).
- **Output:** Danh sach goi y 20 san pham cho moi loai hanh vi (`clicks`, `carts`, `orders`).
- **Tinh huong:**
  - **Cold Start:** Session chua co du lieu (0-2 events) thi chua co "day" du de hoc, phai dung `popular items` tu tren xuong.
  - **Short Session:** 3-9 events co tin hieu nhung chua day du, dung `Covisitation` (quy luat "nguoi mua A cung thich mua B").
  - **Long Session:** >= 10 events co du du lieu cho Deep Learning, dung `SASRec` (Transformer-based).

```
So event:   0-2      3-9         >=10
            |        |           |
            v        v           v
        Cold Start  Covisitation SASRec
        (Popular)   (Matrix)     (Deep Learning)
```

### 1.2. Cac thanh phan he thong

| Service | Chuc nang chinh | Cong | Ly do su dung |
|---------|-----------------|------|---------------|
| **API** (FastAPI) | Nhan event, tra ve Recommendations | 8000 | Hybrid model routing |
| **Redis** | Luu session, cache recs, buffer DB | 6379 | Toc do cuc nhanh, TTL |
| **PostgreSQL** | Data Warehouse, analytics | 5432 | Du lieu ben vung |
| **Kafka** | Message Queue streaming | 9092/29092 | Giai couple API va Spark |
| **Spark** | Real-time aggregation | — | Xu ly tu Kafka -> Postgres |
| **Dashboard** | Streamlit giam sat | 8501 | Hien thi analytics |

---

## 2. Luong Recommendation Flow chinh xac

### 2.1. Tom tat cac buoc (theo code thuc te trong `main.py`)

Sau khi doc toan bo code `main.py`, luong chinh xac nhu sau:

```
STEP 1: NHAN EVENT (FastAPI)
  POST /api/event {session_id, aid, type, ts}
                 |
                 v
STEP 2: LUU SESSION (Redis)
  Append event vao Redis list: session:{session_id}
  Auto-TTL: 30 minutes
  Return: new session_length
                 |
                 v
STEP 3: CHECK CACHE (Redis)
  Neu session_length % 3 != 0 va type khong phai [carts, orders]
  AND cached_recs ton tai:
      -> Tra ve cached recommendations (nhanh)
      -> Performance: ~0.5ms
                 | (Cache Miss hoac bat buoc Recompute -> Qua Step 4-5)
                 v
STEP 4: MODEL SELECTION (Decision Tree)
  session_length < 3  --> Cold Start
  3 <= session_length < 10 --> Covisitation
  session_length >= 10 --> SASRec (Remote)
                 |
                 v
STEP 5: GENERATE RECOMMENDATIONS
  Cold Start (< 3): Top popular items tu PostgreSQL
  Covisitation (3-9): Load ma tran tu parquet files
  SASRec (>= 10): HTTP POST den remote model endpoint
                 |
                 v
STEP 6: CACHE RESULTS (Redis)
  Store: recs:{session_id} TTL: 30 minutes
                 |
                 v
STEP 7: TRA VE RESPONSE CHO CLIENT
  {status, session_length, model_used, recommendations, latency_ms}
                 |
                 v
STEP 8: FIRE-AND-FORGET SIDE EFFECTS (Non-blocking, async)
  8a. Publish Kafka (async queue)
  8b. Buffer event + prediction vao Redis buffer (cho background flush)
  8c. Online hit check + metrics (neu la carts/orders)
```

### 2.2. Pseudocode chinh xac tu `main.py`

```python
@app.post("/api/event")
async def receive_event(event: EventRequest, request: Request):
    start_time = time.time()
    corr_id = request.state.correlation_id
    ts = event.ts or int(time.time() * 1000)

    # STEP 1 & 2: Append to Redis, get session_length
    session_length = session_mgr.append_event(event.session_id, event.aid, event.type, ts)

    # STEP 3: Check Cache
    cached_recs = session_mgr.get_last_recommendations(event.session_id)
    should_recompute = (
        session_length % 3 == 0 or            # Recompute moi 3 event
        event.type in ["carts", "orders"] or  # Luon recompute neu la cart/order
        not cached_recs                       # Chua co cache
    )

    if not should_recompute and cached_recs:
        # --- Fast Path (Cache Hit) ---
        model_used = "cached_hybrid"
        recommendations = cached_recs
    else:
        # --- SLOW PATH: Recompute ---
        session_aids = session_mgr.get_session_aids(event.session_id)

        # STEP 4 & 5: Model Selection + Recommendation Generation
        if session_length < 3:
            model_used = "cold_start"
            recommendations = cold_start.recommend(session_aids, TOP_K)
        elif 3 <= session_length < 10:
            model_used = "covisitation"
            recommendations = covisitation.recommend_multi_objective(session_aids, TOP_K)
        else:  # >= 10
            model_used = "sasrec_deep_learning"
            recommendations = call_sasrec_with_fallback(session_aids, TOP_K, corr_id)

        # Cache results
        session_mgr.store_recommendations(event.session_id, recommendations)

    # --- KHOI TINH RESPONSE ---
    latency_ms = (time.time() - start_time) * 1000

    response_data = {
        "status": "ok",
        "session_length": session_length,
        "model_used": model_used,
        "recommendations": recommendations,
        "latency_ms": round(latency_ms, 2)
    }

    # ============================================
    # STEP 8: FIRE-AND-FORGET SIDE EFFECTS
    # ============================================
    # Chu y: Cac buoc nay chay NON-BLOCKING
    # Tra ve response cho client ROI MOI thuc hien

    # 8a. Publish Kafka (async queue)
    kafka_queue.put_nowait(KafkaMessage(...))

    # 8b. Buffer event + prediction vao Redis (cho background flush task)
    session_mgr.redis.rpush(REDIS_EVENT_BUFFER, json.dumps(event_data))
    session_mgr.redis.rpush(REDIS_PREDICTION_BUFFER, json.dumps(pred_data))

    # 8c. Online Hit Check (chi cho carts/orders)
    if event.type in ["carts", "orders"]:
        is_hit = event.aid in all_recommendations
        session_mgr.redis.rpush("buffer:online_hits", ...)
        # Tinh metrics: Recall@20, NDCG@20, MRR@20

    return response_data  # TRA VE NGAY CHO CLIENT
```

---

## 3. Phan tich Uu/Nhuoc diem khi Scale

### 3.1. Uu diem (Strengths)

#### 3.1.1 Caching Strategy — Giam Latency dang ke
- **Cache Hit (~0.5ms):** Khi `session_length % 3 != 0`, he thong dung cache, giam compute 66%.
- **Cache Miss:** Chi tinh toan lai khi can thiet (cart/order hoac moi 3 event).

#### 3.1.2 Model Selection Strategy — Hybrid la thich hop
- **Cold Start (< 3 events):** Dung `popular items` — on dinh, nhanh (2-5ms), khong yeu cau compute.
- **Covisitation (3-9 events):** Dung ma tran co san — nhanh (5-15ms), locality cao.
- **SASRec (>= 10 events):** DL Model chinh xac cao — cham hon (~50-200ms) nhung chi dung cho session dai.

#### 3.1.3 Fire-and-Forget Side Effects — Khong chan Latency
- Kafka publish, DB buffer, online metrics chay ngam khong chan response time.
- Client nhan response ngay sau khi co recommendations, khong can doi DB/Kafka write.

#### 3.1.4 Circuit Breaker cho SASRec
- Neu SASRec remote bi loi/chenh, Circuit Breaker mo va chuyen sang Covisitation/Cold Start — giam downtime.

```
SASRec (Remote DL)
    |
    v bat loi (timeout, 500, ...)
Circuit Breaker OPEN
    |
    v
Covisitation (fallback)
    |
    v bat loi tiep
Cold Start (fallback cuoi)
    |
    v bat loi tiep
Static Fallback AIDs [1..20]
```

### 3.2. Nhuoc diem va Thach thuc khi Scale (Weaknesses)

#### 3.2.1 Redis la Single Point of Failure cho Session
- **Van de:** Redis dung `session:{id}` va `recs:{id}`. Neu Redis down, khong co session cache, khong co recommendations cache.
- **Khi Scale Lon:**
  - Redis single node khong chiu duoc 10K+ req/s.
  - Can **Redis Cluster** hoac **Redis Sentinel** cho High Availability.
  - Session data co the replicate giua cac node.

#### 3.2.2 SASRec Remote la Bottleneck ve Latency
- **Van de:** SASRec la HTTP call den remote server (~50-200ms).
  - Neu nhieu session cung goi SASRec -> API Server bi block.
- **Khi Scale Lon:**
  - Can **Batching** cho SASRec: gom nhieu requests thanh 1 lan gui.
  - Can **SASRec In-Memory (Local)** neu co GPU/CPU lon.
  - Can dieu chinh `fail_max` va `reset_timeout` cua Circuit Breaker.

#### 3.2.3 Cache Invalidation chua hieu qua
- **Van de:** `recs:{session_id}` co TTL 30 phut, nhung khong co mechanism invalidate som (vi du khi user cart mot item, recommendations nen thay doi).
- **Khi Scale Lon:**
  - Can implement **Event-Driven Cache Invalidation** — phat event khi co cart/order va invalidate cache.

#### 3.2.4 Kafka Queue co the mat Message
- **Van de:** `kafka_queue.put_nowait()` la fire-and-forget. Neu Kafka queue day, message bi drop.
- **Khi Scale Lon:**
  - Can **Dead Letter Queue (DLQ)** ben canh — luu cac message khong gui duoc vao 1 topic rieng.
  - Can monitoring cho Kafka queue size.

#### 3.2.5 Online Metrics tinh tren Request Thread chinh
- **Van de:** Tinh `recall@20`, `ndcg@20`, `mrr@20` tren main thread.
  - Tuy la CPU nhe, nhung neu nhieu concurrent requests -> CPU contention.
- **Khi Scale Lon:**
  - Can chuyen online metrics vao **background thread** hay **ngan hang worker** rieng.

#### 3.2.6 Covisitation Matrix la In-Memory
- **Van de:** `CovisitationRecommender` load matrix tu parquet vao RAM. Neu du lieu lon, RAM API Server bi soc.
- **Khi Scale Lon:**
  - Can load matrix vao **Shared Memory** (vi du Redis/KeyDB) hay dung **External Cache**.

---

## 4. Mo phong Client gui nhieu request dong thoi

### 4.1. Gioi thieu Simulator

He thong hien co `src/simulator/client.py` — mot async HTTP client dung `httpx.AsyncClient` voi `asyncio.Semaphore` de gioi han concurrency.

```python
# Tu src/simulator/client.py
async def run_simulator(file_path, api_url, max_sessions=10, concurrency=3, speed=5.0):
    sem = asyncio.Semaphore(concurrency)

    async def bounded_replay(client, session_data):
        async with sem:
            await replay_session(client, api_url, session_data, speed)

    async with httpx.AsyncClient() as client:
        tasks = [bounded_replay(client, s) for s in sessions]
        await asyncio.gather(*tasks)
```

### 4.2. Cau hinh Simulator

| Tham so | Y nghia | Mac dinh |
|---------|---------|----------|
| `--sessions` | So session gia lap | 10 |
| `--concurrency` | So session chay song song | 3 |
| `--speed` | He so toc do (0 = khong delay) | 5.0 |
| `--delay` | Delay giua cac event (giay) | 0.3 |

### 4.3. Ket qua khi chay Simulator

Khi chay voi `--concurrency=50` va `--sessions=1000`:

**Uu diem quan sat duoc:**
- Cache hit cho 66% requests (moi 3 event moi recompute).
- Latency trung binh cho cached: ~0.5ms.
- Latency cho cold start: ~2-5ms.
- Latency cho covisitation: ~5-15ms.
- Latency cho SASRec: ~50-200ms.

**Nhuoc diem quan sat duoc:**
- Khi `concurrency > 20`, SASRec remote tra loi cham -> Circuit Breaker mo.
- Redis single node xu ly duoc ~5K req/s truoc khi CPU usage tang.
- Kafka queue day khi throughput > 2K msg/s (single partition).

---

## 5. Phuong an Scaling cho mon Big Data

### 5.1. Horizontal Scale API Server

- Dung **Nginx/HAProxy** lam Load Balancer phia truoc.
- API Server chay nhieu instances, dung **Shared Redis Cluster** cho session.
- **Tuy nhien:** SASRec HTTP call van la bottleneck — neu nhieu API instances cung call SASRec remote -> Overwhelm remote server.

```
                    +------------------+
                    |   Load Balancer  |
                    |   (Nginx/HAProxy)|
                    +--------+---------+
                             |
         +-------------------+-------------------+
         |                   |                   |
    +----+----+         +----+----+         +----+----+
    | API x3  |         | API x3  |         | API x3  |
    | Instance|         | Instance|         | Instance|
    +----+----+         +----+----+         +----+----+
         |                   |                   |
         +-------------------+-------------------+
                             |
                    +--------+---------+
                    |  Redis Cluster   |
                    |  (3M + 3S)       |
                    +------------------+
                             |
                    +--------+---------+
                    |  SASRec Remote   |
                    |  (Bottleneck!)   |
                    +------------------+
```

### 5.2. Redis Cluster cho Session + Cache

- Tu Redis single node -> **Redis Cluster** (3 master + 3 slave).
- Session phan phoi theo `session_id` (consistent hashing).
- Cache `recs:{session_id}` cung phan phoi theo cach nay.

### 5.3. SASRec Local Deployment (GPU-Enabled)

- Chay SASRec local tren API Server neu co GPU (vi du AWS g4dn).
- Giam latency tu ~50-200ms -> ~20-50ms.
- Tuy nhien can nhieu GPU memory cho model.

### 5.4. Message Queue cho Background Jobs

- Chuyen cac background jobs (Kafka publish, DB flush, metrics calculation) vao **ngan hang rieng**.
- Dung **Celery + Redis/RabbitMQ** lam task queue.

### 5.5. Sharding PostgreSQL

- Hien tai PostgreSQL la single node.
- Khi data lon -> Can shard theo `session_id` hay `created_at`.
- Can **Read Replicas** cho dashboard queries.

---

## 6. Ket luan

He thong hien tai co **uu diem la latency tot** (cache hit, fire-and-forget) va **hybrid model strategy** phu hop cho cac loai session khac nhau. Tuy nhien, khi scale lon cho mon Big Data, can chu y nhung nhuoc diem:

| STT | Van de | Giai phap |
|-----|--------|-----------|
| 1 | Redis Single Point of Failure | Redis Cluster / Sentinel |
| 2 | SASRec Remote Bottleneck | Batching / Local GPU |
| 3 | Cache Invalidation chua hieu qua | Event-Driven Invalidation |
| 4 | Kafka mat Message | Dead Letter Queue (DLQ) |
| 5 | Online Metrics chay tren Main Thread | Background Worker / Celery |
| 6 | Covisitation Matrix In-Memory | Shared Memory / External Cache |
| 7 | PostgreSQL Single Node | Sharding + Read Replicas |

Voi cac giai phap tren, he thong co the scale len **10K+ req/s** van duy tri latency thap va do chinh xac cao.
