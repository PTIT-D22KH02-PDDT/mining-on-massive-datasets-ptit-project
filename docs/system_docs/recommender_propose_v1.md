# De xuat cai tien: Luong Recommendation 2-tang – Read-Path & Write-Path tach biet

> **Du an:** Mining on Massive Datasets – PTIT  
> **Ngay cap nhat:** 2026-05-26  
> **Tac gia de xuat:** Nguoi dung (Y tuong goc)  
> **Phan tich & ghi chep:** AI Assistant  
> **Phien ban:** v1  
> **Muc tieu:** Tu du hien tai (hybrid 3-model inline) thanh 2 luong tach biet:  
> **(A) Online Serving (read-only, <5ms)** + **(B) Background Compute (async, model-heavy)**

---

## 1. Dong luc & Van de can giai quyet

### 1.1. He thong hien tai (Baseline)

Hien tai nhu trong `system_achitecture.md` va `main.py`, API endpoint `/api/event` thuc hien **tat ca trong 1 request thread**:

```
Client POST -> API -> Redis append (blocking)
                      -> Check cache (blocking)
                      -> Recompute? -> Cold Start / Covisitation / SASRec (blocking, synchronous)
                      -> Cache write (blocking)
                      -> Return Response
                      -> (sau do) Kafka publish (non-blocking but still on main thread before return)
                      -> (sau do) Buffer to Redis (non-blocking)
```

**Thoi gian xu ly trung binh (theo mode):**

| Model | Latency | Tan suat goi |
|-------|---------|--------------|
| Cache Hit | ~0.5ms | ~66% requests |
| Cold Start | 2-5ms | Session < 3 events |
| Covisitation | 5-15ms | Session 3-9 events |
| SASRec (Remote) | 50-200ms | Session >= 10 events |
| Kafka Publish | ~2-10ms (async) | 100% requests |
| Buffer Write | ~1-3ms (async) | 100% requests |

### 1.2. Nut that (Bottleneck)

1. **SASRec Remote (~50-200ms)** giu chan request thread de cho DL model xu ly.
2. **Kafka + Buffer Write** tuy async nhung van chay tren main event loop, gay gian doan nho.
3. **CPU contention** khi tinh Online Metrics (`recall@20`, `NDCG@20`, ...). code hien tai:
   ```python
   all_recs_list = recommendations["clicks"] + recommendations["carts"] + recommendations["orders"]
   eval_metrics = {
       "recall@20": recall_at_k(all_recs_list, ground_truth, k=20),
       "ndcg@20": ndcg_at_k(...),
       "mrr@20": mrr_at_k(...),
   }
   ```
   Day deu la CPU-bound operations chay tren main thread.

### 1.3. Muc tieu moi: P95 < 5ms

| Chi so | Hien tai | Muc tieu |
|--------|----------|----------|
| P50 Latency | ~0.5ms (cache) ~10ms (miss) | <2ms (cache), <5ms (miss) |
| P95 Latency | ~100ms (khi SASRec chan) | <5ms luon |
| Throughput | ~1000 req/s (single instance) | ~5000-10000 req/s |
| Offline Compute | Inline (chan request) | Async worker rieng |

---

## 2. De xuat: 2-Luong Recommendation (Read-Path & Write-Path)

### 2.1. Tom tat kien truc 2-Tang

