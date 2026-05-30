"""
python -m src.api.main
FastAPI Server - OTTO Recommender Pipeline API.

Phase 2 Improvements:
- 2.1 Circuit Breaker for SASRec remote calls
- 2.2 Structured JSON logging with Correlation ID
- 2.3 Batch DB writes via Redis buffer
- 2.4 Detailed health check
"""

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

root_dir = str(Path(__file__).resolve().parents[2])
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import httpx
import pybreaker
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.api.db import Database
from src.api.session_manager import SessionManager
from src.core.infra.kafka_queue import KafkaMessage
from src.evaluation.metrics import mrr_at_k, ndcg_at_k, recall_at_k
from src.serving.sasrec_recommender import RemoteModelRecommender

from dotenv import load_dotenv
load_dotenv()
MODEL_NAME = os.getenv("MODEL_NAME")   #tên model ở trong env nhé 

# --- JSON Logging Setup (Phase 2.2) ---
class UUIDFormatter(logging.Formatter):
    def format(self, record):
        record.correlation_id = getattr(record, "correlation_id", "-")
        return super().format(record)


def setup_json_logging():
    handler = logging.StreamHandler()
    formatter = UUIDFormatter(
        "%(asctime)s %(levelname)s %(name)s [%(correlation_id)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers = []
    root.addHandler(handler)
    root.setLevel(logging.INFO)


setup_json_logging()
logger = logging.getLogger(__name__)

# --- Global singletons ---
session_mgr: Optional[SessionManager] = None
db: Optional[Database] = None
sasrec: Optional[RemoteModelRecommender] = None
kafka_producer = None
background_queue: Optional[asyncio.Queue] = None
pending_sessions: set = set()  # Dedup: track sessions already in queue

TOP_K = 20

# --- Buffer Config (Phase 2.3 + 6.1 + 9.1) ---
REDIS_EVENT_BUFFER = "buffer:collected_events"
REDIS_PREDICTION_BUFFER = "buffer:predictions"
BUFFER_TTL_SECONDS = 3600  # 1 hour (Phase 6.1: prevent OOM)
MAX_BUFFER_SIZE = 10000  # Max items per buffer (Phase 6.1: prevent unbounded growth)
BATCH_SIZE = int(os.getenv("DB_BATCH_SIZE", "50"))
FLUSH_INTERVAL = int(os.getenv("DB_FLUSH_INTERVAL", "5"))

# --- Circuit Breaker (Phase 2.1) ---
sasrec_breaker = pybreaker.CircuitBreaker(
    fail_max=3,
    reset_timeout=60,
)
SASREC_TIMEOUT = 10.0
# recommend_multi_objective

async def call_sasrec_with_fallback(
    session_aids: List[int],
    top_k: int,
    request_id: str = "-",
    type_sequence: Optional[List[str]] = None,
    ts_sequence: Optional[List[int]] = None,
):
    """
    Phase 2.1: Call SASRec with circuit breaker + covisitation fallback.
    """

    async def _call():
        try:
            result = await sasrec.predict_remote(
                top_k, session_aids,
                type_sequence=type_sequence,
                ts_sequence=ts_sequence,
                model=MODEL_NAME,
            )
            logger.info(
                f"[{request_id}] Call model succeeded", extra={"correlation_id": request_id}
            )
            return result
        except Exception as e:
            logger.warning(
                f"[{request_id}] Model call failed: {e}",
                extra={"correlation_id": request_id},
            )
            raise

    try:
        return await sasrec_breaker.call(_call)
    except pybreaker.CircuitBreakerError:
        logger.warning(
            f"[{request_id}] Circuit OPEN — falling back to covisitation",
            extra={"correlation_id": request_id},
        )
        raise


# --- Pydantic Models ---
class EventRequest(BaseModel):
    session_id: int
    aid: int
    type: str
    ts: Optional[int] = None


class EventResponse(BaseModel):
    status: str
    session_length: int
    model_used: str
    recommendations: dict
    latency_ms: float


class SessionResponse(BaseModel):
    session_id: int
    events: list
    length: int


class HealthStatus(BaseModel):
    status: str
    api: str
    redis: dict
    postgres: dict
    kafka: dict
    sasrec: dict


# --- Background Task: Flush DB buffers (Phase 2.3) ---
async def flush_db_buffers_task():
    """Periodically flush buffered events/predictions from Redis to PostgreSQL."""
    while True:
        await asyncio.sleep(FLUSH_INTERVAL)
        if not db or not session_mgr:
            continue
        try:
            flushed_events = 0
            flushed_predictions = 0

            # Flush collected_events
            while True:
                batch = await session_mgr.redis.lpop(REDIS_EVENT_BUFFER, BATCH_SIZE)
                if not batch:
                    break
                if isinstance(batch, str):
                    batch = [batch]
                for item in batch:
                    try:
                        event_data = json.loads(item)
                        db.log_event(
                            event_data["session_id"],
                            event_data["aid"],
                            event_data["type"],
                            event_data["ts"],
                        )
                        flushed_events += 1
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"Failed to parse buffered event: {e}")
            if flushed_events > 0:
                logger.info(f"Flushed {flushed_events} buffered events to PostgreSQL")

            # Flush predictions_log
            while True:
                batch = await session_mgr.redis.lpop(REDIS_PREDICTION_BUFFER, BATCH_SIZE)
                if not batch:
                    break
                if isinstance(batch, str):
                    batch = [batch]
                for item in batch:
                    try:
                        pred_data = json.loads(item)
                        db.log_prediction(
                            session_id=pred_data["session_id"],
                            model_used=pred_data["model_used"],
                            session_length=pred_data["session_length"],
                            predicted_clicks=pred_data.get("predicted_clicks", []),
                            predicted_carts=pred_data.get("predicted_carts", []),
                            predicted_orders=pred_data.get("predicted_orders", []),
                            latency_ms=pred_data["latency_ms"],
                        )
                        flushed_predictions += 1
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"Failed to parse buffered prediction: {e}")
            if flushed_predictions > 0:
                logger.info(
                    f"Flushed {flushed_predictions} buffered predictions to PostgreSQL"
                )

            # Flush online_hits
            while True:
                batch = await session_mgr.redis.lpop("buffer:online_hits", BATCH_SIZE)
                if not batch:
                    break
                if isinstance(batch, str):
                    batch = [batch]
                hits = []
                for item in batch:
                    try:
                        hit_data = json.loads(item)
                        hits.append(
                            (
                                hit_data["session_id"],
                                hit_data["aid"],
                                hit_data["event_type"],
                                hit_data["is_hit"],
                            )
                        )
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"Failed to parse buffered online_hit: {e}")
                if hits:
                    db.log_online_hits_batch(hits)
                    logger.info(
                        f"Flushed {len(hits)} buffered online_hits to PostgreSQL"
                    )

            # Flush online_metrics (5.1)
            while True:
                batch = await session_mgr.redis.lpop("buffer:online_metrics", BATCH_SIZE)
                if not batch:
                    break
                if isinstance(batch, str):
                    batch = [batch]
                for item in batch:
                    try:
                        metric_data = json.loads(item)
                        db.log_online_metrics(
                            session_id=metric_data["session_id"],
                            model_used=metric_data["model_used"],
                            event_type=metric_data["event_type"],
                            metrics=metric_data["metrics"],
                        )
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"Failed to parse buffered online_metrics: {e}")

        except Exception as e:
            logger.error(f"Error flushing DB buffers: {e}")


