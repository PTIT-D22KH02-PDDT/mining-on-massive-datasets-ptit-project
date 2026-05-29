# De xuat cai tien v2: Read-Path / Write-Path tach biet + Precomputed Parquet + Redis Covisitation

> **Du an:** Mining on Massive Datasets – PTIT
> **Nguoi cap nhat:** User
> **Phien ban:** v2
> **Muc tieu:** 
> - **Read-Path**: Tra recs ngay tu Redis sau khi append event (<5ms), khong tinh model inline.
> - **Write-Path**: Background async recompute khi can, luu ket qua vao Redis cache.
> - **Precomputed Parquet**: Chi popular items va covisitation matrix duoc tinh 1 lan roi luu thanh parquet.
> - **Redisc Covisitation**: Tai lifespan, load covisitation parquet vao Redis. Read-Path chi can tra item tu Redis.
> - **Transition Rule**: Session < 5 events dung covisitation (Redis). Session >= 5 events cho qua model (SASRec) ngay.

---

## 1. Luong hoat dong moi (Flow v2)

### 1.1. Sequence Diagram day du

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  Client  │     │ FastAPI  │     │  Redis   │     │ Background│     │ SASRec   │
│          │     │ Server   │     │  Cache   │     │  Worker   │     │ Remote   │
└────┬─────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘
     │                │                │                │                │
     │ POST /api/event│                │                │                │
     │ (session_id,   │                │                │                │
     │  aid, type)    │                │                │                │
     │───────────────>│                │                │                │
     │                │                │                │                │
     │                │ RPUSH session  │                │                │
     │                │────────────────>│                │                │
     │                │                │                │                │
     │                │ HGET recs:{id} │                │                │
     │                │────────────────>│                │                │
     │                │                │                │                │
     │                │ HGET covis:aid │                │                │
     │                │  OR            │                │                │
     │                │ HGET popular:{type}│            │                │
     │                │────────────────>│                │                │
     │                │                │                │                │
     │                │ HGET popular:all│                │               │
     │                │────────────────>│                │               │
     │                │                │                │                │
     │                │ RETURN Response│                │                │
     │ {recommendations}, lat<=5ms    │                │                │
     │<───────────────│                │                │                │
     │                │                │                │                │
     │                │ PUSH To Queue  │                │                │
     │                │ (async)        │                │                │
     │                │─────────────────────────────────>│               │
     │                │                │                │                │
     │                │                │                │ GET session    │
     │                │                │                │────────────────>│
     │                │                │                │                │
     │                │                │                │ HSET recs:{id} │
     │                │                │                │────────────────>│
     │                │                │                │                │
     │                │                │                │ [Kafka/DB...]  │
     │                │                │                │                │

```

### 1.2. Luong Read-Path (Tang A) -- Tuyen tinh, cuc nhanh

```python
@app.post("/api/event")
async def receive_event(event: EventRequest, request: Request):
    # B1: Append event vao Redis session
    session_length = session_mgr.append_event(...)
    
    # B2: Doc recs tu Redis cache
    recs = session_mgr.get_last_recommendations(event.session_id)
    
    if recs:
        # Cache HIT -- tra recs cu (co the stale)
        return recs
    else:
        # Cache MISS:
        #   session_length < 5: tra covisitation tu Redis
        #   session_length >= 5: tra popular items (doi SASRec tinh)
        if session_length < 5:
            recs = get_covisitation_from_redis(event.aid, top_k=20)
        else:
            recs = get_popular_items_from_redis(event.type, top_k=20)
        return recs
    
    # B3: Push vao background queue (non-blocking)
    background_queue.put_nowait(event)
```

### 1.3. Luong Write-Path (Tang B) -- Async Background Worker

```python
async def background_worker(queue: asyncio.Queue):
    while True:
        event = await queue.get()
        session_aids = session_mgr.get_session_aids(event.session_id)
        session_length = len(session_aids)
        
        if session_length >= 5:
            # Chi SASRec khi session >= 5
            recs = call_sasrec_with_fallback(session_aids, TOP_K)
            session_mgr.store_recommendations(event.session_id, recs)
        elif session_length > 0:
            # Covisitation tu Redis (da load tai startup)
            recs = get_covisitation_from_redis_multi(session_aids, TOP_K)
            session_mgr.store_recommendations(event.session_id, recs)
        
        # Sau do: KAFKA + DB (fire-and-forget)
        await kafka_queue.put_nowait(...)
