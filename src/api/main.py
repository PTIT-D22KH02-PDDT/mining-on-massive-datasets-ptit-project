"""
FastAPI Server - OTTO Recommender Pipeline API.
Receives events from clients, manages sessions via Redis,
returns recommendations (Hybrid Inference), and publishes events to Kafka.
"""

import time
import logging
import asyncio
import sys
import os
from pathlib import Path
from contextlib import asynccontextmanager
from typing import List, Optional

# Add the project root to sys.path to resolve 'src' imports when running directly
root_dir = str(Path(__file__).resolve().parents[2])
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

from src.api.session_manager import SessionManager
from src.api.db import Database
from src.api.cold_start import ColdStartRecommender
from src.serving.covisitation_recommender import CovisitationRecommender
from src.serving.sasrec_recommender import SASRecRecommender

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

# --- Global singletons (initialized in lifespan) ---
session_mgr: Optional[SessionManager] = None
db: Optional[Database] = None
cold_start: Optional[ColdStartRecommender] = None
covisitation: Optional[CovisitationRecommender] = None
sasrec: Optional[SASRecRecommender] = None
kafka_producer = None  # optional, will try to connect

TOP_K = 20

# --- Pydantic Models ---
class EventRequest(BaseModel):
    session_id: int
    aid: int
    type: str  # "clicks", "carts", "orders"
    ts: Optional[int] = None

class EventResponse(BaseModel):
    status: str
    session_length: int
    model_used: str
    recommendations: dict  # {clicks: [...], carts: [...], orders: [...]}
    latency_ms: float

class SessionResponse(BaseModel):
    session_id: int
    events: list
    length: int

class HealthResponse(BaseModel):
    status: str
    redis: str
    postgres: str

# --- Background Task for Ranking ---
async def refresh_ranks_task():
    """Periodically refresh popular items ranks in the database."""
    while True:
        try:
            if db:
                db.refresh_popular_items_ranks()
            
            # Also clear the cold start cache to reflect new popularity
            if cold_start:
                cold_start._popular_cache.clear()
                logger.info("Popular items cache cleared")
        except Exception as e:
            logger.error(f"Error in refresh_ranks_task: {e}")
        # Refresh every 2 minutes
        await asyncio.sleep(120)

# --- Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    global session_mgr, db, cold_start, covisitation, sasrec, kafka_producer

    logger.info("Starting OTTO API Server...")

    # Init Redis
    redis_host = os.getenv("REDIS_HOST", "localhost")
    session_mgr = SessionManager(host=redis_host, port=6379)

    # Init PostgreSQL
    pg_host = os.getenv("POSTGRES_HOST", "localhost")
    pg_user = os.getenv("POSTGRES_USER", "otto")
    pg_pass = os.getenv("POSTGRES_PASSWORD", "otto123")
    pg_db = os.getenv("POSTGRES_DB", "otto_recommender")
    db = Database(host=pg_host, port=5432, dbname=pg_db, user=pg_user, password=pg_pass)

    # Init Covisitation recommender
    try:
        covisitation = CovisitationRecommender(matrix_dir="datasets")
        logger.info("Covisitation recommender loaded")
    except Exception as e:
        logger.warning(f"Covisitation not available: {e}")
        covisitation = None

    # Init Cold Start
    cold_start = ColdStartRecommender(db=db, covisitation_recommender=covisitation)
    
    # Init SASRec (Deep Learning) - FORCED REMOTE MODE
    remote_url = os.getenv("SASREC_REMOTE_URL", "https://rs-model1.vucongtuanduong.dpdns.org/")
    if not remote_url:
        logger.error("CRITICAL: SASREC_REMOTE_URL is not set! Remote inference is REQUIRED. Exiting...")
        sys.exit(1)
    
    sasrec = SASRecRecommender(remote_url=remote_url)
    logger.info(f"SASRec initialized in FORCED REMOTE mode (Kaggle Host: {remote_url})")

    # Try Kafka (optional for prototype)
    try:
        from src.core.infra.kafka import KafkaProducerService
        kafka_producer = KafkaProducerService()
        await kafka_producer.start()
        logger.info("Kafka producer connected")
    except Exception as e:
        logger.warning(f"Kafka not available (will skip publishing): {e}")
        kafka_producer = None

    # Tables are now managed via postgres-init/01_create_tables.sql

    # Start the rank refresh background task
    asyncio.create_task(refresh_ranks_task())
    logger.info("Background rank refresh task started")

    yield

    # Shutdown
    if kafka_producer:
        await kafka_producer.stop()
    if db:
        db.close()
    logger.info("OTTO API Server shut down")