# --- Background Task: Rank refresh ---
async def refresh_ranks_task():
    while True:
        try:
            if db:
                db.refresh_popular_items_ranks()
                logger.info("Popular items ranks refreshed")
        except Exception as e:
            logger.error(f"Error in refresh_ranks_task: {e}")
        await asyncio.sleep(120)

async def background_recompute_worker():
    """
    Write-Path async worker:
    - session >= 5: gọi SASRec remote model (chạy trên thread riêng để tránh block)
    - Lưu kết quả vào Redis cache (recs:{session_id})
    """
    while True:
        try:
            if not background_queue:
                await asyncio.sleep(1)
                continue
            #Đợi nhận event từ queue (Non-blocking)
            event = await background_queue.get()
            session_id = event["session_id"]
            corr_id = event.get("corr_id", "-")
            
            session_aids, type_sequence, ts_sequence = await session_mgr.get_session_sequences(session_id)

            session_length = len(session_aids)
            
            if session_length == 0:
                background_queue.task_done()
                continue
            if session_length >= 5:
                model_used = "remote_model"
                try:
                    recs = await call_sasrec_with_fallback(
                        session_aids, TOP_K, request_id=corr_id,
                        type_sequence=type_sequence, ts_sequence=ts_sequence,
                    )
                except Exception as e:
                    logger.warning(
                        f"[Worker][{corr_id}] Remote model failed, fallback to covisitation: {e}"
                    )
                    model_used = "remote_model_fallback_covisitation"
                    recs = await session_mgr.get_covisitation_recommendations(session_aids, TOP_K)
            else:
                model_used = "covisitation_redis"
                recs =await session_mgr.get_covisitation_recommendations(session_aids, TOP_K)
            
            # Ghi đè kết quả mới tính toán xong vào Redis Cache 
            await session_mgr.store_recommendations(session_id, recs)
            
            logger.info(
                f"[Worker][{corr_id}] Recomputed recs for session {session_id} "
                f"(len={session_length}, model={model_used})"
            )
            background_queue.task_done()
            
        except Exception as e:
            logger.error(f"[Worker] Error trong vòng lặp chính: {e}")
            # Tránh vòng lặp vô hạn chạy quá nhanh làm quá tải CPU khi có lỗi hệ thống
            await asyncio.sleep(1)

