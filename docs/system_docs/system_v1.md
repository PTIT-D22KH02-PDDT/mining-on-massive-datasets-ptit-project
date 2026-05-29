# Mô tả hệ thống — Otto Recommender Pipeline
**Ngày:** 2026-05-17
**Phiên bản:** v1

---

## 1. Tổng quan

### 1.1. Bài toán

OTTO là một cuộc thi trên Kaggle về recommender system cho thương mại điện tử. Mỗi user có một session — một chuỗi các events gồm click, cart (thêm vào giỏ), và order (mua). Mục tiêu là đề xuất 20 items tiếp theo mà user có thể tương tác, cho mỗi loại event (clicks, carts, orders).

**Tại sao cần hệ thống phức tạp như vậy?**
- Dữ liệu OTTO có ~12M sessions, ~1.8M items → không thể xử lý trên 1 server đơn lẻ
- Cần vừa predict nhanh (realtime, <100ms) vừa phân tích được hành vi (analytics)
- Cold start: session mới hoàn toàn không có lịch sử
- Short session: phần lớn sessions chỉ có 1-3 events

### 1.2. Kiến trúc tổng thể

Hệ thống gồm 8 Docker containers:

| Service | Image | Port | Vai trò |
|---------|-------|------|---------|
| `api` | Python 3.12 + FastAPI | 8000 | Nhận event từ client, trả recommendations |
| `spark-streaming` | Python 3.12 + PySpark | - | Xử lý realtime events từ Kafka, ghi analytics |
| `dashboard` | Streamlit | 8501 | Dashboard giám sát |
| `setup-jobs` | Python 3.12 + PySpark + Java | - | Batch job ban đầu (chạy 1 lần) |
| `kafka` | Apache Kafka 4.1.1 | 29092 | Message queue cho realtime events |
| `postgres` | PostgreSQL 16 | 5432 | Data warehouse |
| `redis` | Redis 7 | 6379 | Session store + recommendation cache |
| `kafka-ui` | Kafka UI | 8989 | Giao diện quản lý Kafka |

**Tại sao dùng Kafka thay vì ghi thẳng vào PostgreSQL?**
- Kafka cho phép **decouple** giữa API và analytics processing
- API không bị block bởi việc xử lý analytics (bất đồng bộ - async)
- Spark có thể đọc lại từ đầu nếu cần (replay)
- Có thể mở rộng thêm consumers (evaluation, ML training) mà không cần sửa API

**Tại sao dùng Redis cho session thay vì PostgreSQL?**
- Redis có độ trễ ~1ms cho read/write, PostgreSQL ~10-50ms
- Session chỉ cần TTL đơn giản, không cần query phức tạp
- Redis List (rpush/lrange) phù hợp tự nhiên cho chuỗi events
- Nhược điểm: Redis là memory-first, nhưng với session TTL 30 phút và dữ liệu nhỏ (JSON events) thì không vấn đề