```
┌───────────────────────────────────────────────────────────────────┐
│                        CLIENT / SIMULATOR                          │
└───────────────────────────────┬───────────────────────────────────┘
                                │
                                ▼ HTTP POST /api/event
┌───────────────────────────────────────────────────────────────────┐
│  TANG A: ONLINE SERVING (Write-Path)                               │
│  ──────────────────────────────────────────────────────────────   │
│  FastAPI + Redis (Read-Only)                                       │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │ Only 2 Redis calls:                                       │    │
│  │   1. RPUSH session:{id} (append, no compute)            │    │
│  │   2. GET recs:{id} (cached recs from previous compute) │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                    │
│  Return: {status, recs, model_last_used, ts_cached}               │
│  Latency target: <2ms (99th percentile)                           │
│                                                                    │
│  NO model execution (no Cold Start, no Covisitation, no SASRec)    │
│  NO Kafka call                                                     │
│  NO PostgreSQL interaction                                         │
└──────────────────┬────────────────────────────────────────────────┘
                   │
                   │ sau khi tra response
                   │
                   ▼
┌───────────────────────────────────────────────────────────────────┐
│  ASYNC WORKER (Write-Path)                                         │
│  ──────────────────────────────────────────────────────────────   │
│  Luong xu ly background, khong anh huong den client latency       │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │ Receive event from internal queue                         │    │
│  │   -> Route to correct model (Cold/Covisitation/SASRec)   │    │
│  │   -> Generate recommendations                             │    │
│  │   -> SET recs:{id} in Redis (overwrite TTL)               │    │
│  │   -> Emit to Kafka & Buffer to DB (deferred)            │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                    │
│  Latency: 2ms - 200ms (OK vi chay ngam)                            │
│                                                                    │
└───────────────────────────────────────────────────────────────────┘
```

### 2.2. Sequence Diagram day du

```asciiflow
                          +-------+      +-----------+
                          |Client |      |   Redis   |
                          +---+---+      +----+------+
                              |               |
         1. POST /api/event   |               |
         ----------------->    |               |
                              | 2. RPUSH      |
                              |    session:123|
                              |-------------->|
                              |               |
                         3. GET recs:123    |
                              |<--------------|
                              |               |
         4. Return recs       |               |
         <-----------------    |               |
                              |               |
                              +-------+-------+
                                      |
                              5. Push event
                                  to internal
                                  queue (async)
                                      |
                                      v
                    +----------------------------------+
                    |   Async Background Worker        |
                    |   (dedicated process/thread)    |
                    +----------------------------------+
                                      |
                                      v
                         +----------------------+
                         |  Routing Logic         |
                         |  (same as before)      |
                         |                        |
                         |  len < 3 -> Cold Start |
                         |  3-9 -> Covisitation    |
                         |  >=10 -> SASRec Remote  |
                         |                        |
                         |  -> Generate recs       |
                         +-----------+------------+
                                      |
                                      v
                          +----------------------+
                          |  SET recs:{id}       |
                          |  TTL=30m             |
                          +-----------+----------+
                                      |
                                      v
                          +----------------------+
                          |  Emit to Kafka       |
                          |  Buffer to DB        |
                          +----------------------+
```

### 2.3. Chi tiet Luong A: Online Serving (Write-Path)

#### 2.3.1. Pseudocode tuyen tinh

```python
# --- LUONG A: ONLINE SERVING (Write-PATH) ---
@app.post("/api/event", response_model=EventResponse)
async def online_serving(event: EventRequest) -> EventResponse:
    start = time.time()
    ts = event.ts or int(time.time() * 1000)

    # 1. LUU SESSION (Redis append — chi ghi, khong doc model)
    #    RPUSH chi tra ve length, khong cham den model
    session_length = session_mgr.append_event(event.session_id, event.aid, event.type, ts)

    # 2. LAY CACHE (chi GET, khong tinh toan)
    recs = session_mgr.get_last_recommendations(event.session_id)

    # 3. TAO RESPONSE
    # recs co the = None (cache miss) nhung van tra ve voi model_used="pending"
    latency_ms = (time.time() - start) * 1000

    return EventResponse(
        status="ok",
        session_length=session_length,
        model_used=recs.get("_model_used") if recs else "pending",
        recommendations=recs["recommendations"] if recs else {
            "clicks": [], "carts": [], "orders": []
        },
        latency_ms=round(latency_ms, 2)
    )

    # 4. (Sau return) — FIRE-AND-FORGET: push to internal background queue
    # Vi du: asyncio background task hoac dedicated queue
    background_queue.put_nowait({
        "session_id": event.session_id,
        "aid": event.aid,
        "type": event.type,
        "ts": ts,
        "session_length": session_length,
    })
```

