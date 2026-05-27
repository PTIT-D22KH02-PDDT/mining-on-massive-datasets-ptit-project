# Co-Visitation Matrix Builder — Algorithm Overview

**Source:** `src/trainer/preprocess/build_covisited_matrix.py`

---

## 1. Mục tiêu

Xây dựng **ma trận đồng truy cập** (co-visitation matrix) duy nhất từ tất cả event types (click, cart, order) trong dataset OTTO.

Mỗi article ID (`aid`) sẽ có danh sách **top-K article liên quan nhất** kèm weight — dùng cho recommendation.

---

## 2. Pipeline tổng quan

```
Dataset Parquet
    │
    ▼
[1] Load & Select columns (session, aid, ts, type)
    │
    ▼
[2] Group by session →
    │     - Collect events thành array
    │     - Sort desc theo ts
    │     - Slice lấy tail 30 events cuối
    │     - Sort asc (để xử lý sliding window)
    │
    ▼
[3] Posexplode + Sliding Window (W = 5)
    │     - Mỗi event: lấy 5 event trước + 5 event sau
    │     - Filter: khác aid, |ts_diff| < 24h
    │     - Normalize undirected: aid_a < aid_b
    │     - dropDuplicates trong session
    │
    ▼
[4] Apply event bonus (click/cart/order → weight)
    │
    ▼
[5] Aggregate (aid_a, aid_b) → SUM(weight)
    │
    ▼
[6] Expand bidirectional (aid_a→aid_b + aid_b→aid_a)
    │     - Repartition(200, aid1) chống skew
    │
    ▼
[7] Window rank per aid → top-K
    │
    ▼
[8] Group by aid → Collect array → Sorted desc by wgt
    │
    ▼
[9] Save Parquet: (aid, candidates: array<struct<aid2, wgt>>)
```

---

## 3. Chi tiết từng bước

### 3.1. Load & Select

```python
df = spark.read.parquet(str(DATASETS_FILEPATH))
    .select(session, aid, ts, type)
    .repartition(100, SESSION_COLUMN_NAME)
```

Dataset OTTO dạng Parquet, flatten: mỗi row là một event (session, aid, ts, type).

---

### 3.2. Group → Tail → Pairs (1 lần Shuffle duy nhất)

**Vấn đề bản cũ:** Dùng self-join trên `session` → mỗi session 30 events sinh 30×30 = 900 row → intermediate khổng lồ.

**Giải pháp hiện tại:** Gom nhóm + xử lý trong 1 shuffle.

**Step A — Group & Collect**

```python
df.groupBy("session").agg(
    F.sort_array(
        F.collect_list(F.struct(ts, aid, type)),
        asc=False      # ts giảm dần
    ).alias("events_desc")
)
```

Với `collect_list`, thứ tự các event không đảm bảo, nên dùng `sort_array(..., asc=False)` để sắp xếp giảm dần theo `ts` (field đầu tiên của struct).

**Step B — Slice tail**

```python
.withColumn("events_tail", F.slice("events_desc", 1, TAIL_SIZE))
```

Giữ `TAIL_SIZE = 30` event cuối cùng (gần nhất) của mỗi session. Các event cũ hơn bị bỏ qua — giảm noise và memory.

**Step C — Sort asc for sliding window**

```python
.withColumn("events", F.sort_array("events_tail", asc=True))
```

Sắp xếp tăng dần để khi dùng `posexplode`, chỉ số `i` chạy từ 0..N-1 theo thứ tự thời gian — sliding window (lấy event trước/sau) hoạt động đúng.

**Step D — Posexplode + Sliding Window**

```python
.select("*", F.posexplode("events").alias("i", "event"))
```

Với mỗi event ở vị trí `i`:

- **After:** `slice(events, i + 2, WINDOW_SIZE)` — 5 event sau
- **Before:** `slice(events, max(1, i+1-WINDOW_SIZE), min(WINDOW_SIZE, i))` — 5 event trước (không lấy chính nó)

Gộp `before + after` → `neighbors`, explode thành các row riêng.

**Step E — Filter**

```python
.filter(
    (event.aid != neighbor.aid) &
    (abs(event.ts - neighbor.ts) < 24h_in_ms)
)
```

**Step F — Normalize undirected**

```python
F.least(event.aid, neighbor.aid)   → aid_a
F.greatest(event.aid, neighbor.aid) → aid_b
```