# --- Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    global \
        session_mgr, \
        db, \
        sasrec, \
        kafka_producer, \
        kafka_queue, \
        background_queue

    logger.info("Starting OTTO API Server...")

    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    session_mgr = SessionManager(host=redis_host, port=redis_port)

    # Kiểm tra covisitation matrix đã được load vào Redis chưa
    try:
        keys = (await session_mgr.redis.scan(cursor=0, match="covis:*", count=1))[1]
        if not keys:
            logger.warning(
                "No covisitation matrix in Redis! "
                "Run 'docker compose --profile setup run --rm setup-matrix' first"
            )
        else:
            logger.info("Covisitation matrix found in Redis")
    except Exception as e:
        logger.warning(f"Cannot check covisitation matrix in Redis: {e}")

    db = None
    pg_enabled = os.getenv("POSTGRES_ENABLED", "true").lower() != "false"
    if pg_enabled:
        pg_host = os.getenv("POSTGRES_HOST", "localhost")
        pg_port = int(os.getenv("POSTGRES_PORT", "5432"))
        pg_user = os.getenv("POSTGRES_USER", "otto")
        pg_pass = os.getenv("POSTGRES_PASSWORD", "otto123")
        pg_db = os.getenv("POSTGRES_DB", "otto_recommender")
        try:
            _db = Database(
                host=pg_host, port=pg_port, dbname=pg_db, user=pg_user, password=pg_pass
            )
            _db._get_conn()
            db = _db
            logger.info("PostgreSQL connected")
        except Exception as e:
            logger.warning(f"PostgreSQL unavailable, running without DB: {e}")
            db = None
    else:
        logger.info("PostgreSQL disabled via POSTGRES_ENABLED=false")

    remote_url = os.getenv(
        "REMOTE_MODEL_URL", "https://rs-model1.vucongtuanduong.dpdns.org/"
    )
    if not remote_url:
        logger.error("REMOTE_MODEL_URL is not set! Exiting...")
        sys.exit(1)

    sasrec = RemoteModelRecommender(remote_url=remote_url)
    logger.info(f"SASRec initialized in FORCED REMOTE mode ({remote_url})")

    kafka_producer = None
    kafka_queue = None
    kafka_init_task = None

    async def _init_kafka_background():
        global kafka_producer, kafka_queue
        from src.core.infra.kafka import KafkaProducerService
        from src.core.infra.kafka_queue import KafkaQueue

        attempt = 0
        while True:
            try:
                attempt += 1
                p = KafkaProducerService()
                await p.start()
                q = KafkaQueue(p, maxsize=5000)
                await q.start()
                kafka_producer = p
                kafka_queue = q
                logger.info(
                    "Kafka producer + queue connected (after %d attempts)", attempt
                )
                return
            except Exception as e:
                logger.warning("Kafka not available yet (attempt %d): %s", attempt, e)
                await asyncio.sleep(5)

    kafka_init_task = asyncio.create_task(_init_kafka_background())

    background_queue = asyncio.Queue(maxsize=1000)
    worker_task = asyncio.create_task(background_recompute_worker())

    asyncio.create_task(flush_db_buffers_task())
    asyncio.create_task(refresh_ranks_task())
    logger.info("Background tasks started (DB buffer flush, rank refresh, background recompute)")

    yield

    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass

    if kafka_init_task and not kafka_init_task.done():
        kafka_init_task.cancel()
        try:
            await kafka_init_task
        except asyncio.CancelledError:
            pass
    if kafka_queue:
        await kafka_queue.stop()
    if kafka_producer:
        await kafka_producer.stop()
    if db:
        db.close()
    await sasrec.aclose()

    logger.info("OTTO API Server shut down")


