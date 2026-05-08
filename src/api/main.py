"""
FastAPI Server — OTTO Recommender Pipeline API.
Receives events from clients, manages sessions via Redis,
returns recommendations, and publishes events to Kafka.
"""

import time
import logging
import asyncio
import sys
from pathlib import Path
from contextlib import asynccontextmanager
from typing import List, Optional

# Add the project root to sys.path to resolve 'src' imports when running directly
root_dir = str(Path(__file__).resolve().parents[2])
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.api.session_manager import SessionManager
from src.api.db import Database
from src.api.cold_start import ColdStartRecommender
from src.serving.covisitation_recommender import CovisitationRecommender

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

# --- Global singletons (initialized in lifespan) ---
session_mgr: Optional[SessionManager] = None
db: Optional[Database] = None
cold_start: Optional[ColdStartRecommender] = None
covisitation: Optional[CovisitationRecommender] = None
kafka_producer = None  # optional, will try to connect

# Threshold: session needs this many events before using SASRec
COLD_START_THRESHOLD = 3
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


# --- Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    global session_mgr, db, cold_start, covisitation, kafka_producer

    logger.info("Starting OTTO API Server...")

    # Init Redis
    session_mgr = SessionManager(host="localhost", port=6379)

    # Init PostgreSQL
    db = Database(host="localhost", port=5432, dbname="otto_recommender", user="otto", password="otto123")

    # Init Covisitation recommender
    try:
        covisitation = CovisitationRecommender(matrix_dir="datasets")
        logger.info("Covisitation recommender loaded")
    except Exception as e:
        logger.warning(f"Covisitation not available: {e}")
        covisitation = None

    # Init Cold Start
    cold_start = ColdStartRecommender(db=db, covisitation_recommender=covisitation)

    # Try Kafka (optional for prototype)
    try:
        from src.core.infra.kafka import KafkaProducerService
        kafka_producer = KafkaProducerService()
        await kafka_producer.start()
        logger.info("Kafka producer connected")
    except Exception as e:
        logger.warning(f"Kafka not available (will skip publishing): {e}")
        kafka_producer = None

    # Ensure tables exist
    if db:
        try:
            with db.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS online_hits (
                        id SERIAL PRIMARY KEY,
                        session_id BIGINT,
                        aid INT,
                        event_type TEXT,
                        is_hit BOOLEAN,
                        timestamp TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
        except Exception as e:
            logger.warning(f"Failed to ensure online_hits table: {e}")

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
async def receive_event(event: EventRequest):
    """
    Receive a user event and return recommendations.

    Flow:
    1. Append event to Redis session
    2. Publish to Kafka (if available)
    3. Get recommendations (cold-start or covisitation)
    4. Log prediction to PostgreSQL
    5. Return top-K recommendations
    """
    start_time = time.time()

    # 1. Append to Redis
    ts = event.ts or int(time.time() * 1000)
    session_length = session_mgr.append_event(event.session_id, event.aid, event.type, ts)

    # 2. Publish to Kafka (fire-and-forget)
    if kafka_producer:
        try:
            await kafka_producer.send(
                "user-events",
                {"session_id": event.session_id, "aid": event.aid, "type": event.type, "ts": ts},
                key=str(event.session_id),
            )
        except Exception as e:
            logger.warning(f"Kafka publish failed: {e}")

    # 3. Save event to PostgreSQL for retrain
    if db:
        db.log_event(event.session_id, event.aid, event.type, ts)

    # 4. Get recommendations
    session_aids = session_mgr.get_session_aids(event.session_id)

    if session_length < COLD_START_THRESHOLD:
        model_used = "cold_start"
        recommendations = cold_start.recommend(session_aids, TOP_K)
    else:
        # Use covisitation (SASRec can be added later when checkpoint is ready)
        model_used = "covisitation"
        if covisitation:
            try:
                recommendations = covisitation.recommend_multi_objective(session_aids, TOP_K)
            except Exception as e:
                logger.warning(f"Covisitation failed, falling back: {e}")
                recommendations = cold_start.recommend(session_aids, TOP_K)
        else:
            recommendations = cold_start.recommend(session_aids, TOP_K)

    latency_ms = (time.time() - start_time) * 1000

    # 5. Log prediction
    if db:
        db.log_prediction(
            session_id=event.session_id,
            model_used=model_used,
            session_length=session_length,
            predicted_clicks=recommendations.get("clicks", []),
            predicted_carts=recommendations.get("carts", []),
            predicted_orders=recommendations.get("orders", []),
            latency_ms=latency_ms,
        )

    # 5. Online Evaluation (Hit Checking)
    if db and event.type in ["carts", "orders"]:
        last_recs = session_mgr.get_last_recommendations(event.session_id)
        if last_recs:
            # Check if this aid was recommended for ANY type
            all_recs = set(last_recs.get("clicks", []) + last_recs.get("carts", []) + last_recs.get("orders", []))
            is_hit = event.aid in all_recs
            db.log_online_hit(event.session_id, event.aid, event.type, is_hit)
            if is_hit:
                logger.info(f"🎯 ONLINE HIT! Session {event.session_id} {event.type} aid {event.aid}")

    # 6. Cache current recommendations for next event evaluation
    session_mgr.store_recommendations(event.session_id, recommendations)

    return EventResponse(
        status="ok",
        session_length=session_length,
        model_used=model_used,
        recommendations=recommendations,
        latency_ms=round(latency_ms, 2),
    )


@app.get("/api/session/{session_id}", response_model=SessionResponse)
async def get_session(session_id: int):
    """Get the current event history for a session."""
    events = session_mgr.get_session(session_id)
    return SessionResponse(session_id=session_id, events=events, length=len(events))


@app.get("/api/recommend/{session_id}")
async def get_recommendations(session_id: int, top_k: int = 20):
    """Get recommendations for an existing session (without adding a new event)."""
    session_aids = session_mgr.get_session_aids(session_id)
    session_length = len(session_aids)

    if session_length < COLD_START_THRESHOLD:
        model_used = "cold_start"
        recommendations = cold_start.recommend(session_aids, top_k)
    else:
        model_used = "covisitation"
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
    """Get system statistics."""
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
    }


@app.get("/api/popular/{event_type}")
async def get_popular(event_type: str, limit: int = 10):
    """Get popular items with counts."""
    items = db.get_popular_items_with_counts(event_type, limit) if db else []
    return {"event_type": event_type, "items": items}


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Check service health."""
    redis_status = "ok"
    pg_status = "ok"

    try:
        session_mgr.redis.ping()
    except Exception:
        redis_status = "error"

    try:
        with db.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception:
        pg_status = "error"

    overall = "ok" if redis_status == "ok" and pg_status == "ok" else "degraded"
    return HealthResponse(status=overall, redis=redis_status, postgres=pg_status)


if __name__ == "__main__":
    import uvicorn
    # Use string reference for reload to work correctly
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True)
