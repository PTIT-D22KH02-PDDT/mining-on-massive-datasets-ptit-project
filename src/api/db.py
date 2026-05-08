"""
Database helper — PostgreSQL connection and common queries.
"""

import logging
from typing import Any, Dict, List, Optional
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)


class Database:
    """Simple PostgreSQL wrapper."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        dbname: str = "otto_recommender",
        user: str = "otto",
        password: str = "otto123",
    ):
        self.conn_params = dict(host=host, port=port, dbname=dbname, user=user, password=password)
        self._conn = None

    def _get_conn(self):
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(**self.conn_params)
            self._conn.autocommit = True
        return self._conn

    @contextmanager
    def cursor(self):
        conn = self._get_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            yield cur
        finally:
            cur.close()

    def log_prediction(
        self,
        session_id: int,
        model_used: str,
        session_length: int,
        predicted_clicks: List[int],
        predicted_carts: List[int],
        predicted_orders: List[int],
        latency_ms: float,
    ):
        """Log a prediction to the database."""
        try:
            with self.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO predictions_log
                        (session_id, model_used, session_length, predicted_clicks, predicted_carts, predicted_orders, latency_ms)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (session_id, model_used, session_length, predicted_clicks, predicted_carts, predicted_orders, latency_ms),
                )
        except Exception as e:
            logger.error(f"Failed to log prediction: {e}")

    def log_event(self, session_id: int, aid: int, event_type: str, ts: int):
        """Save a collected event for retrain."""
        try:
            with self.cursor() as cur:
                cur.execute(
                    "INSERT INTO collected_events (session_id, aid, event_type, ts) VALUES (%s, %s, %s, %s)",
                    (session_id, aid, event_type, ts),
                )
        except Exception as e:
            logger.error(f"Failed to log event: {e}")

    def get_popular_items(self, event_type: str = "clicks", limit: int = 20) -> List[int]:
        """Get pre-computed popular items (AIDs only)."""
        try:
            with self.cursor() as cur:
                cur.execute(
                    "SELECT aid FROM popular_items WHERE event_type = %s AND time_scope = 'all_time' ORDER BY rank LIMIT %s",
                    (event_type, limit),
                )
                return [row["aid"] for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get popular items: {e}")
            return []

    def get_popular_items_with_counts(self, event_type: str = "clicks", limit: int = 10) -> List[Dict]:
        """Get popular items with counts for visualization."""
        try:
            with self.cursor() as cur:
                cur.execute("""
                    SELECT aid, count, rank
                    FROM popular_items
                    WHERE event_type = %s AND time_scope = 'all_time'
                    ORDER BY rank ASC
                    LIMIT %s
                """, (event_type, limit))
                return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get popular items with counts: {e}")
            return []

    def get_prediction_stats(self) -> Dict[str, Any]:
        """Get aggregate prediction statistics."""
        try:
            with self.cursor() as cur:
                cur.execute("""
                    SELECT
                        COUNT(*) as total_predictions,
                        AVG(latency_ms) as avg_latency_ms,
                        COUNT(DISTINCT session_id) as unique_sessions,
                        AVG(session_length) as avg_session_length
                    FROM predictions_log
                """)
                return dict(cur.fetchone() or {})
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}

    def get_model_usage(self) -> List[Dict]:
        """Get model usage breakdown."""
        try:
            with self.cursor() as cur:
                cur.execute("""
                    SELECT model_used, COUNT(*) as count, AVG(latency_ms) as avg_latency
                    FROM predictions_log
                    GROUP BY model_used
                    ORDER BY count DESC
                """)
                return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get model usage: {e}")
            return []

    def get_recent_predictions(self, limit: int = 20) -> List[Dict]:
        """Get recent predictions."""
        try:
            with self.cursor() as cur:
                cur.execute(
                    "SELECT * FROM predictions_log ORDER BY created_at DESC LIMIT %s",
                    (limit,),
                )
                return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get recent predictions: {e}")
            return []

    def get_anomalies(self, limit: int = 50) -> List[Dict]:
        """Get recent anomalies."""
        try:
            with self.cursor() as cur:
                cur.execute(
                    "SELECT * FROM anomaly_logs ORDER BY detected_at DESC LIMIT %s",
                    (limit,),
                )
                return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get anomalies: {e}")
            return []

    def get_collected_events_count(self) -> int:
        """Get total collected events count."""
        try:
            with self.cursor() as cur:
                cur.execute("SELECT COUNT(*) as cnt FROM collected_events")
                row = cur.fetchone()
                return row["cnt"] if row else 0
        except Exception as e:
            logger.error(f"Failed to count events: {e}")
            return 0

    def get_event_distribution(self) -> List[Dict]:
        """Get distribution of event types in collected_events."""
        try:
            with self.cursor() as cur:
                cur.execute("""
                    SELECT event_type, COUNT(*) as count
                    FROM collected_events
                    GROUP BY event_type
                    ORDER BY count DESC
                """)
                return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get event distribution: {e}")
            return []

    def get_latency_history(self, limit: int = 100) -> List[Dict]:
        """Get latency history for plotting."""
        try:
            with self.cursor() as cur:
                cur.execute("""
                    SELECT created_at, latency_ms, model_used
                    FROM predictions_log
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (limit,))
                return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get latency history: {e}")
            return []

    def get_funnel_stats(self) -> Dict:
        """Get conversion funnel data."""
        try:
            with self.cursor() as cur:
                cur.execute("SELECT * FROM funnel_stats ORDER BY computed_at DESC LIMIT 1")
                return dict(cur.fetchone() or {})
        except Exception as e:
            logger.error(f"Failed to get funnel stats: {e}")
            return {}

    def get_hourly_stats(self, limit: int = 24) -> List[Dict]:
        """Get hourly traffic stats."""
        try:
            with self.cursor() as cur:
                cur.execute("SELECT * FROM stats_hourly ORDER BY window_start DESC LIMIT %s", (limit,))
                return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get hourly stats: {e}")
            return []

    def get_session_distribution(self) -> List[Dict]:
        """Get session type/length distribution."""
        try:
            with self.cursor() as cur:
                cur.execute("SELECT * FROM stats_sessions ORDER BY count DESC")
                return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get session distribution: {e}")
            return []

    def get_spark_metrics(self, limit: int = 50) -> List[Dict]:
        """Get recent Spark performance metrics."""
        try:
            with self.cursor() as cur:
                cur.execute("""
                    SELECT * FROM spark_metrics 
                    ORDER BY timestamp DESC 
                    LIMIT %s
                """, (limit,))
                return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get spark metrics: {e}")
            return []

    def log_online_hit(self, session_id: int, aid: int, event_type: str, is_hit: bool):
        """Log whether an order/cart event was a result of a recommendation."""
        try:
            with self.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO online_hits (session_id, aid, event_type, is_hit)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (session_id, aid, event_type, is_hit),
                )
        except Exception as e:
            logger.error(f"Failed to log online hit: {e}")

    def get_hit_rate_stats(self) -> Dict[str, float]:
        """Get aggregate online hit rates."""
        try:
            with self.cursor() as cur:
                cur.execute("""
                    SELECT 
                        COUNT(*) as total_actions,
                        SUM(CASE WHEN is_hit THEN 1 ELSE 0 END) as total_hits,
                        AVG(CASE WHEN is_hit THEN 1.0 ELSE 0.0 END) as hit_rate
                    FROM online_hits
                """)
                return dict(cur.fetchone() or {"total_actions": 0, "total_hits": 0, "hit_rate": 0})
        except Exception as e:
            logger.error(f"Failed to get hit rate stats: {e}")
            return {"total_actions": 0, "total_hits": 0, "hit_rate": 0}

    def close(self):
        if self._conn:
            self._conn.close()