# --- FastAPI App ---
app = FastAPI(
    title="OTTO Recommender Pipeline API",
    description="Hybrid recommender with circuit breaker, batch DB writes, structured logging",
    version="1.1.0",
    lifespan=lifespan,
)


# --- Correlation ID Middleware (Phase 2.2) ---
@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    correlation_id = str(uuid.uuid4())
    request.state.correlation_id = correlation_id

    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response


# --- Event endpoint with batch DB writes + circuit breaker ---
@app.post("/api/event", response_model=EventResponse)
async def receive_event(event: EventRequest, request: Request):
    start_time = time.time()
    corr_id = getattr(request.state, "correlation_id", "-")
    ts = event.ts or int(time.time() * 1000)

    logger.info(
        f"[{corr_id}] Event received: session={event.session_id} aid={event.aid} type={event.type}"
    )

    # 1. Append to Redis session
    session_length = await session_mgr.append_event(
        event.session_id, event.aid, event.type, ts
    )

    # 2. Get recommendations (Read-Path logic)
    cached_recs = await session_mgr.get_last_recommendations(event.session_id)

    if cached_recs:
        # Cache HIT - return precomputed recommendations immediately
        model_used = "cached-redis"
        recommendations = cached_recs
    else:
        # Cache MISS - choose strategy based on session length
        # Inline covisitation from Redis (single aid lookup)
        model_used = "covisitation_redis"
        session_aids = await session_mgr.get_session_aids(event.session_id)
        recommendations = await session_mgr.get_covisitation_recommendations(session_aids, TOP_K)
    # 3. Push to background recompute queue (non-blocking Write-Path)
    should_recompute = session_length >= 5  # Complex model needs updates
    if should_recompute and background_queue:
        try:
            background_queue.put_nowait({
                "session_id": event.session_id,
                "session_length": session_length,
                "event_aid": event.aid,
                "event_type": event.type,
                "ts": ts,
                "corr_id": corr_id,
            })
        except asyncio.QueueFull:
            logger.warning(f"[{corr_id}] Background recompute queue full, skipping task enqueue")

    # 3. Publish to Kafka via queue (non-blocking, fire-and-forget)
    if kafka_queue:
        kafka_queue.put_nowait(
            KafkaMessage(
                topic="user-events",
                message={
                    "session_id": event.session_id,
                    "aid": event.aid,
                    "type": event.type,
                    "ts": ts,
                    "model_used": model_used,
                },
                key=str(event.session_id),
            )
        )
    else:
        logger.warning(f"[{corr_id}] kafka_queue is None, skipping Kafka publish")

    # 4. Buffer event to Redis (Phase 2.3 batch writes + 6.1 TTL protection)
    event_data = json.dumps(
        {"session_id": event.session_id, "aid": event.aid, "type": event.type, "ts": ts}
    )
    await session_mgr.redis.rpush(REDIS_EVENT_BUFFER, event_data)
    await session_mgr.redis.ltrim(
        REDIS_EVENT_BUFFER, -MAX_BUFFER_SIZE, -1
    )  # Phase 6.1: Max length
    await session_mgr.redis.expire(REDIS_EVENT_BUFFER, BUFFER_TTL_SECONDS)  # Phase 6.1: TTL

    latency_ms = (time.time() - start_time) * 1000

    # 5. Buffer prediction to Redis (Phase 2.3 batch writes)
    pred_data = json.dumps(
        {
            "session_id": event.session_id,
            "model_used": model_used,
            "session_length": session_length,
            "predicted_clicks": recommendations.get("clicks", []),
            "predicted_carts": recommendations.get("carts", []),
            "predicted_orders": recommendations.get("orders", []),
            "latency_ms": latency_ms,
        }
    )
    await session_mgr.redis.rpush(REDIS_PREDICTION_BUFFER, pred_data)
    await session_mgr.redis.ltrim(
        REDIS_PREDICTION_BUFFER, -MAX_BUFFER_SIZE, -1
    )  # Phase 6.1: Max length
    await session_mgr.redis.expire(
        REDIS_PREDICTION_BUFFER, BUFFER_TTL_SECONDS
    )  # Phase 6.1: TTL

    # 6. Online hit tracking (buffer to Redis + 6.1 TTL protection)
    if event.type in ["carts", "orders"]:
        all_recs = set(
            recommendations.get("clicks", [])
            + recommendations.get("carts", [])
            + recommendations.get("orders", [])
        )
        is_hit = event.aid in all_recs
        await session_mgr.redis.rpush(
            "buffer:online_hits",
            json.dumps(
                {
                    "session_id": event.session_id,
                    "aid": event.aid,
                    "event_type": event.type,
                    "is_hit": is_hit,
                }
            ),
        )
        await session_mgr.redis.ltrim("buffer:online_hits", -MAX_BUFFER_SIZE, -1)
        await session_mgr.redis.expire("buffer:online_hits", BUFFER_TTL_SECONDS)

        # 5.1: Calculate and log Recall@K, NDCG@K, MRR@K
        ground_truth = [event.aid]
        all_recs_list = (
            recommendations.get("clicks", [])
            + recommendations.get("carts", [])
            + recommendations.get("orders", [])
        )
        eval_metrics = {
            "recall@20": recall_at_k(all_recs_list, ground_truth, k=20),
            "ndcg@20": ndcg_at_k(all_recs_list, ground_truth, k=20),
            "mrr@20": mrr_at_k(all_recs_list, ground_truth, k=20),
            "hit_rate": 1.0 if is_hit else 0.0,
        }
        await session_mgr.redis.rpush(
            "buffer:online_metrics",
            json.dumps(
                {
                    "session_id": event.session_id,
                    "model_used": model_used,
                    "event_type": event.type,
                    "metrics": eval_metrics,
                }
            ),
        )
        await session_mgr.redis.ltrim("buffer:online_metrics", -MAX_BUFFER_SIZE, -1)
        await session_mgr.redis.expire("buffer:online_metrics", BUFFER_TTL_SECONDS)

    logger.info(f"[{corr_id}] Response: model={model_used} latency={latency_ms:.1f}ms")

    return EventResponse(
        status="ok",
        session_length=session_length,
        model_used=model_used,
        recommendations=recommendations,
        latency_ms=round(latency_ms, 2),
    )