#### 2.3.2. Logic lua chon mo hinh cho Luong A

| Dieu kien | Hanh dong |
|-----------|-----------|
| `recs` ton tai trong Redis | Tra ngay, `model_used` = cached |
| `recs` khong ton tai | Tra voi `model_used` = `"pending"` va `recommendations` = `{}` (hoac popular items fallback) |
| `session_length` vua du 1, 2, 3,... | Worker background se tinh toan va update cache |

#### 2.3.3. Fallback khi Cache MISS

Khi `recs:{session_id}` chua duoc compute (session moi hoac cache expire):

| Option | Uu diem | Nhuoc diem |
|--------|---------|------------|
| **A. Tra empty (`[]`)** | Don gian, nhanh | User khong thay gioi y gi -> UX te |
| **B. Tra popular items** (cold start) | Luon co data de hien thi | Co the khong relevant, popularity bias |
| **C. Tra recs cu (stale)** | Khong mat tin hieu | Recs cu co the khong con relevant |
| D. Block cho den khi worker xong | Chinh xac nhat | Mat loi ich cua 2-luong, chan request |

**De xuat: Chon Option B + tin hieu meta:**

```json
{
  "status": "ok",
  "session_length": 1,
  "model_used": "pending",  // hoac "cold_start"
  "recommendations": {
    "clicks": [101, 102, 103, ...],
    "carts": [201, 202, 203, ...],
    "orders": [301, 302, 303, ...]
  },
  "meta": {
    "is_pending": true,     // Client biet dang cho recs thuc
    "computed_at": null,    // Chua co
    "fallback": "popular_items"
  },
  "latency_ms": 1.23
}
```

### 2.4. Chi tiet Luong B: Background Worker (Write-Path)

#### 2.4.1. Kien truc worker

```
┌─────────────────────────────────────────────────────────────────┐
│  ASYNC BACKGROUND WORKER                                        │
│  ──────────────────────────────────────────────────────────    │
│                                                                  │
│  ┌────────────┐    ┌────────────┐    ┌──────────────────┐     │
│  |Job Queue   | -> | Dispatcher | -> | Model Workers    |     │
│  |Internal    |    | (routing)   |    | (dedicated pool) |     │
│  └────────────┘    └────────────┘    └──────────────────┘     │
│                                                          |     │
│  Queue: asyncio.Queue / Redis BRPOP / Celery / RQ     |     │
│                                                          |     │
│  Mot event duoc xu ly boi background worker:            |     │
│    1. Doc session tu Redis (get_session)                 |     │
│    2. Tinh session_length                                |     │
│    3. Chon model theo nguyen tac nhu cu                  |     │
│    4. Generate recommendations                         |     │
│    5. SET recs:{id} vao Redis (update cache)           |     │
│    6. Emit to Kafka & Buffer to DB                     |     │
└──────────────────────────┬──────────────────────────────────┘
                           |
                           v
                  ┌──────────────────┐
                  | Background Flush  |
                  | (DB + Online Hits) ├──> PostgreSQL
                  └──────────────────┘
```

#### 2.4.2. Pseudocode Background Worker

