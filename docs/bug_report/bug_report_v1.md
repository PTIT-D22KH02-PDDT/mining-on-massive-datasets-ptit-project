# Bug Report — Otto Recommender Pipeline
**Date:** 2026-05-17
**Version:** v1

---

## 1. [CRITICAL] Double-counting trong Streaming Upserts

**File:** `src/streaming/spark_streaming_job.py`

### Mô tả
Streaming aggregations (`groupBy().count()`) với `outputMode("update")` trả về **giá trị tích lũy** (cumulative) từ đầu query. Nhưng upsert logic lại **cộng thêm** vào giá trị cũ trong DB, dẫn đến double-counting qua từng micro-batch.

### Cách sửa
Thay `count = existing + EXCLUDED.count` bằng `count = EXCLUDED.count` vì giá trị từ Spark đã là cumulative.

---

## 2. [CRITICAL] Race Condition — Model Performance Pipeline

**File:** `src/streaming/spark_streaming_job.py`

### Mô tả
Hàm `process_model_performance` join streaming events với bảng `predictions_log` (được FastAPI ghi bất đồng bộ qua `background_tasks`). Streaming xử lý event **trước** khi API kịp ghi `predictions_log` → Join mất session → model performance tracking bị thiếu. Đồng thời đọc toàn bộ bảng `predictions_log` mỗi micro-batch.

### Cách sửa
Thêm `model_used` vào Kafka event payload, parse trực tiếp từ event, loại bỏ DB join.

---

## 3. [CRITICAL] Hit Rate Đo Trên Cached Recommendations Cũ

**File:** `src/api/main.py`

### Mô tả
Hit rate được tính bằng `cached_recs` — có thể là recommendation từ 3 events trước, không phải recommendation thực sự hiển thị.

### Cách sửa
Dùng `recommendations` (mới nhất) thay vì `cached_recs` cho hit rate logging.

---

## 4. [MEDIUM] Tên Constant Sai — `_IN_MS` Nhưng Giá Trị Là Seconds

**File:** `src/core/constant.py`

### Mô tả
`ONE_DAY_IN_MS` = 86400 (seconds, không phải ms). `DataProcessor._generate_pairs()` nhân thêm `* 1000` nên tính toán đúng, nhưng tên gây nhầm lẫn.

### Cách sửa
Đổi tên → `ONE_DAY_IN_SECONDS`, `FOURTEEN_DAYS_IN_SECONDS`.

---

## 5. [MEDIUM] Anomaly Logs Không Có Dedup

**File:** `src/streaming/spark_streaming_job.py`

### Mô tả
Cùng `session_id` có thể bị log nhiều lần qua các window khác nhau.

### Cách sửa
Thêm `dropDuplicates(["session_id"])` vào anomaly pipeline.

---

## 6. [MEDIUM] Unbounded State Cho `items_stats_df`

**File:** `src/streaming/spark_streaming_job.py`

### Mô tả
`groupBy("aid")` không có window → state tăng vô hạn.

### Cách sửa
Thêm `window(col("timestamp"), "1 hour")` vào groupBy.

---

## 7. [MEDIUM] `iterrows()` Hiệu Năng Thấp

**File:** `src/serving/covisitation_recommender.py`

### Mô tả
Dùng `iterrows()` để build lookup dictionary → chậm.

### Cách sửa
Thay bằng `groupby()` để build lookup.

---

## 8. [MEDIUM] `stats_sessions` Không Được Cập Nhật Bởi Streaming

**File:** `src/streaming/spark_streaming_job.py`

### Mô tả
Bảng `stats_sessions` chỉ được ghi bởi `funnel_analysis.py` (batch job, chạy 1 lần trong `setup-jobs`). Streaming job không có pipeline nào update `stats_sessions`, nên bảng không được cập nhật theo thời gian thực.

### Cách sửa
Thêm Pipeline F — `process_stats_sessions` trong streaming job, classify sessions (buyer/cart_abandoner/browse_only) per micro-batch và upsert vào `stats_sessions`.

---

## Tổng kết

| # | Mức | File | Lỗi |
|---|-----|------|-----|
| 1 | **Critical** | `spark_streaming_job.py` | Double-counting do upsert cộng cumulative values |
| 2 | **Critical** | `spark_streaming_job.py` | Race condition + full table read mỗi batch |
| 3 | **Critical** | `api/main.py` | Hit rate đo trên cached recs cũ |
| 4 | Medium | `constant.py` | Tên constant `_IN_MS` nhưng giá trị là seconds |
| 5 | Medium | `spark_streaming_job.py` | Anomaly logs không dedup |
| 6 | Medium | `spark_streaming_job.py` | Unbounded streaming state |
| 7 | Medium | `covisitation_recommender.py` | `iterrows()` chậm |
| 8 | Medium | `spark_streaming_job.py` | `stats_sessions` không được update realtime |

---

## Changelog

| Version | Date | Description |
|---------|------|-------------|
| v1 | 2026-05-17 | Initial bug report (bugs 1-7) |
| v1 | 2026-05-17 | Add bug #8: `stats_sessions` not updated by streaming |