Luôn đảm bảo `aid_a < aid_b` — tránh đếm đôi (A,B) và (B,A) khi aggregate sau này.

**Step G — dropDuplicates trong session**

```python
.dropDuplicates([session, aid_a, aid_b, type_a, type_b])
```

Nếu trong sliding window có nhiều event cùng (aid, type) trùng, chỉ giữ 1 row.

**Kết quả đầu ra:**
```
session | aid_a | aid_b | type_a | type_b
```

---

### 3.3. Event Bonus

Gán weight cho mỗi cặp (type_a, type_b) dựa trên bảng symmetric:

| type_a | type_b | weight |
|--------|--------|--------|
| clicks | clicks | 1.0 |
| clicks | carts | 3.0 |
| clicks | orders | 4.0 |
| carts | carts | 6.0 |
| carts | orders | 7.0 |
| orders | orders | 10.0 |

Dùng `F.least` / `F.greatest` trên type string để đảm bảo symmetric (vì `aid_a < aid_b` nhưng type_a và type_b không nhất thiết theo alphabet).

Output: `(session, aid_a, aid_b, wgt)`

---

### 3.4. Aggregate

```python
.groupBy(aid_a, aid_b).agg(F.sum(wgt))
```

Cộng dồn weight của cùng 1 cặp (aid_a, aid_b) qua tất cả session. Không quan tâm thứ tự — (`aid_a=3, aid_b=5`) và (`aid_a=5, aid_b=3`) là 2 cặp khác nhau (vì đã normalize undirected).

---

### 3.5. Expand Bidirectional + Top-K

Vì ma trận đã normalize undirected, mỗi row chỉ có `aid_a → aid_b`. Khi cần query neighbors của one aid bất kỳ, nó có thể nằm ở cả 2 cột.

**Giải pháp:** Tạo 2 chiều từ 1 row:

```python
forward:  (aid_a, aid_b, wgt)
backward: (aid_b, aid_a, wgt)   # → đổi tên cột
```

**Repartition trước Window:** `repartition(200, "aid1")` — rải đều dữ liệu trước khi Window rank, tránh OOM do skew (aid phổ biến có hàng triệu neighbors).

**Window rank:** `partitionBy(aid1).orderBy(wgt desc, aid2 desc)` — lấy top-K neighbors cho mỗi aid.

---

### 3.6. Group thành array

```python
.withColumn("candidate_sortable",
    F.struct(F.col(wgt).alias("wgt"), F.col("aid2").alias("aid2")))
.groupBy("aid1").agg(
    F.sort_array(F.collect_list("candidate_sortable"), asc=False)
)
```

**Lưu ý:** `F.struct` đặt `wgt` làm field đầu tiên vì `sort_array` sort theo field đầu tiên của struct. Sau đó dùng `transform` để khôi phục schema chuẩn `struct<aid2, wgt>`.

---

## 4. So sánh với bản cũ (self-join)

| Khía cạnh | Bản cũ (self-join) | Bản hiện tại (group + sliding window) |
|-----------|-------------------|--------------------------------------|
| Số Shuffle | 4-5 | 3 (group + aggregate + window) |
| Intermediate rows/session | ~900 (30×30) | ~135 (30 × 2W) |
| dropDuplicates | ~50% bị drop | ~15% bị drop |
| Xử lý tail | Window riêng | Trong cùng 1 groupBy |
| Sort struct | **Sai** (sort theo aid2) | **Đúng** (wgt field đầu) |
| Output path | Relative string | Absolute (`DATASETS_DIR`) |
| Skew handling | Không | `repartition(200, aid1)` trước Window |

---

## 5. Trade-offs & hạn chế

**Sliding window W = 5** — thay vì full combination C(30,2) = 435 pairs/session, chỉ còn ~135 pairs. Mất ~70% signals, đặc biệt là các cặp xa nhau trong session. Tuy nhiên, với dữ liệu session ngắn (trung bình ~5-10 events), ảnh hưởng không lớn.

**Có thể cải thiện thêm:**
- Tăng `WINDOW_SIZE` nếu cluster đủ mạnh
- Hoặc dùng UDF Python để sinh full combination từ tail 30 events (tốn serialization nhưng giữ được 100% signals)
- `repartition(100, session)` ở đầu pipeline có thể redundant nếu bước sau `groupBy(session)` shuffle lại; có thể bỏ để giảm 1 shuffle.