```python
import asyncio
from typing import Dict
from collections import deque

class BackgroundRecommender:
    def __init__(self, session_mgr, cold_start, covisitation, sasrec,
                 kafka_queue, max_workers=4):
        self.session_mgr = session_mgr
        self.cold_start = cold_start
        self.covisitation = covisitation
        self.sasrec = sasrec
        self.kafka_queue = kafka_queue
        self.internal_queue = asyncio.Queue()
        self.max_workers = max_workers
        self._running = False

    async def start(self):
        """Khoi dong pool of workers"""
        self._running = True
        workers = [
            asyncio.create_task(self._worker_loop(i))
            for i in range(self.max_workers)
        ]
        self._workers = workers

    async def stop(self):
        self._running = False
        for w in self._workers:
            w.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)

    async def enqueue(self, event_data: dict):
        """API thread push vao queue"""
        await self.internal_queue.put(event_data)

    async def _worker_loop(self, worker_id: int):
        """Moi worker chay vong lap xu ly"""
        while self._running:
            try:
                event = await asyncio.wait_for(
                    self.internal_queue.get(),
                    timeout=1.0
                )
            except asyncio.TimeoutError:
                continue

            session_id = event["session_id"]

            # De-duplicate: Chi process event moi nhat cua session
            # (de batching nhieu event cung session)
            # Cach de: Dung Redis SETNX voi TTL nho

            try:
                # Lay session data tu Redis
                session_aids = self.session_mgr.get_session_aids(session_id)
                session_length = len(session_aids)

                # Chon model theo session_length
                if session_length < 3:
                    model_used = "cold_start"
                    recs = self.cold_start.recommend(session_aids, TOP_K=20)
                elif 3 <= session_length < 10:
                    model_used = "covisitation"
                    recs = self.covisitation.recommend_multi_objective(session_aids, TOP_K=20)
                else:
                    model_used = "sasrec_deep_learning"
                    recs = self.sasrec.recommend_multi_objective(session_aids, TOP_K=20)

                # Luu cache (overwrite)
                self.session_mgr.store_recommendations(session_id, recs)

                # Bat dau Fire-and-Forget Side Effects:
                self.kafka_queue.put_nowait(KafkaMessage(
                    topic="user-events",
                    message={
                        "session_id": session_id,
                        **event,
                        "model_used": model_used,
                    },
                    key=str(session_id),
                ))

                # Buffer to Redis (cho background flush)
                # ... (event_data, prediction_data, online_metrics) ...

            except Exception as e:
                logger.error(f"[Worker {worker_id}] Error processing event: {e}")
                # Retry logic? DLQ?
```

---

## 3. Cac thac mac lam ro (Open Question trong De xuat)

### 3.1. Cau hoi 1: Cache MISS tai Luong A — tra gi cho client?

| Tinh huong | Hanh vi hien tai | Hanh vi 2-luong |
|------------|------------------|-----------------|
| `recs:{id}` ton tai | Dung cache, tra ngay | Dung cache, tra ngay (`model_used=cached`) |
| `recs:{id}` chua ton tai | Inline compute -> tra | **??? Tra gi?** |
| `recs:{id}` da expire | Inline compute -> tra | **??? Tra gi?** |

**Cac phuong an va phan tich:**

- **Option A: Tra empty (`{}`)**
  - Uu: Don gian, toc do nhanh nhat
  - Nhuroc: User khong co gioi y -> UX te
  - Ap dung cho: Noi bo/He thong khach quan khong quan trong UX

- **Option B: Tra popular items (cold start)**
  - Uu: Luon co data, UX o muc chap nhan duoc
  - Nhuroc: Co the khong relevant
  - Ap dung cho: E-commerce production
  - De xuat: Kem theo flag `"is_pending": true`

- **Option C: Tra recs cu (stale)**
  - Uu: Gi tin hieu sequence
  - Nhuroc: Recs cu co the da outdated
  - Ap dung cho: Session khong thay doi nhieu

- **Option D: Block cho den khi worker xong (synchronous)**
  - Uu: Chinh xac nhat
  - Nhuroc: Mat loi ich cua kien truc 2-luong, SASRec van chan
  - De xuat tranh: Tra recs cu/popular ngay, client co the poll sau

**De xuat cua toi (AI):** Chon **Option B** (cold start/popular fallback) + flag `"is_pending"`. Client co quyen biet recs nay chua phai cuoi cung.

### 3.2. Cau hoi 2: Trigger worker — moi event hay chi khi `should_recompute`?