```
┌─────────────────────────────────────────────────────────────────┐
│                         Client App                               │
│                  (Mobile/Web Application)                         │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP POST /api/event
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                         API Service                              │
│  FastAPI + Redis + PostgreSQL + Kafka Producer                   │
│                                                                  │
│  1. Append event vào Redis session                              │
│  2. Publish event lên Kafka (background, non-blocking)           │
│  3. Lưu event vào PostgreSQL (background, non-blocking)          │
│  4. Hybrid recommendation engine → trả recommendations          │
│  5. Log prediction + hit rate (background)                        │
└────────────┬───────────────────────┬───────────────────────────┘
             │ Kafka: user-events     │ PostgreSQL: collected_events
             ▼                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Spark Streaming Job                          │
│                                                                  │
│  6 pipelines xử lý song song:                                    │
│  A. stats_hourly (global funnel metrics)                         │
│  B. anomaly_logs (bot detection)                                 │
│  C. popular_items (realtime popularity)                         │
│  D. stats_items (per-item performance)                          │
│  E. advanced_funnel_stats (model performance)                   │
│  F. stats_sessions (session segmentation)                        │
└────────────┬────────────────────────────────────────────────────┘
             │ PostgreSQL: 12 analytics tables
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     PostgreSQL Data Warehouse                    │
│   stats_hourly | stats_items | stats_sessions | funnel_stats     │
│   popular_items | predictions_log | anomaly_logs | spark_metrics  │
│   online_hits | evaluation_results | collected_events            │
└────────────┬────────────────────────────────────────────────────┘
             │ Dashboard reads from here
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Streamlit Dashboard                       │
│        stats, funnel, latency, hit rate, spark metrics          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Chi tiết các thành phần

### 2.1. API Service

#### 2.1.1. Event Flow chi tiết trong `/api/event`

```
Client POST /api/event
    │
    ├─ 1. session_mgr.append_event() → Redis rpush
    │     Key: session:{session_id}
    │     Value: [{"aid": 123, "type": "clicks", "ts": 1234567890}, ...]
    │     TTL: 30 phút (tự động expire session cũ)
    │
    ├─ 2. kafka_producer.send("user-events", payload) → Kafka
    │     Payload: {session_id, aid, type, ts, model_used}
    │     Key: session_id (để partition đúng session vào cùng partition)
    │
    ├─ 3. db.log_event() → PostgreSQL collected_events
    │     Lưu raw events để retrain sau này
    │
    ├─ 4. Hybrid recommendation logic
    │     ├─ session_length % 3 == 0 OR cart/order → recompute
    │     ├─ ngược lại → return cached recs từ Redis
    │     └─ model chọn dựa trên session_length:
    │          ├─ 0 event: cold_start (popular items)
    │          ├─ 1-2 events: cold_start_short (covisitation + popular)
    │          ├─ 3-9 events: covisitation (XEM 2.1.4)
    │          └─ 10+ events: sasrec_deep_learning
    │
    ├─ 5. session_mgr.store_recommendations() → Redis
    │     Key: recs:{session_id}
    │     TTL: 30 phút
    │
    ├─ 6. db.log_prediction() → PostgreSQL predictions_log
    │     {session_id, model_used, session_length, predicted_clicks/carts/orders, latency_ms}
    │
    └─ 7. Nếu action là cart/order: db.log_online_hit()
          So sánh action aid với recommendations vừa trả