# --- FastAPI App ---
app = FastAPI(
    title="OTTO Recommender Pipeline API",
    description="Receives user events, manages sessions, returns recommendations",
    version="1.0.0",
    lifespan=lifespan,
)


@app.post("/api/event", response_model=EventResponse)
async def receive_event(event: EventRequest, background_tasks: BackgroundTasks):
    start_time = time.time()

    # 1. Append to Redis (Very fast)
    ts = event.ts or int(time.time() * 1000)
    session_length = session_mgr.append_event(event.session_id, event.aid, event.type, ts)

    # 2. Determine model and recommendations BEFORE Kafka send (model_used needed in event)
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
                        logger.warning("Covisitation returned no results, falling back to cold_start")
                        model_used = "covisitation_fallback_cold_start"
                        recommendations = cold_start.recommend(session_aids, TOP_K)
                except Exception as e:
                    logger.warning(f"Covisitation failed, falling back: {e}")
                    recommendations = cold_start.recommend(session_aids, TOP_K)
            else:
                recommendations = cold_start.recommend(session_aids, TOP_K)
        else:
            model_used = "sasrec_deep_learning"
            recommendations = sasrec.recommend_multi_objective(session_aids, TOP_K)

        session_mgr.store_recommendations(event.session_id, recommendations)

    # 3. Publish to Kafka (now includes model_used)
    if kafka_producer:
        background_tasks.add_task(
            kafka_producer.send,
            "user-events",
            {"session_id": event.session_id, "aid": event.aid, "type": event.type, "ts": ts, "model_used": model_used},
            key=str(event.session_id)
        )

    # Save event to PostgreSQL
    if db:
        background_tasks.add_task(db.log_event, event.session_id, event.aid, event.type, ts)

    latency_ms = (time.time() - start_time) * 1000

    # 4. Background Logging of Predictions & Hits
    if db:
        background_tasks.add_task(
            db.log_prediction,
            session_id=event.session_id,
            model_used=model_used,
            session_length=session_length,
            predicted_clicks=recommendations.get("clicks", []),
            predicted_carts=recommendations.get("carts", []),
            predicted_orders=recommendations.get("orders", []),
            latency_ms=latency_ms
        )

        if event.type in ["carts", "orders"]:
            all_recs = set(recommendations.get("clicks", []) + recommendations.get("carts", []) + recommendations.get("orders", []))
            is_hit = event.aid in all_recs
            background_tasks.add_task(db.log_online_hit, event.session_id, event.aid, event.type, is_hit)

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

    # Hybrid Logic for standalone recommend endpoint
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
        recommendations = sasrec.recommend_multi_objective(session_aids, top_k)

    return {
        "session_id": session_id,
        "session_length": session_length,
        "model_used": model_used,
        "recommendations": recommendations,
    }


@app.get("/api/stats")
async def get_stats():
    """Get rich system statistics for Dashboard."""
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
    }


@app.get("/api/popular/{event_type}")
async def get_popular(event_type: str, limit: int = 10):
    items = db.get_popular_items_with_counts(event_type, limit) if db else []
    return {"event_type": event_type, "items": items}


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    redis_status = "ok"
    pg_status = "ok"
    try: session_mgr.redis.ping()
    except: redis_status = "error"
    try:
        with db.cursor() as cur: cur.execute("SELECT 1")
    except: pg_status = "error"

    overall = "ok" if redis_status == "ok" and pg_status == "ok" else "degraded"
    return HealthResponse(status=overall, redis=redis_status, postgres=pg_status)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True)