Hien tai `main.py` co logic:
```python
should_recompute = (
    session_length % 3 == 0 or
    event.type in ["carts", "orders"] or
    not cached_recs
)
```

**Luong moi:**

| Phuong an | Moi event deu push | Chi push khi `should_recompute` |
|-----------|-------------------|-------------------------------|
| Uu diem | Don gian, khong can logic o Luong A | Tiet kiem compute (66% job bo qua cache hit) |
| Nhuoc diem | Lang phi compute | Phuc tap hon, phai duplicate logic |
| Throughput | Worker chay 100% | Worker chay ~33% |

**De xuat cua toi (AI):**

```python
# Luong A: Chi push khi CAN recompute (tiet kiem compute)
async def online_serving(event):
    session_length = session_mgr.append_event(...)
    cached_recs = session_mgr.get_last_recommendations(event.session_id)

    # Same as before:
    should_recompute = (
        session_length % 3 == 0 or
        event.type in ["carts", "orders"] or
        not cached_recs
    )

    if not should_recompute:
        # Cache hit -> Khong can push worker
        return cached_recs
    else:
        # Push to background worker
        background_queue.put_nowait({...})
        return {"status": "pending", "fallback": "popular"}
```

### 3.3. Cau hoi 3: Can Redis Lock cho race condition khong?

**Scenario:**

```
Time:  |----t0-----------|----t1-----------|----t2------------|
Event: Worker A tinh     Client B request  Worker A finish
       recs cho          GET /api/event    SET recs:123
       session:123        recs:123 = ???
       START
```

- **t0:** Worker A bat dau tinh recs cho `session:123` (SASRec, ~150ms)
- **t1:** Client B request `GET /api/event` cho cung `session:123`
  - Kiem tra `recs:123` -> chua ton tai (hoac con OLD)
  - Tra fallback (popular)
- **t2:** Worker A finish va `SET recs:123`
  - Recs moi da duoc cap nhat
  - Request tiep theo se dung recs moi

**Co can Redis lock khong?**

| Option | Giai phap | Uu diem | Nhuoc diem |
|--------|-----------|---------|------------|
| A. Khong lock | De cho 2 worker chay song song, ai write sau cung duoc | Don gian | Compute lang phi, last-write-wins khong nghiem ngat |
| B. SETNX lock | Worker kiem tra `SETNX recs:{id}_computing 1 TTL=5s` | Tranh duplicate compute | Lock co the expire som hon compute -> race condition van xay ra |
| C. Check cache truoc khi compute | Worker kiem tra lai `recs` ngay truoc khi `SET` | Giam race | Khong tranh duoc compute duplicate o 2 worker |

**De xuat cua toi (AI):** Khong can lock. Voi cache-based system, "last-write-wins" la chap nhan duoc. Thay vao do, su dung **cache warming** va **batch deduplication** trong queue.

### 3.4. Cau hoi 4: Kafka publish dat o dau — Luong A hay Luong B?

**Hien tai:** Kafka publish chay tren main event loop (sau khi tra response).

**Kien truc 2-luong:**

| Phuong an | Dat Kafka o Luong B | Giu Kafka o Luong A (async) |
|-----------|---------------------|---------------------------|
| Uu diem | Luong A pure read | Analytics real-time hon |
| Nhuoc diem | Analytics delay = queue latency + worker latency | Luong A van co overhead nho (du async) |

**De xuat cua toi (AI):** Dat Kafka o **Luong B** (sau khi worker tinh xong).

Ly do:
1. Luong A nen la pure read
2. Analytics data can co `model_used` va `recommendations` -> chi co sau khi worker xong
3. Neu can real-time monitoring, co the thieu them 1 Kafka topic cho raw events (chi co `session_id`, `aid`, `type`, `ts`)

