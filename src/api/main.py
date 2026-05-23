"""
FastAPI Server - OTTO Recommender Pipeline API.

Phase 2 Improvements:
- 2.1 Circuit Breaker for SASRec remote calls
- 2.2 Structured JSON logging with Correlation ID
- 2.3 Batch DB writes via Redis buffer
- 2.4 Detailed health check
"""

import time
import logging
import asyncio
import sys
import os
import uuid
import json
from pathlib import Path
from contextlib import asynccontextmanager
from typing import List, Optional

root_dir = str(Path(__file__).resolve().parents[2])
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import httpx
import pybreaker
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.api.session_manager import SessionManager
from src.api.db import Database
from src.api.cold_start import ColdStartRecommender
from src.serving.covisitation_recommender import CovisitationRecommender
from src.serving.sasrec_recommender import SASRecRecommender
from src.evaluation.metrics import recall_at_k, ndcg_at_k, mrr_at_k
from src.core.infra.kafka_queue import KafkaMessage

# --- JSON Logging Setup (Phase 2.2) ---
class UUIDFormatter(logging.Formatter):
    def format(self, record):
        record.correlation_id = getattr(record, 'correlation_id', '-')
        return super().format(record)

def setup_json_logging():
    handler = logging.StreamHandler()
    formatter = UUIDFormatter(
        '%(asctime)s %(levelname)s %(name)s [%(correlation_id)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
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
cold_start: Optional[ColdStartRecommender] = None
covisitation: Optional[CovisitationRecommender] = None
sasrec: Optional[SASRecRecommender] = None
kafka_producer = None

TOP_K = 20

# --- Buffer Config (Phase 2.3 + 6.1 + 9.1) ---
REDIS_EVENT_BUFFER = "buffer:collected_events"
REDIS_PREDICTION_BUFFER = "buffer:predictions"
BUFFER_TTL_SECONDS = 3600  # 1 hour (Phase 6.1: prevent OOM)
MAX_BUFFER_SIZE = 10000    # Max items per buffer (Phase 6.1: prevent unbounded growth)
BATCH_SIZE = int(os.getenv("DB_BATCH_SIZE", "50"))
FLUSH_INTERVAL = int(os.getenv("DB_FLUSH_INTERVAL", "5"))

# --- Circuit Breaker (Phase 2.1) ---
sasrec_breaker = pybreaker.CircuitBreaker(
    fail_max=3,
    reset_timeout=60,
)
SASREC_TIMEOUT = 10.0


def call_sasrec_with_fallback(session_aids: List[int], top_k: int, request_id: str = "-"):
    """
    Phase 2.1: Call SASRec with circuit breaker + covisitation fallback.
    """
    def _call():
        try:
            result = sasrec.recommend_multi_objective(session_aids, top_k)
            logger.info(f"[{request_id}] SASRec succeeded", extra={"correlation_id": request_id})
            return result
        except Exception as e:
            logger.warning(f"[{request_id}] SASRec call failed: {e}", extra={"correlation_id": request_id})
            raise
    try:
        return sasrec_breaker.call(_call)
    except pybreaker.CircuitBreakerError:
        logger.warning(f"[{request_id}] SASRec circuit OPEN — falling back to covisitation", extra={"correlation_id": request_id})
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
                batch = session_mgr.redis.lpop(REDIS_EVENT_BUFFER, BATCH_SIZE)
                if not batch:
                    break
                if isinstance(batch, str):
                    batch = [batch]
                for item in batch:
                    try:
                        event_data = json.loads(item)
                        db.log_event(
                            event_data['session_id'], event_data['aid'],
                            event_data['type'], event_data['ts']
                        )
                        flushed_events += 1
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"Failed to parse buffered event: {e}")
            if flushed_events > 0:
                logger.info(f"Flushed {flushed_events} buffered events to PostgreSQL")

            # Flush predictions_log
            while True:
                batch = session_mgr.redis.lpop(REDIS_PREDICTION_BUFFER, BATCH_SIZE)
                if not batch:
                    break
                if isinstance(batch, str):
                    batch = [batch]
                for item in batch:
                    try:
                        pred_data = json.loads(item)
                        db.log_prediction(
                            session_id=pred_data['session_id'],
                            model_used=pred_data['model_used'],
                            session_length=pred_data['session_length'],
                            predicted_clicks=pred_data.get('predicted_clicks', []),
                            predicted_carts=pred_data.get('predicted_carts', []),
                            predicted_orders=pred_data.get('predicted_orders', []),
                            latency_ms=pred_data['latency_ms']
                        )
                        flushed_predictions += 1
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"Failed to parse buffered prediction: {e}")
            if flushed_predictions > 0:
                logger.info(f"Flushed {flushed_predictions} buffered predictions to PostgreSQL")

            # Flush online_hits
            while True:
                batch = session_mgr.redis.lpop("buffer:online_hits", BATCH_SIZE)
                if not batch:
                    break
                if isinstance(batch, str):
                    batch = [batch]
                hits = []
                for item in batch:
                    try:
                        hit_data = json.loads(item)
                        hits.append((hit_data['session_id'], hit_data['aid'], hit_data['event_type'], hit_data['is_hit']))
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"Failed to parse buffered online_hit: {e}")
                if hits:
                    db.log_online_hits_batch(hits)
                    logger.info(f"Flushed {len(hits)} buffered online_hits to PostgreSQL")

            # Flush online_metrics (5.1)
            while True:
                batch = session_mgr.redis.lpop("buffer:online_metrics", BATCH_SIZE)
                if not batch:
                    break
                if isinstance(batch, str):
                    batch = [batch]
                for item in batch:
                    try:
                        metric_data = json.loads(item)
                        db.log_online_metrics(
                            session_id=metric_data['session_id'],
                            model_used=metric_data['model_used'],
                            event_type=metric_data['event_type'],
                            metrics=metric_data['metrics'],
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
            if cold_start:
                cold_start._popular_cache.clear()
                logger.info("Popular items cache cleared")
        except Exception as e:
            logger.error(f"Error in refresh_ranks_task: {e}")
        await asyncio.sleep(120)


# --- Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    global session_mgr, db, cold_start, covisitation, sasrec, kafka_producer, kafka_queue

    logger.info("Starting OTTO API Server...")

    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    session_mgr = SessionManager(host=redis_host, port=redis_port)

    pg_host = os.getenv("POSTGRES_HOST", "localhost")
    pg_port = int(os.getenv("POSTGRES_PORT", "5432"))
    pg_user = os.getenv("POSTGRES_USER", "otto")
    pg_pass = os.getenv("POSTGRES_PASSWORD", "otto123")
    pg_db = os.getenv("POSTGRES_DB", "otto_recommender")
    db = Database(host=pg_host, port=pg_port, dbname=pg_db, user=pg_user, password=pg_pass)

    try:
        covisitation = CovisitationRecommender(matrix_dir="datasets")
        logger.info("Covisitation recommender loaded")
    except Exception as e:
        logger.warning(f"Covisitation not available: {e}")
        covisitation = None

    cold_start = ColdStartRecommender(db=db, covisitation_recommender=covisitation)

    remote_url = os.getenv("SASREC_REMOTE_URL", "https://rs-model1.vucongtuanduong.dpdns.org/")
    if not remote_url:
        logger.error("SASREC_REMOTE_URL is not set! Exiting...")
        sys.exit(1)

    sasrec = SASRecRecommender(remote_url=remote_url)
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
                logger.info("Kafka producer + queue connected (after %d attempts)", attempt)
                return
            except Exception as e:
                logger.warning("Kafka not available yet (attempt %d): %s", attempt, e)
                await asyncio.sleep(5)

    kafka_init_task = asyncio.create_task(_init_kafka_background())

    asyncio.create_task(flush_db_buffers_task())
    asyncio.create_task(refresh_ranks_task())
    logger.info("Background tasks started (DB buffer flush, rank refresh)")

    yield

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
    corr_id = getattr(request.state, 'correlation_id', '-')
    ts = event.ts or int(time.time() * 1000)

    logger.info(f"[{corr_id}] Event received: session={event.session_id} aid={event.aid} type={event.type}")

    # 1. Append to Redis session
    session_length = session_mgr.append_event(event.session_id, event.aid, event.type, ts)

    # 2. Get recommendations (model selection logic)
    cached_recs = session_mgr.get_last_recommendations(event.session_id)
    should_recompute = (
        session_length % 3 == 0 or
        event.type in ["carts", "orders"] or
        not cached_recs
    )

    if not should_recompute and cached_recs:
        model_used = "cached_hybrid"
        recommendations = cached_recs
    else:
        session_aids = session_mgr.get_session_aids(event.session_id)
        if session_length < 3:
            model_used = "cold_start"
            recommendations = cold_start.recommend(session_aids, TOP_K)
        elif 3 <= session_length < 10:
            model_used = "covisitation"
            if covisitation:
                try:
                    recommendations = covisitation.recommend_multi_objective(session_aids, TOP_K)
                    if not any(recommendations.values()):
                        logger.warning(f"[{corr_id}] Covisitation no results, falling back to cold_start")
                        model_used = "covisitation_fallback_cold_start"
                        recommendations = cold_start.recommend(session_aids, TOP_K)
                except Exception as e:
                    logger.warning(f"[{corr_id}] Covisitation failed: {e}")
                    recommendations = cold_start.recommend(session_aids, TOP_K)
            else:
                recommendations = cold_start.recommend(session_aids, TOP_K)
        else:
            model_used = "sasrec_deep_learning"
            try:
                recommendations = call_sasrec_with_fallback(session_aids, TOP_K, request_id=corr_id)
            except pybreaker.CircuitBreakerError:
                logger.warning(f"[{corr_id}] SASRec circuit open, fallback to covisitation")
                model_used = "sasrec_fallback_covisitation"
                if covisitation:
                    recommendations = covisitation.recommend_multi_objective(session_aids, TOP_K)
                else:
                    recommendations = cold_start.recommend(session_aids, TOP_K)
            except Exception as e:
                logger.error(f"[{corr_id}] SASRec unexpected error: {e}")
                model_used = "sasrec_error_covisitation"
                if covisitation:
                    recommendations = covisitation.recommend_multi_objective(session_aids, TOP_K)
                else:
                    recommendations = cold_start.recommend(session_aids, TOP_K)

        session_mgr.store_recommendations(event.session_id, recommendations)

    # 3. Publish to Kafka via queue (non-blocking, fire-and-forget)
    if kafka_queue:
        kafka_queue.put_nowait(KafkaMessage(
            topic="user-events",
            message={"session_id": event.session_id, "aid": event.aid, "type": event.type, "ts": ts, "model_used": model_used},
            key=str(event.session_id)
        ))
    else:
        logger.warning(f"[{corr_id}] kafka_queue is None, skipping Kafka publish")

    # 4. Buffer event to Redis (Phase 2.3 batch writes + 6.1 TTL protection)
    event_data = json.dumps({"session_id": event.session_id, "aid": event.aid, "type": event.type, "ts": ts})
    session_mgr.redis.rpush(REDIS_EVENT_BUFFER, event_data)
    session_mgr.redis.ltrim(REDIS_EVENT_BUFFER, -MAX_BUFFER_SIZE, -1)  # Phase 6.1: Max length
    session_mgr.redis.expire(REDIS_EVENT_BUFFER, BUFFER_TTL_SECONDS)    # Phase 6.1: TTL

    latency_ms = (time.time() - start_time) * 1000

    # 5. Buffer prediction to Redis (Phase 2.3 batch writes)
    pred_data = json.dumps({
        "session_id": event.session_id,
        "model_used": model_used,
        "session_length": session_length,
        "predicted_clicks": recommendations.get("clicks", []),
        "predicted_carts": recommendations.get("carts", []),
        "predicted_orders": recommendations.get("orders", []),
        "latency_ms": latency_ms
    })
    session_mgr.redis.rpush(REDIS_PREDICTION_BUFFER, pred_data)
    session_mgr.redis.ltrim(REDIS_PREDICTION_BUFFER, -MAX_BUFFER_SIZE, -1)  # Phase 6.1: Max length
    session_mgr.redis.expire(REDIS_PREDICTION_BUFFER, BUFFER_TTL_SECONDS)    # Phase 6.1: TTL

# 6. Online hit tracking (buffer to Redis + 6.1 TTL protection)
    if event.type in ["carts", "orders"]:
        all_recs = set(recommendations.get("clicks", []) + recommendations.get("carts", []) + recommendations.get("orders", []))
        is_hit = event.aid in all_recs
        session_mgr.redis.rpush("buffer:online_hits", json.dumps({
            "session_id": event.session_id, "aid": event.aid, "event_type": event.type, "is_hit": is_hit
        }))
        session_mgr.redis.ltrim("buffer:online_hits", -MAX_BUFFER_SIZE, -1)
        session_mgr.redis.expire("buffer:online_hits", BUFFER_TTL_SECONDS)

        # 5.1: Calculate and log Recall@K, NDCG@K, MRR@K
        ground_truth = [event.aid]
        all_recs_list = recommendations.get("clicks", []) + recommendations.get("carts", []) + recommendations.get("orders", [])
        eval_metrics = {
            "recall@20": recall_at_k(all_recs_list, ground_truth, k=20),
            "ndcg@20": ndcg_at_k(all_recs_list, ground_truth, k=20),
            "mrr@20": mrr_at_k(all_recs_list, ground_truth, k=20),
            "hit_rate": 1.0 if is_hit else 0.0,
        }
        session_mgr.redis.rpush("buffer:online_metrics", json.dumps({
            "session_id": event.session_id,
            "model_used": model_used,
            "event_type": event.type,
            "metrics": eval_metrics,
        }))
        session_mgr.redis.ltrim("buffer:online_metrics", -MAX_BUFFER_SIZE, -1)
        session_mgr.redis.expire("buffer:online_metrics", BUFFER_TTL_SECONDS)

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
    events = session_mgr.get_session(session_id)
    return SessionResponse(session_id=session_id, events=events, length=len(events))


@app.get("/api/recommend/{session_id}")
async def get_recommendations(session_id: int, top_k: int = 20):
    session_aids = session_mgr.get_session_aids(session_id)
    session_length = len(session_aids)

    if session_length < 3:
        model_used = "cold_start"
        recommendations = cold_start.recommend(session_aids, top_k)
    elif 3 <= session_length < 10:
        model_used = "covisitation"
        if covisitation:
            recommendations = covisitation.recommend_multi_objective(session_aids, top_k)
        else:
            recommendations = cold_start.recommend(session_aids, top_k)
    else:
        model_used = "sasrec_deep_learning"
        try:
            recommendations = sasrec.recommend_multi_objective(session_aids, top_k)
        except Exception:
            if covisitation:
                recommendations = covisitation.recommend_multi_objective(session_aids, top_k)
            else:
                recommendations = cold_start.recommend(session_aids, top_k)

    return {
        "session_id": session_id,
        "session_length": session_length,
        "model_used": model_used,
        "recommendations": recommendations,
    }


@app.get("/api/stats")
async def get_stats():
    return {
        "active_sessions": session_mgr.get_active_session_count() if session_mgr else 0,
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
        r.ping()
        redis_info = {
            "status": "ok",
            "memory_mb": r.info("memory")["used_memory_human"],
            "connected_clients": r.info("clients")["connected_clients"],
            "db_keys": r.dbsize()
        }
    except Exception as e:
        redis_status = f"error: {e}"
        redis_info = {"status": "error", "error": str(e)}

    # PostgreSQL health
    pg_status = "ok"
    pg_info = {}
    try:
        with db.cursor() as cur:
            cur.execute("SELECT 1")
            cur.execute("SELECT COUNT(*) FROM pg_stat_activity")
            row = cur.fetchone()
            conn_count = row['count'] if row else 0
        pg_info = {
            "status": "ok",
            "active_connections": conn_count
        }
        logger.debug(f"Postgres health OK: {conn_count} connections")
    except Exception as e:
        logger.error(f"Postgres health check failed: {e}")
        pg_status = f"error: {e}"
        pg_info = {"status": "error", "error": str(e)}

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

    # SASRec health (ping + latency)
    sasrec_status = "ok"
    sasrec_info = {}
    try:
        import urllib.request
        import urllib.error
        start = time.time()
        req = urllib.request.Request(sasrec.remote_url.rstrip('/') + "/health",
                                    headers={"User-Agent": "OTTO-API/1.0"})
        urllib.request.urlopen(req, timeout=5)
        latency = (time.time() - start) * 1000
        sasrec_info = {"status": "ok", "latency_ms": round(latency, 1), "url": sasrec.remote_url}
    except urllib.error.URLError:
        sasrec_status = "unreachable"
        sasrec_info = {"status": "unreachable", "circuit_state": str(sasrec_breaker._state)}
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
        sasrec=sasrec_info
    )


if __name__ == "__main__":
    import uvicorn
    reload = os.getenv("RELOAD", "false").lower() == "true"
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=reload)