@app.get("/api/session/{session_id}", response_model=SessionResponse)
async def get_session(session_id: int):
    events = await session_mgr.get_session(session_id)
    return SessionResponse(session_id=session_id, events=events, length=len(events))


@app.get("/api/stats")
async def get_stats():
    return {
        "active_sessions": await session_mgr.get_active_session_count() if session_mgr else 0,
        "prediction_stats": db.get_prediction_stats() if db else {},
        "model_usage": db.get_model_usage() if db else [],
        "collected_events": db.get_collected_events_count() if db else 0,
        "event_distribution": db.get_event_distribution() if db else [],
        "latency_history": db.get_latency_history() if db else [],
        "recent_predictions": db.get_recent_predictions(limit=10) if db else [],
        "funnel_stats": db.get_funnel_stats() if db else {},
        "hourly_stats": db.get_hourly_stats() if db else [],
        "session_distribution": db.get_session_distribution() if db else [],
        "spark_metrics": db.get_spark_metrics() if db else [],
        "anomaly_logs": db.get_anomalies(limit=50) if db else [],
        "hit_rate_stats": db.get_hit_rate_stats() if db else {},
        "advanced_funnel": db.get_advanced_funnel_stats() if db else [],
        "online_metrics_summary": db.get_all_online_metrics_summary() if db else [],
        "online_metrics_trend": db.get_online_metrics_trend() if db else [],
        "item_insights": db.get_item_insights() if db else [],
    }