```python
# Luong A: Khong cham Kafka
# Luong B:
async def worker_process(event):
    # Compute recs, store Redis
    # Then:
    self.kafka_queue.put_nowait(KafkaMessage(
        topic="user-events",
        message={
            "session_id": event.session_id,
            "aid": event.aid,
            "type": event.type,
            "ts": event.ts,
            "model_used": model_used,      # Can co sau compute
            "has_recs": recs is not None,
        },
        key=str(event.session_id),
    ))
```

### 3.5. Cau hoi 5: Online Metrics (Hit Rate / Recall / NDCG / MRR) tinh o dau?

**Hien tai:**
```python
# main.py (inline tren main thread)
if event.type in ["carts", "orders"]:
    is_hit = event.aid in all_recs
    recall = recall_at_k(all_recs_list, [event.aid], k=20)
    ndcg = ndcg_at_k(all_recs_list, [event.aid], k=20)
```

**Viec 2-luong:**

| Option | Put metrics o Luong B (worker) | Giu metrics tren Luong A |
|--------|-------------------------------|-------------------------|
| Du lieu co | Co | Co (recs tren Luong A co the stale) |
| Chinh xac | Cao hon (recs moi nhat) | Co the stale (recs cu) |
| Latency impact | Khong anh huong Luong A | CPU-bound, anh huong Luong A |

**De xuat cua toi (AI):**

- **Tinh metrics o Luong B** (sau khi co recs moi nhat).
- **Log recs tra cho client** vao Redis de truy van.
- **Background flush metrics** vao PostgreSQL (nhu hien tai).

```python
# Luong B: Sau khi compute và cache recs
if event.type in ["carts", "orders"]:
    # Lay recs cu tra cho client (neu co)
    old_recs = session_mgr.get_last_recommendations(session_id)

    # Tinh metrics dua tren old_recs (recs user thuc su thay)
    if old_recs:
        all_recs_list = (
            old_recs.get("clicks", []) +
            old_recs.get("carts", []) +
            old_recs.get("orders", [])
        )
        metrics = {
            "recall@20": recall_at_k(all_recs_list, [event.aid], k=20),
            "ndcg@20": ndcg_at_k(all_recs_list, [event.aid], k=20),
            # ...
        }
        # Buffer to Redis -> background flush
```

### 3.6. Cau hoi 6: Lam sao xu ly session vua vua moi vua eo?

**Scenario:** Session moi tao, chua co recs cache. Client gui event lien tuc:

```
Event 1 (click) -> Luong A: return popular_items
Event 2 (click) -> Luong A: return popular_items (chua cache)
Event 3 (click) -> Luong A: should_recompute=True -> push worker
                                    |
                                    v
                               Worker tinh recs tu ~5-15ms -> SET recs:123
                                    | (may take 50-200ms for SASRec)
Event 4 (click) -> Luong A: co cache? No (chua xong) -> return popular_items
Event 5 (click) -> Luong A: co cache? Yes! -> return recs
```

**Giai phap:**

```python
# Luong A: Kiem tra cache du bang worker status
recs = session_mgr.get_last_recommendations(session_id)
if recs is None:
    # Check xem worker da duoc khoi dong chua
    computing = session_mgr.redis.exists(f"compuing:{session_id}")
    if computing:
        # Van return popular items, nhung them flag
        return {
            "recommendations": popular_items,
            "meta": {"is_pending": True, "computing": True}
        }
    else:
        # Chua khoi dong -> vua return vua trigger worker
        background_queue.put_nowait({...})
        return {
            "recommendations": popular_items,
            "meta": {"is_pending": True, "computing": False}
        }
```

---

## 4. So sanh Hien tai vs De xuat

| Chi so | He thong hien tai | De xuat 2-Luong | Giam thieu |
|--------|-------------------|-----------------|------------|
| P95 Latency | ~100ms (khi SASRec) | <5ms | ~95% |
| Throughput | ~1000 req/s | ~5000-10000 req/s | ~5-10x |
| CPU Main Thread | Cao (model + metrics) | Cuc thap (chi Redis GET/SET) | ~99% |
| Scalability | Vertical + limited horizontal | Horizontal de dang | API stateless |
| Code Complexity | Don gian | Phuc tap hon (queue + worker) | +30% code |
| Real-time analytics | Yes | Co delay (worker latency) | ~50-200ms |

