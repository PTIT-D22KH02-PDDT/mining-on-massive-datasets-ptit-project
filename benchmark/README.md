# Benchmark Scripts - OTTO Recommender Pipeline

## Prerequisites

- Docker & docker-compose (stack dang chay)
- k6 (cai bang `./install_k6.sh`)

## Quick Start

```bash
# 1. Cai k6
./install_k6.sh

# 2. Kiem tra stack
docker compose -f docker-compose.dev.yml ps

# 3. Chay toan bo benchmark
./run_all.sh
```

## Scripts

| Script | Chuc nang | Thoi gian |
|--------|-----------|-----------|
| `install_k6.sh` | Cai dat k6 (Grafana load testing) | 30s |
| `kafka_producer_test.sh` | Do Kafka producer throughput | 5 phut |
| `kafka_consumer_test.sh` | Do Kafka consumer throughput | 2 phut |
| `log_resources.sh` | Ghi docker stats vao CSV lien tuc | tuy y |
| `loadtest.js` | K6 script load test API | 12 phut |
| `e2e_latency.sql` | SQL query do E2E pipeline latency | 5s |
| `report_generator.sh` | Tong hop ket qua thanh report | 10s |
| `run_all.sh` | Chay toan bo benchmark tu dong | ~25 phut |

## Output

Tat ca ket qua nam trong `benchmark/results/`:

```
results/
  kafka_producer_<ts>.log    -- Kafka throughput & latency
  kafka_consumer_<ts>.log    -- Consumer performance
  k6_results_<ts>.json       -- API latency (P50/P90/P95/P99)
  stats_<ts>.csv             -- Docker stats per container
  report_<ts>.txt            -- Final report
```

## Chi tiet

Xem `docs/benchmark_docs.md` cho full documentation (lam gi, tai sao, tac dong).
