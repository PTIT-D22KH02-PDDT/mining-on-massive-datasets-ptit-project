# Review: Cluster Mode Tuning & Benchmark v5

## Tóm tắt

Đã apply cluster tuning fixes và chạy benchmark v5. Kết quả vẫn chạy ở **local mode** (`.env` default), chưa test cluster mode thực tế.

## Thay đổi đã apply (Cluster Tuning)

| File | Thay đổi |
|------|----------|
| `config/config.yml` | executor memory `4g→3g`, thêm `executor.cores=2`, `cores.max=4`, shuffle partitions `12→24`, deployMode `client`, maxResultSize `2g→1g` |
| `docker-compose.yml` | thêm `PYSPARK_PYTHON=/usr/bin/python3` cho workers, spark-streaming, setup-jobs; executor memory default `4g→3g` |
| `docker-compose.dev.yml` | thêm `PYSPARK_PYTHON` + `PYSPARK_DRIVER_PYTHON`; executor memory `4g→3g` |
| `docker-compose-hub.yml` | same as above |
| `benchmark/report_generator.sh` | sửa pattern stats CSV (→`during_*.csv`), fallback spark metrics từ DB→JSON, detect Spark mode, thêm postgres/redis resource tracking |

## So sánh v4 vs v5

| Metric | v4 (before) | v5 (after) | Thay đổi |
|--------|-------------|------------|----------|
| Kafka TPS | 5987 | 12353 | **+106%** |
| API P95 | 4946ms | 5321ms | +7.6% |
| API error rate | N/A (no API) | 0.76% | — |
| Spark batches | — | 23 batches | — |
| Spark avg batch | — | 14770ms | — |
| Spark process rate | 140-220 rows/s | 700-1100 rows/s | **~5x** |
| Spark stability ratio | — | ~1.48 | FAIL |
| E2E P50 | — | 255s | FAIL |
| E2E P95 | — | 428s | FAIL |
| Spark mode | local | local | — |
| Workers CPU | 0.3% idle | 0.3% idle | idle |

### Phân tích

1. **Cả v4 và v5 đều chạy local mode**: `.env` set `SPARK_MASTER_URL=local[*]`, benchmark script không override → Spark job chạy ngay trên spark-streaming container. Workers (spark-worker-1, spark-worker-2) hoàn toàn idle.

2. **Config tuning có tác dụng**: dù chạy local, các config như shuffle partitions 24, executor.cores=2, cores.max=4 giúp Spark process rate tăng ~5x (140-220 → 700-1100 rows/s).

3. **Kafka TPS tăng gấp đôi (5987 → 12353)**: có thể do variance giữa các lần chạy hoặc do giảm tải từ Spark tuning (ít tranh chấp I/O hơn). Cần nhiều sample để kết luận.

4. **API P95 tăng nhẹ (4946 → 5321)**: có thể do variance. 0.76% error rate là mới (v4 không có).

5. **Spark stability FAIL**: batch duration trung bình 14.8s > trigger interval 10s, backlog tích tụ.

## Next Steps

### 1. Test cluster mode thực tế

```bash
# Kill local mode containers trước (tránh port conflict)
docker compose down

# Start cluster mode
SPARK_MASTER_URL=spark://spark-master:7077 docker compose up -d spark-master spark-worker-1 spark-worker-2 spark-streaming

# Verify workers registered: http://localhost:8080
# Run benchmark
cd benchmark && SPARK_MASTER_URL=spark://spark-master:7077 bash run_all.sh
```

### 2. Dự kiến cluster mode sẽ cải thiện

- **Spark process rate**: 2 workers × 2 cores = 4 executor cores (parallel) vs 1 core local
- **Spark batch duration**: giảm nhờ parallel executors
- **E2E latency**: giảm theo batch duration
- **Workers**: CPU usage từ 0.3% → active

### 3. Rủi ro

- Worker `PYSPARK_PYTHON` không đúng PATH → executor fail
- Shared volume (datasets/, spark-checkpoints/) không accessible từ worker
- Network latency giữa spark-streaming (driver) và workers