---

## 5. Uu & Nhuoc diem cua De xuat

### 5.1. Uu diem

1. **Latency cuc thap cho Read Path:** <2ms cho 99% requests
2. **Tach biet ro rang:** Online (latency-sensitive) vs Offline (throughput-sensitive)
3. **Scale horizontal de dang:** API server khong state, chi can Redis Cluster
4. **Worker co the scale doc lap:** Them worker pool, khong anh huong API
5. **Chong DoS tu nhien:** Background worker khong anh huong stability

### 5.2. Nhuoc diem & Rui ro

1. **Updated nhanh, hieu qua:** Worker co the phai xu ly backlog. Can queue monitoring va auto-scaling.

2. **Event-ordering:** Nhieu event cung session co the race. Can batching trong worker.

3. **Client phai xu ly "pending":** Client/UI can hien thi "dang tinh toan" neu `is_pending=True`.

4. **Operational complexity:** Them 1 lop (queue + worker) de van hanh va giam sat.

5. **Kafka delay:** Analytics real-time co delay bang queue latency + worker latency.

---

## 6. De xuat Buoc tiep va Khao sat Chung

### 6.1. Danh sach Vec Can Lam

| STT | Cong viec | Do uu tien | Kho kha nang |
|-----|-----------|------------|--------------|
| 1 | Chon queue technology (asyncio.Queue, Redis BRPOP, Celery, RQ, Kafka) | **Cao** | Thap |
| 2 | Implement Luong A (FastAPI online serving) | **Cao** | Trung binh |
| 3 | Implement Background Worker (routing + model) | **Cao** | Trung binh |
| 4 | Implement Cache + Fallback logic | **Cao** | Thap |
| 5 | Implement Redis lock / batch dedup | Trung binh | Thap |
| 6 | Bo sung test: benchmark latency & throughput | **Cao** | Thap |
| 7 | Giam sat: queue length, worker lag, cache hit rate | **Cao** | Thap |
| 8 | Tunning: batch size, worker count, timeout | Trung binh | Trung binh |

### 6.2. Cau hoi can Nguoi dung xac nhan

| Cau hoi | Lien quan | AI De xuat |
|---------|-----------|------------|
| Cache MISS -> tra gi? | UX | Popular items + flag is_pending |
| Push worker: moi event hay only should_recompute? | Efficiency | Only should_recompute (tiet kiem compute) |
| Can Redis Lock cho race condition? | Correctness | Khong can, last-write-wins OK |
| Kafka publish o dau? | Analytics delay | Luong B (sau worker compute) |
| Online metrics (recall/ndcg) tinh o dau? | Accuracy | Luong B + log recs tra cho client |

---

## 7. Ket luan

De xuat **2-Luong Recommendation (Read-Path & Write-Path)** la mot architectural improvement dang gia nham tu latency cua API endpoint `/api/event`. Bang cach tach biet hoan toan luong doc (nhanh, <2ms) va luong ghi (async, khong chan client), he thong se dat duoc:

- **P95 < 5ms** cho moi request (du la SASRec session di nua)
- **Throughput tang 5-10x** chi voi horizontal scaling API + Redis Cluster
- **Kha nang chiu loi tot hon** vi worker co the retry/requeue ma khong anh huong UX

**Nut then chot de trien khai thanh cong:**
1. Chon dung queue technology (toi uu: asyncio.Queue cho lightweight, Redis BRPOP cho multi-process)
2. Xac dinh fallback khi cache MISS (cold start? stale? empty?)
3. Giam sat queue length va worker lag de canh bao som

---

> **Ghi chu:** File nay la ban thao de xuat. Can thao luan va xac nhan cac cau hoi phan 3 truoc khi trien khai.