```

#### 2.1.2. Hybrid Model Routing — Tại sao chọn cách này?

**Lý do chia theo session_length:**

| Session length | Hành vi user | Model phù hợp | Tại sao |
|----------------|-------------|---------------|---------|
| 0 event | Hoàn toàn mới | Cold Start (Popular) | Không có data, chỉ có thể dùng global popularity |
| 1-2 events | Rất ít lịch sử | Cold Start Short | 1-2 items không đủ cho sequential pattern, nhưng đủ để tìm items cùng mua cùng lúc |
| 3-9 events | Ngắn nhưng có signal | Covisitation | 3-9 events cho thấy user đang browse, covisitation hiệu quả để tìm items liên quan |
| 10+ events | Có đủ lịch sử | SASRec (Deep Learning) | Đủ data để học sequential pattern, SASRec tốt hơn collaborative/rule-based |

**Tại sao không dùng 1 model cho tất cả?**
- SASRec cần đủ data để học pattern, với 1-2 events thì overfit
- Covisitation không học được sequential order, chỉ work với items cùng mua
- Cold start hoàn toàn không có data để học

**Tại sao chia 3/10 làm threshold?**
- 3: minimum để covisitation có đủ pairs (session có ít nhất 2 items để tạo pair)
- 10: empirical từ SASRec paper và OTTO competition experience, đủ để model learn meaningful patterns

#### 2.1.3. Caching Strategy — Tại sao chỉ recompute mỗi 3 events?

```python
should_recompute = (
    session_length % 3 == 0 or
    event.type in ["carts", "orders"] or
    not cached_recs
)
```

**Tại sao modulo 3?**
- Recompute sau mỗi 3 events thay vì mỗi event → giảm 66% computation
- User không nhận ra sự khác biệt nếu recs chỉ thay đổi mỗi 3 events
- 3 là số nhỏ nhất mà user vẫn có trải nghiệm tương đối realtime

**Tại sao cart/order LUÔN recompute?**
- Cart/order là strong intent signals → recs phải accurate ngay
- Nếu user add to cart và recs vẫn là 3 events trước → bad UX
- Cart/order là conversion points, sai recs ở đây cost cao nhất

**Trade-offs:**
- Lợi: giảm latency, giảm compute
- Bất lợi: recs có thể stale ~2 events, user có thể thấy "lạ" recs không thay đổi ngay

#### 2.1.4. Covisitation Recommender — Tại sao không hoạt động?

**Covisitation là gì?**
Covisitation là kỹ thuật đề xuất: "Users who bought X also bought Y". Thay vì dùng ML model, ta đếm số lần 2 items xuất hiện cùng session, coi đó là similarity score.

**Tại sao cần build matrix trước?**
- Đếm pairs trên full dataset (~12M sessions) cần Spark hoặc distributed computing
- Matrix được build 1 lần, lưu vào parquet, load khi API start
- Nếu không build → matrix rỗng → fallback về cold_start

**Các loại matrix:**
- `clicks_matrix.parquet`: pairs từ click events, weighted theo thời gian (event gần đây weight cao hơn)
- `carts_orders_matrix.parquet`: pairs từ cart/order events, weights cố định (click=1, cart=6, order=3) — cart/order có intent mạnh hơn click
- `buy2buy_matrix.parquet`: pairs từ 2 cart/order events cách nhau 14 ngày → "sau khi mua A, user thường mua B tiếp"

**Weights (OTTO official):**
- Click: 1 điểm
- Cart: 6 điểm (cart = strong intent)
- Order: 3 điểm (mua = đã có quyết định)
- Buy2Buy: nhân đôi (vì repeat purchase là strong signal)

**Tại sao weights này?**
- Cart có weight cao nhất (6) vì user đã thể hiện rõ ý định mua nhưng chưa quyết định cuối
- Order weight thấp hơn cart vì đây là endpoint, không còn "next action" để predict
- Click weight thấp nhất vì click có thể accidental

#### 2.1.5. SASRec Recommender

**SASRec là gì?**
Self-Attentive Sequential Recommendation. Dùng Transformer (self-attention) để học sequential patterns từ user history.


**Cách hoạt động:**
1. API gửi session_aids (list of item IDs user đã tương tác) lên remote
2. Remote model predict top-k candidates
3. API slice kết quả: clicks[:20], carts[2:22], orders[5:25] (khác nhau để diversification)

#### 2.1.6. Cold Start Handling

**Cold start là gì?**
Khi user mới hoặc session mới, không có lịch sử để predict.

**Các cấp độ cold start:**
1. **Empty session (0 events):** Chỉ có thể dùng global popular items
2. **Short session (1-2 events):** Dùng covisitation từ 1-2 items đó, fill bằng popular items

**Tại sao popular items làm fallback?**
- Popular items có baseline accuracy cao nhất khi không có personalization
- Đảm bảo user luôn có gì để xem, không phải empty response

Tuy nhiên, sẽ có vấn đề về popularity bias, sẽ cố gắng để khắc phục ở những phiên bản sau.

### 2.2. Spark Streaming Job

#### 2.2.1. Tổng quan 6 Pipelines

**Watermark và Late Data:**
```python
events_df.withWatermark("timestamp", "2 minutes")
```
- Events đến trễ hơn 2 phút sẽ bị drop
- Chỉ áp dụng cho các pipeline có window
- 2 phút là compromise giữa data completeness và realtime

**Tại sao dùng watermark 2 phút?**
- Events trong OTTO dataset có timestamp chính xác, nhưng real-time system có network jitter
- 2 phút đủ để handle mayoría của delays mà không giữ stale state quá lâu

#### 2.2.2. Pipeline A: Global Stats (`stats_hourly`)

**Bảng `stats_hourly` lưu gì?**
| Column | Mô tả |
|--------|-------|
| `window_start` | Bắt đầu window 5 phút |
| `window_end` | Kết thúc window |
| `total_events` | Tổng số events trong window |
| `total_sessions` | Số unique sessions (approximate) |
| `total_clicks/carts/orders` | Số events theo type |
| `unique_items` | Số unique items |
| `click_to_cart_rate` | Conversion rate click → cart |
| `cart_to_order_rate` | Conversion rate cart → order |

**Tại sao cần bảng này?**
- Dashboard cần trend theo thời gian
- So sánh weekday vs weekend, morning vs evening
- Phát hiện anomalies (đột tăng/giảm traffic)

**Tại sao dùng JDBC append thay vì upsert?**
- Mỗi window là row mới, không trùng lặp
- Append simple, không cần conflict handling
- Có thể query theo time range dễ dàng

**Tại sao `approx_count_distinct` thay vì `countDistinct`?**
- `approx_count_distinct` dùng HyperLogLog algorithm, nhanh hơn nhưng có ~2% error
- Với dashboard metrics, 2% error chấp nhận được
- `countDistinct` chính xác nhưng chậm với nhiều sessions

#### 2.2.3. Pipeline B: Anomaly Detection (`anomaly_logs`)

**Bot detection logic:**
- Session nào có > 50 events trong 1 phút → likely bot
- Người dùng bình thường không thể tạo 50+ events/phút

**Tại sao dùng INSERT thay vì UPSERT?**
- Mỗi detection là event mới, không muốn update
- Có thể muốn track multiple detections của same session ở các window khác nhau
- Dùng `dropDuplicates(["session_id"])` per micro-batch để tránh spam

**Tại sao dropDuplicates per micro-batch thay vì global?**
- Global dedup cần state vĩnh viễn → unbounded state
- Per micro-batch dedup chỉ tránh duplicate TRONG CÙNG BATCH
- Same session detection ở batch khác → vẫn insert (đáng để track theo thời gian)

**Tại sao threshold = 50 events/phút?**
- Empirical: normal user browsing ~20-30 events trong 5-10 phút
- 50 events/phút = 0.83 events/sec = bot-like pace

#### 2.2.4. Pipeline C: Real-time Popularity (`popular_items`)

**Bảng `popular_items` lưu gì?**
| Column | Mô tả |
|--------|-------|
| `time_scope` | "all_time" (hiện tại chỉ có 1 scope) |
| `event_type` | clicks/carts/orders |
| `aid` | Item ID |
| `count` | Số lần xuất hiện |
| `rank` | Ranking theo count |

**Tại sao cần UPSERT thay vì INSERT?**
- Streaming aggregation là cumulative từ đầu query
- Batch 1: aid=123 count=5 → INSERT
- Batch 2: cumulative count=8 → UPSERT overwrite count=8 (không phải 5+8)
- Đã fix bug: trước đây code cộng thêm → double-counting

**Tại sao không có window?**
- Muốn "all-time" popularity → state không bounded
- Spark sẽ giữ state vĩnh viễn (có thể OOM nếu items quá nhiều)
- Hiện tại dùng `outputMode("update")` với global groupBy, Spark sẽ accumulate

**Tại sao rank cần refresh định kỳ?**
- Streaming update không maintain sorted order
- Background task trong API gọi `refresh_popular_items_ranks()` mỗi 2 phút
- Dùng `ROW_NUMBER() OVER (PARTITION BY event_type ORDER BY count DESC)` để recalculate ranks

#### 2.2.5. Pipeline D: Item Performance (`stats_items`)

**Bảng `stats_items` lưu gì?**
| Column | Mô tả |
|--------|-------|
| `aid` | Item ID (Primary Key) |
| `total_clicks/carts/orders` | Tổng counts từ đầu |
| `click_to_cart_rate` | Conversion rates |
| `click_to_order_rate` | |
| `cart_to_order_rate` | |
| `last_updated` | Timestamp cuối cùng được update |

**Tại sao có window = 1 giờ?**
- `groupBy("aid")` không window → unbounded state (OOM)
- Thêm window 1 giờ → Spark có thể drop old windows theo watermark
- 1 giờ đủ granular cho item-level analytics

**Tại sao rates được tính lại từ EXCLUDED values thay vì cumulative?**
- Streaming aggregation đã cumulative từ watermark
- UPSERT overwrite bằng giá trị mới, không cộng thêm

#### 2.2.6. Pipeline E: Model Performance (`advanced_funnel_stats`)

**Bảng `advanced_funnel_stats` lưu gì?**
| Column | Mô tả |
|--------|-------|
| `model_used` | Tên model (Primary Key) |
| `total_sessions` | Số sessions đã dùng model này |
| `sessions_with_clicks/carts/orders` | Sessions có mỗi loại event |
| `click_to_order_rate` | Overall conversion |
| `last_updated` | Timestamp |

**Tại sao `model_used` embed trong Kafka event thay vì join DB?**
- Trước đây: join streaming events với `predictions_log` table
- Vấn đề 1: Race condition → streaming có thể xử lý event TRƯỚC KHI API ghi predictions_log
- Vấn đề 2: Đọc toàn bộ bảng `predictions_log` MỖI MICRO-BATCH → chậm, không scale
- Solution: API embed `model_used` trong Kafka payload, streaming parse trực tiếp

**Tại sao đây là improvement quan trọng?**
- Race condition gây missing data trong analytics
- Full table read gây latency tăng theo thời gian (bảng càng lớn càng chậm)

#### 2.2.7. Pipeline F: Session Segmentation (`stats_sessions`)

**Bảng `stats_sessions` lưu gì?**
| Column | Mô tả |
|--------|-------|
| `session_type` | buyer/cart_abandoner/browse_only (Primary Key) |
| `count` | Số sessions thuộc type này |
| `avg_length` | Trung bình số events/session |
| `avg_duration_sec` | Trung bình thời gian session (giây) |
| `pct_of_total` | % sessions thuộc type này |

**Session type logic:**
```python
if has_orders: "buyer"
elif has_carts: "cart_abandoner"
else: "browse_only"
```

**Tại sao chia như vậy?**
- **Buyer**: có order = có conversion, metric quan trọng nhất
- **Cart abandoner**: có cart nhưng không order = potential customers bị lost
- **Browse only**: chỉ click, không cart = chưa có purchase intent

**Phân biệt cart_abandoner vs browse_only:**
- Cart là strong intent signal (user đã quyết định mua nhưng chưa checkout)
- Click có thể accidental/uninterested browsing
- Separating helps identify improvement areas (why carts don't convert?)

**Tại sao pct_of_total tính trong Python thay vì SQL?**
- PostgreSQL subquery trong UPSERT phức tạp và có thể race condition khi concurrent updates
- Đơn giản hơn: collect batch → tính tổng trong Python → upsert từng row với pct đã tính

### 2.3. Batch Jobs

#### 2.3.1. `funnel_analysis.py`

**Chạy khi nào?**
- 1 lần trong `setup-jobs` khi bắt đầu hệ thống
- Có thể chạy lại thủ công nếu muốn reset analytics

**Đọc data từ đâu?**
- Primary: `datasets/otto-recommender-system/test.jsonl` (402MB)
- Fallback: `datasets/test.jsonl`

**Output:**
1. `funnel_stats`: Global click→cart→order conversion rates
2. `stats_sessions`: Session segmentation (buyer/cart_abandoner/browse_only)
3. `advanced_funnel_stats`: Ghi chú là "Batch Analysis (test.jsonl)"

**Tại sao dùng `mode("overwrite")`?**
- Batch job chạy 1 lần, không cần append
- Overwrite đảm bảo clean state mỗi lần chạy

#### 2.3.2. `seed_popular_items.py`

**Tại sao seed?**
- API cần popular items cho cold start ngay khi start
- Nếu không có data → cold start fallback = empty
- Seed từ test.jsonl để có baseline popular items

**Top K = 100 items mỗi event type:**
- Đủ để cold start recommendation
- Không quá nhiều để tăng lookup time

#### 2.3.3. Covisitation Matrix Builder (CHƯA CHẠY)

**Lưu ý: Hiện tại chưa build matrices. Cần chạy `src/trainer/preprocess/CovisitationMatrixBuilder.py` để tạo:**

**Step 1: Generate Pairs (`DataProcessor.build_intermediate_pairs`)**
- Tạo cặp (aid1, aid2) từ events trong cùng session
- Pair 24h: tất cả events trong 24 giờ, last 30 events/session
- Pair 14d buy2buy: chỉ cart/order events trong 14 ngày

**Tại sao 24h window cho clicks/carts/orders?**
- 24h là typical browsing session length
- Quá ngắn (1h) → miss long browsing sessions
- Quá dài (7d) → include unrelated browsing

**Tại sao 14d cho buy2buy?**
- Buy2buy pattern: sau khi mua A, user mua B sau vài ngày
- 14 ngày là typical repurchase cycle cho e-commerce

**Step 2: Build Matrices (`CovisitationMatrixBuilder`)**
- **carts_orders_matrix**: top 15 candidates, weights: click=1, cart=6, order=3
- **buy2buy_matrix**: top 15 candidates, count unique sessions
- **clicks_matrix**: top 20 candidates, time-weighted: `1 + 3 * (ts - min) / (max - min)`

**Tại sao top-K per item?**
- Không thể return tất cả candidates (có thể hàng nghìn)
- Top 15-20 là đủ để generate good recommendations
- Giới hạn để không inflation storage và lookup time

**Partition strategy:**
- Repartition trước window function để tránh OOM
- `groupBy("aid1").orderBy("weight").limit(15)` là shuffle operation

### 2.4. Database Schema chi tiết

#### 2.4.1. `collected_events`

**Lưu trữ:**
| Column | Type | Mô tả |
|--------|------|-------|
| `session_id` | BIGINT | User session ID |
| `aid` | INT | Item ID |
| `event_type` | VARCHAR | clicks/carts/orders |
| `ts` | BIGINT | Timestamp (ms) |
| `created_at` | TIMESTAMP | Khi được insert |

**Tại sao cần bảng này?**
- Backup data để retrain/rebuild matrices
- Không dùng cho realtime prediction
- Có thể replay để rebuild analytics

**Index trên session_id:**
- Query events của 1 session → frequent operation
- Without index → full table scan

#### 2.4.2. `predictions_log`

**Lưu trữ:**
| Column | Type | Mô tả |
|--------|------|-------|
| `session_id` | BIGINT | |
| `model_used` | VARCHAR | cold_start/covisitation/sasrec |
| `session_length` | INT | Số events khi predict |
| `predicted_clicks/carts/orders` | INT[] | Array of item IDs |
| `latency_ms` | FLOAT | Thời gian predict |
| `created_at` | TIMESTAMP | |

**Tại sao log predictions?**
- Debug: xem model nào đang được dùng
- Analytics: model usage distribution
- Latency monitoring: detect slow predictions

#### 2.4.3. `online_hits`

**Lưu trữ:**
| Column | Type | Mô tả |
|--------|------|-------|
| `session_id` | BIGINT | |
| `aid` | INT | Item user thực sự tương tác |
| `event_type` | TEXT | |
| `is_hit` | BOOLEAN | Item có trong recs không |

**Tính hit rate:**
```sql
SELECT AVG(CASE WHEN is_hit THEN 1.0 ELSE 0.0 END) as hit_rate
FROM online_hits
WHERE event_type = 'orders'
```

**Tại sao hit rate quan trọng?**
- Direct measure của recommendation quality
- So sánh giữa các models
- Track over time để phát hiện model degradation

#### 2.4.4. `spark_metrics`

**Lưu trữ:**
| Column | Type | Mô tả |
|--------|------|-------|
| `query_id` | VARCHAR | Spark query ID |
| `query_name` | VARCHAR | Global-Stats-Query, Anomaly-Detection-Query, etc. |
| `batch_id` | BIGINT | Micro-batch ID |
| `input_rows_per_second` | FLOAT | Kafka consumption rate |
| `process_rows_per_second` | FLOAT | Processing rate |
| `batch_duration_ms` | BIGINT | Thời gian xử lý batch |

**Tại sao cần?**
- Monitor Spark job health
- Detect wenn job falling behind (input > process rate)
- Capacity planning

---

## 3. Data Flow chi tiết

### 3.1. Event Lifecycle

```
[1] Client
      │
      ▼ POST /api/event {session_id=123, aid=456, type="clicks", ts=...}