```

---

## 2. Xu huong ma tran Covisitation: Thiet ke Precomputed Parquet

### 2.1. Giai doan 1: Offline Compute -- Sinh file Parquet

**Muc dinh**: Tinh toan ma theo ma tran covisitation 1 lan, luu thanh parquet de lifespan load vao Redis.

**Input**: `train_parquet/*.parquet` (lich su event OTTO)

**Output**: 
- `datasets/covisitation_matrix.parquet` -- Mo hinh: (aid, related_aid, weight)
- `datasets/popular_items.parquet` -- Top items moi event type

**Thuat toan**:

```python
import pandas as pd
import numpy as np
from collections import defaultdict, Counter

def build_covisitation_matrix(parquet_dir: str, output_dir: str):
    """
    Doc toan bo train_parquet, tinh covisitation matrix roi luu parquet.
    Chi giu top_k items pho bien nhat de giam do lon file.
    """
    # B1: Doc toan bo event
    all_files = sorted(glob(f"{parquet_dir}/*.parquet"))
    df = pd.concat([pd.read_parquet(f) for f in all_files])
    
    # B2: Group theo session de tim cac item trong cung 1 session
    covis_counts = defaultdict(lambda: defaultdict(float))
    
    for session_id, group in df.groupby("session"):
        items = group["aid"].tolist()
        # Voi moi cap items trong cung session, tang weight
        for i, item_i in enumerate(items):
            for j, item_j in enumerate(items):
                if i != j:
                    covis_counts[item_i][item_j] += 1.0
    
    # B3: Chi giu top_k items pho bien nhat
    top_k = 20  # Giữ top 20 items lieä quan cho moii AID
    
    rows = []
    for aid, related in covis_counts.items():
        # Sap xep theo weight giam dan
        sorted_items = sorted(related.items(), key=lambda x: x[1], reverse=True)
        for related_aid, weight in sorted_items[:top_k]:
            rows.append({
                "aid": aid,
                "related_aid": related_aid,
                "weight": weight
            })
    
    # B4: Luu parquet
    covis_df = pd.DataFrame(rows)
    covis_df.to_parquet(f"{output_dir}/covisitation_matrix.parquet", index=False)
    print(f"Saved {len(covis_df)} rows to covisitation_matrix.parquet")


def build_popular_items(parquet_dir: str, output_dir: str):
    """
    Tinh top popular items cho click, cart, order.
    """
    all_files = sorted(glob(f"{parquet_dir}/*.parquet"))
    df = pd.concat([pd.read_parquet(f) for f in all_files])
    
    popular = {}
    for event_type in ["clicks", "carts", "orders"]:
        event_items = df[df["type"] == event_type]["aid"].value_counts()
        top_items = event_items.head(20).index.tolist()
        popular[event_type] = top_items
    
    # Luu parquet
    popular_df = pd.DataFrame([
        {"event_type": et, "items": items} 
        for et, items in popular.items()
    ])
    popular_df.to_parquet(f"{output_dir}/popular_items.parquet", index=False)
```

### 2.2. Giai doan 2: Lifespan -- Load Parquet vao Redis

**Muc tieu**: Khoi dong API server, load du lieu vao Redis 1 lan.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... khoi tao Redis, DB ...
    
    # === LOAD COVISITATION MATRIX VAO REDIS ===
    logger.info("Loading covisitation matrix into Redis...")
    covis_df = pd.read_parquet("datasets/covisitation_matrix.parquet")
    
    # So items can load vao RAM
    r = session_mgr.redis
    pipe = r.pipeline()
    count = 0
    
    for aid, group in covis_df.groupby("aid"):
        # Chuyen thanh dict: related_aid -> weight
        related_items = group.set_index("related_aid")["weight"].to_dict()
        
        # Luu vao Redis Hash hoac String JSON
        pipe.hset(f"covis:{aid}", mapping=related_items)
        count += 1
        
        # Pipeline batch de giam so lan round-trip
        if count % 1000 == 0:
            pipe.execute()
            pipe = r.pipeline()
    
    pipe.execute()
    logger.info(f"Loaded {count} items into Redis covisitation matrix.")
    
    # === LOAD POPULAR ITEMS VAO REDIS ===
    logger.info("Loading popular items into Redis...")
    popular_df = pd.read_parquet("datasets/popular_items.parquet")
    
    for _, row in popular_df.iterrows():
        event_type = row["event_type"]
        items = row["items"]
        r.setex(f"popular:{event_type}", 3600, json.dumps(items))
    
    logger.info("Popular items loaded.")
    
    yield
    # ... cleanup ...
```

---

## 3. Read-Path chi tiet (Tang A): Chi tra item, khong tinh toan

### 3.1. Nguyen tac vang

1. **Khong tinh toan trong Read-Path**: Chi doc Redis, tra ngay.
2. **Khong ket noi DB/PostgreSQL**: Toan bo du lieu trong Redis.
3. **Transition Rule**: 
   - Session < 5 events: Tra covisitation tu Redis.
   - Session >= 5 events: Tra popular items (doi SASRec tinh)."

### 3.2. Pseudocode Read-Path

```python
@app.post("/api/event", response_model=EventResponse)
async def receive_event(event: EventRequest, request: Request):
    start_time = time.time()
    corr_id = getattr(request.state, "correlation_id", "-")
    ts = event.ts or int(time.time() * 1000)

    # --- 1. APPEND EVENT ---
    session_length = session_mgr.append_event(
        event.session_id, event.aid, event.type, ts
    )

    # --- 2. DOC REDIS (chi doc, khong tinh) ---
    recs = session_mgr.get_last_recommendations(event.session_id)
    
    if recs:
        # Cache HIT
        model_used = "cached"
    else:
        # Cache MISS -- chon theo session_length
        if session_length < 5:
            model_used = "covisitation_redis"
            # Tra top related items cua event.aid tu Redis
            recs = get_covisitation_from_redis(event.aid, top_k=20)
        else:
            # Session >= 5 events => tra popular items, doi SASRec
            model_used = "popular_pending_model"
            recs = get_popular_items_from_redis(event.type, top_k=20)
    
    # --- 3. TRA RESPONSE NGAY ---
    latency_ms = (time.time() - start_time) * 1000
    response = EventResponse(
        status="ok",
        session_length=session_length,
        model_used=model_used,
        recommendations=recs,
        latency_ms=round(latency_ms, 2),
    )
    
    # --- 4. PUSH VAO BACKGROUND QUEUE ---
    # Chi push neu can recompute
    should_recompute = (session_length >= 5) or (session_length % 3 == 0) or (event.type in ["carts", "orders"])
    if should_recompute:
        await background_queue.put({
            "session_id": event.session_id,
            "session_length": session_length,
            "event_aid": event.aid,
            "event_type": event.type,
            "ts": ts,
        })
    
    return response


# --- Helper functions ---

def get_covisitation_from_redis(aid: int, top_k: int = 20) -> List[int]:
    """Doc ma tran covisitation tu Redis tra ve top items."""
    r = session_mgr.redis
    data = r.hgetall(f"covis:{aid}")
    
    if not data:
        return []
    
    # Sap xep theo weight giam dan
    sorted_items = sorted(data.items(), key=lambda x: float(x[1]), reverse=True)
    return [int(item) for item, _ in sorted_items[:top_k]]


def get_popular_items_from_redis(event_type: str, top_k: int = 20) -> Dict[str, List[int]]:
    """Doc popular items tu Redis."""
    r = session_mgr.redis
    popular_data = r.get(f"popular:{event_type}")
    
    if popular_data:
        items = json.loads(popular_data)
        return {
            "clicks": items.get("clicks", []),
            "carts": items.get("carts", []),
            "orders": items.get("orders", []),
        }
    
    # Fallback rong
    return {"clicks": [], "carts": [], "orders": []}
```

---

## 4. Write-Path chi tiet (Tang B): Background Async Worker

### 4.1. Nguyen tac Worker

1. **Lay event tu queue**, lay session tu Redis.
2. **Model selection** dựa vào `session_length`:
   - `session_length < 5` -- Covisitation từ Redis (da san co).
   - `session_length >= 5` -- SASRec Remote call (heavy compute).
3. **Luu ket qua** vao Redis cache.
4. **Kafka + DB** -- fire-and-forget sau khi luu cache.

### 4.2. Worker Code

```python
async def background_worker(queue: asyncio.Queue):
    while True:
        event = await queue.get()
        session_id = event["session_id"]
        
        try:
            # B1: Lay session tu Redis
            session_aids = session_mgr.get_session_aids(session_id)
            session_length = len(session_aids)
            
            # B2: Tuanthe luat Transition Rule
            if session_length >= 5:
                # Cho qua SASRec model
                model_used = "sasrec_deep_learning"
                recs = call_sasrec_with_fallback(session_aids, TOP_K)
            elif 1 <= session_length < 5:
                # Covisitation tu Redis
                model_used = "covisitation_redis"
                recs = covisitation_recommend_from_redis(session_aids, TOP_K)
            else:
                # Session rong
                model_used = "popular"
                recs = get_popular_items_from_redis(event["event_type"], TOP_K)
            
            # B3: Luu vao Redis cache
            session_mgr.store_recommendations(session_id, recs)
            
            # B4: Emit Kafka + Buffer DB
            await emit_kafka_and_db(event, recs, model_used)
            
        except Exception as e:
            logger.error(f"[Worker] Error processing session {session_id}: {e}")


def covisitation_recommend_from_redis(session_aids: List[int], top_k: int = 20) -> Dict[str, List[int]]:
    """
    Tu session_aids, lay tat ca related items tu Redis Hash.
    
    Giong nhu `recommend_multi_objective()` nhung chi doc Redis.
    """
    scores = defaultdict(float)
    
    # Doc covisitation tu Redis cho moi item trong session
    for aid in session_aids:
        data = session_mgr.redis.hgetall(f"covis:{aid}")
        if data:
            for related_aid, weight in data.items():
                scores[int(related_aid)] += float(weight)
    
    # Loai bo chinh minh
    for aid in session_aids:
        scores.pop(aid, None)
    
    # Top-k
    sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_items = [item for item, _ in sorted_items[:top_k]]
    
    return {"clicks": top_items, "carts": top_items, "orders": top_items}
```

---

## 5. Tinh huong dac biet trong v2

### 5.1. Session vua moi vua du < 5 events

```
Event 1 (click) -> Read-Path: tra covisitation tu Redis cho aid 123
                    -> Background: tinh lai covis session cho aid 123, update recs

Event 2 (click) -> Read-Path: neu cache chua co, tra covisitation tu Redis cho aid mới
                    -> Background: tinh lai covis session cho new aid, update recs

Event 3, 4     -> Tuong tu

Event 5        -> Read-Path: tra popular items (vi session >= 5)
                    -> Background: call SASRec, update recs
```

### 5.2. Xu ly khi Redis chua co covis:aid (cold start item)

```python
def get_covisitation_from_redis(aid: int, top_k: int = 20) -> List[int]:
    data = session_mgr.redis.hgetall(f"covis:{aid}")
    if not data:
        # Redis chua co -> tra popular items
        return get_popular_items_from_redis("clicks", top_k)
    
    # Sap xep va tra top_k
    sorted_items = sorted(data.items(), key=lambda x: float(x[1]), reverse=True)
    return [int(item) for item, _ in sorted_items[:top_k]]
```

### 5.3. Xu ly khi SASRec loi

```python
def call_sasrec_with_fallback(session_aids, top_k, request_id="-"):
    try:
        return sasrec.recommend_multi_objective(session_aids, top_k)
    except Exception as e:
        # Fallback ve covisitation tu Redis (da san co)
        logger.warning(f"SASRec failed, fallback to covisitation from Redis")
        return covisitation_recommend_from_redis(session_aids, top_k)
```

---

## 6. Performance So sanh: v1 vs v2

| Chi so | v1 (Inline compute) | v2 (Precomputed Parquet + Redis) | Giai thich |
|---|---|---|---|
| Read-Path Latency (cache hit) | ~0.5ms | **~0.5ms** | Giong nhau |
+| Read-Path Latency (cache miss, <5 events) | 5-15ms (covis disk) | **~1-2ms** (covis Redis) | Covis trong Redis, khong cham disk |
| Read-Path Latency (cache miss, >=5 events) | 50-200ms (SASRec inline) | **~1-2ms** (popular) + background SASRec | Tra popular ngay, SASRec async |
| Write-Path Latency | Inline trong request | **Async background** | Khong anh huong client |
| Database Calls (Read-Path) | Co (get popular, covis) | **KHONG** | Tat ca du lieu trong Redis |
| Disk I/O (Read-Path) | Co (parquet files) | **KHONG** | Chich file parquet 1 lan tai startup |
| Startup Time | Nhanh | Cham hon (load Redis) | Chi 1 lan tai lifespan |
| Do phuc tap | Don gian | Trung binh | Them precompute + load Redis |

---

## 7. Danh sach file can trien khai

### 7.1. Offline Compute Scripts (1 lan)

```
scripts/
├── compute_covisitation.py       # Tinh covis matrix -> parquet
├── compute_popular_items.py      # Tinh popular -> parquet
└── README.md                     # Huong dan chay
```

### 7.2. Source Code Updates

```
src/
├── api/
│   ├── main.py                  # Read-Path update + lifespan load Redis
│   ├── session_manager.py       # Them get_covisitation_from_redis()
│   └── background_worker.py    # Write-Path async worker
├── serving/
│   ├── covisitation_recommender.py  # Them recommend_from_redis()
│   └── ...
└── ...
```

### 7.3. Data Files (Precomputed)

```
datasets/
├── covisitation_matrix.parquet   # Ma tran covisitation
├── popular_items.parquet         # Top popular items
└── ... (train/test parquet giu nguyen)
```

---

## 8. Ket luan

De xuat v2 tren giai quyet:

1. **Read-Path cuc nhanh**: Chi doc Redis, khong cham DB hay disk.
2. **No DB dependency on read**: Toan bo du lieu popular + covisitation duoc tinh offline va luu vao Redis.
3. **Transition Rule ro rang**: 
   - Session < 5 events: covisitation tu Redis.
   - Session >= 5 events: SASRec model (async).
4. **Offline compute 1 lan**: Chi can chay 1 lan de sinh parquet, sau do lifespan tu dong load.
5. **Khong can giu file parquet tron` khi server dang chay** -- chi can Redis du chua.