@app.get("/api/popular/{event_type}")
async def get_popular(event_type: str, limit: int = 10):
    items = db.get_popular_items_with_counts(event_type, limit) if db else []
    return {"event_type": event_type, "items": items}


# --- Phase 2.4: Detailed Health Check ---
@app.get("/api/health", response_model=HealthStatus)
async def health_check():
    # Redis health
    redis_status = "ok"
    redis_info = {}
    try:
        r = session_mgr.redis
        await r.ping()
        info_memory = await r.info("memory")
        info_clients = await r.info("clients")
        redis_info = {
            "status": "ok",
            "memory_mb": info_memory.get("used_memory_human", "N/A"),
            "connected_clients": info_clients.get("connected_clients", 0),
            "db_keys": await r.dbsize(),
        }
    except Exception as e:
        redis_status = f"error: {e}"
        redis_info = {"status": "error", "error": str(e)}

    #tạm bỏ qua postgre với kafka ở đây để test luồng gợi ý
    # PostgreSQL health
    pg_status = "ok"
    pg_info = {}
    try:
        with db.cursor() as cur:
            cur.execute("SELECT 1")
            cur.execute("SELECT COUNT(*) FROM pg_stat_activity")
            row = cur.fetchone()
            conn_count = row["count"] if row else 0
        pg_info = {"status": "ok", "active_connections": conn_count}
        logger.debug(f"Postgres health OK: {conn_count} connections")
    except Exception as e:
        logger.error(f"Postgres health check failed: {e}")
        pg_status = f"error: {e}"
        pg_info = {"status": "error", "error": str(e)}
    pg_info = {"status": "ok"}  # tạm ok 
    # Kafka health
    kafka_status = "ok"
    kafka_info = {}
    try:
        if kafka_producer and kafka_producer._producer:
            kafka_info = {"status": "ok", "producer_ready": True}
        else:
            kafka_status = "not_configured"
            kafka_info = {"status": "not_configured"}
    except Exception as e:
        kafka_status = f"error: {e}"
        kafka_info = {"status": "error", "error": str(e)}

    kafka_info = {"status": "ok"}  # tạm ok 

    # SASRec health (ping + latency)
    sasrec_status = "ok"
    sasrec_info = {}
    try:
        import urllib.error
        import urllib.request

        start = time.time()
        req = urllib.request.Request(
            sasrec.remote_url.rstrip("/") + "/health",
            headers={"User-Agent": "OTTO-API/1.0"},
        )
        urllib.request.urlopen(req, timeout=5)
        latency = (time.time() - start) * 1000
        sasrec_info = {
            "status": "ok",
            "latency_ms": round(latency, 1),
            "url": sasrec.remote_url,
        }
    except urllib.error.URLError:
        sasrec_status = "unreachable"
        sasrec_info = {
            "status": "unreachable",
            "circuit_state": str(sasrec_breaker._state),
        }
    except Exception as e:
        sasrec_status = f"error: {e}"
        sasrec_info = {"status": "error", "error": str(e)}

    overall = "ok"
    if redis_status != "ok" or pg_status != "ok":
        overall = "degraded"
    if kafka_status not in ("ok", "not_configured"):
        overall = "degraded"

    return HealthStatus(
        status=overall,
        api="ok",
        redis=redis_info,
        postgres=pg_info,
        kafka=kafka_info,
        sasrec=sasrec_info,
    )


if __name__ == "__main__":
    import uvicorn

    reload = os.getenv("RELOAD", "false").lower() == "true"
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=reload)