[2] API Service
      │
      ├─► Redis: RPUSH session:123 {"aid":456, "type":"clicks", "ts":...}
      │         → returns session_length = 5
      │
      ├─► Kafka: send("user-events", {session_id, aid, type, ts, model_used})
      │         → async, non-blocking
      │
      ├─► PostgreSQL: INSERT INTO collected_events (...)
      │         → async, non-blocking
      │
      ├─► Hybrid Recommendation Engine
      │         ├── Check cache: recs:123 exists? (key = session_id)
      │         ├── should_recompute = (5 % 3 == 0) → TRUE
      │         ├── session_length = 5 → COVISITATION
      │         ├── Load covisitation matrix from parquet (XEM 2.1.4)
      │         ├── candidates = lookup aid:456 → [aid1, aid2, ...]
      │         ├── scores = sum(weights) → sorted
      │         └── return {clicks: [...], carts: [...], orders: [...]}
      │
      ├─► Redis: SETEX recs:123 {recommendations} 1800
      │
      ├─► PostgreSQL: INSERT INTO predictions_log (...)
      │         → model_used = "covisitation", latency_ms = ...
      │
      ├─► PostgreSQL: INSERT INTO online_hits (nếu action là cart/order)
      │         → is_hit = (action_aid IN recommendations)
      │
      └─► Response: {recommendations, model_used, session_length, ...}

[3] Kafka Consumer (Spark Streaming)
      │
      ▼ readStream from Kafka topic "user-events"
[4] Parse & Watermark
      │
      ├─► from_json(value, schema)
      ├─► withColumn("timestamp", ts/1000 cast Timestamp)
      └─► withWatermark("timestamp", "2 minutes")
[5] 6 Pipelines (parallel)
      │
      ├─► Pipeline A: stats_hourly (window 5min) → JDBC append
      ├─► Pipeline B: anomaly_logs (window 1min, >50) → INSERT
      ├─► Pipeline C: popular_items → UPSERT
      ├─► Pipeline D: stats_items (window 1h) → UPSERT
      ├─► Pipeline E: advanced_funnel_stats → UPSERT
      └─► Pipeline F: stats_sessions → UPSERT
[6] PostgreSQL
```

### 3.2. Tại sao dùng background tasks cho Kafka/DB writes?

```python
background_tasks.add_task(kafka_producer.send, "user-events", payload)
background_tasks.add_task(db.log_event, session_id, aid, event_type, ts)
background_tasks.add_task(db.log_prediction, ...)
```

**Tại sao không đợi?**
- Kafka send + DB insert là I/O operations, mất 10-100ms
- User không cần đợi these writes để nhận recommendations
- Response time = time to compute recommendations (priority)

**Rủi ro:**
- Nếu background task fails, event không được logged
- Với Kafka: event có thể lost (no retry)
- Với DB: silent failure, không visible cho user
- Đây là acceptable trade-off cho performance

---

## 4. Configuration

### 4.1. Environment Variables

| Variable | Default | Tại sao cần |
|----------|---------|-------------|
| `POSTGRES_HOST` | localhost | Có thể chạy multi-container |
| `REDIS_HOST` | localhost | Session store có thể tách riêng |
| `KAFKA_BOOTSTRAP_SERVERS` | localhost:29092 | Kafka cluster có thể nhiều brokers |
| `SASREC_REMOTE_URL` | (required) | FORCED REMOTE mode, không có fallback |
| `DOCKER_USERNAME` | YOUR_USERNAME | Build và push lên DockerHub |
| `DOCKER_TAG` | latest | Versioning cho images |

### 4.2. Key Constants

| Constant | Value | Tại sao |
|----------|-------|---------|
| `SESSION_TTL_SECONDS` | 1800 (30 phút) | Session timeout, balance giữa memory và UX |
| `TOP_K` | 20 | OTTO competition requirement |
| `WATERMARK` | 2 phút | Late data tolerance, balance completeness vs latency |
| `ANOMALY_THRESHOLD` | 50 events/phút | Empirical, bot detection |
| `TOP_K_COVISITATION` | 15-20 | Không quá lớn, đủ coverage |

---

## 5. API Endpoints chi tiết

### 5.1. `POST /api/event`

**Request:**
```json
{
  "session_id": 12345,
  "aid": 67890,
  "type": "clicks",
  "ts": 1664582400000
}
```

**Response:**
```json
{
  "status": "ok",
  "session_length": 5,
  "model_used": "covisitation",
  "recommendations": {
    "clicks": [111, 222, 333, ...],
    "carts": [444, 555, 666, ...],
    "orders": [777, 888, 999, ...]
  },
  "latency_ms": 45.32
}
```

### 5.2. `GET /api/stats`

**Response (tổng hợp tất cả metrics):**
```json
{
  "active_sessions": 1234,
  "prediction_stats": {
    "total_predictions": 56789,
    "avg_latency_ms": 23.5,
    "unique_sessions": 4321,
    "avg_session_length": 7.2
  },
  "model_usage": [
    {"model_used": "covisitation", "count": 3000, "avg_latency": 15.2},
    {"model_used": "sasrec_deep_learning", "count": 1000, "avg_latency": 120.5},
    {"model_used": "cold_start", "count": 321, "avg_latency": 5.1}
  ],
  "funnel_stats": {
    "total_sessions": 4321,
    "sessions_with_clicks": 4000,
    "sessions_with_carts": 1500,
    "sessions_with_orders": 800,
    "click_to_cart_rate": 0.375,
    "cart_to_order_rate": 0.533
  },
  "hit_rate_stats": {
    "total_actions": 2300,
    "total_hits": 1150,
    "hit_rate": 0.5
  },
  "spark_metrics": [...],
  "anomaly_logs": [...],
  ...
}
```

---

## Changelog

| Phiên bản | Ngày | Mô tả |
|-----------|------|-------|
| v1 | 2026-05-17 | Mô tả hệ thống ban đầu |