"""
Redis-based session manager.
Stores session events as a list in Redis with TTL auto-cleanup.
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
import redis
from src.core import SparkService

logger = logging.getLogger(__name__)

SESSION_TTL_SECONDS = 30 * 60  # 30 minutes


class SessionManager:
    """Manages user sessions in Redis."""

    def __init__(self, host: str = None, port: int = None, db: int = 0):
        host = host or os.getenv("REDIS_HOST", "localhost")
        port = port or int(os.getenv("REDIS_PORT", "6379"))
        self.redis = redis.Redis(host=host, port=port, db=db, decode_responses=True)
        try:
            self.redis.ping()
            logger.info("Connected to Redis")
        except redis.ConnectionError:
            logger.warning("Redis not available — session management will fail")

    def load_covisitation_matrix(self, parquet_path: str) -> None:
        """
        Loads the co-visitation matrix from Parquet file to Redis using Spark.
        Matches the loading logic in test_load_covisited_matrix_to_redis.py.
        """
        logger.info(f"Loading co-visitation matrix from {parquet_path} into Redis using Spark...")

        spark_service = SparkService()
        spark = spark_service.spark_session
        df = spark.read.parquet(str(parquet_path))
        logger.info(f"Total rows to load from Parquet: {df.count()}")
        
        # Giới hạn số lượng kết nối đồng thời vào Redis (tránh làm ngộp Redis)
        df_optimized = df.coalesce(10)
        
        # Define partition writer
        def send_partition_to_redis(partition):
            host = os.getenv("REDIS_HOST", "localhost")
            port = int(os.getenv("REDIS_PORT", "6379"))
            
            r = redis.Redis(host=host, port=port, db=0, decode_responses=True)
            pipe = r.pipeline(transaction=False)
            
            batch_size = 5000
            count = 0
            
            for row in partition:
                aid = row['aid']
                candidates = row['candidates']
                aid2_list = [str(c['aid2']) for c in candidates]
                
                if aid2_list:
                    key = f"covis:{aid}"
                    pipe.delete(key)
                    pipe.rpush(key, *aid2_list)
                    count += 1
                    
                if count % batch_size == 0:
                    pipe.execute()
            
            pipe.execute()
            
        df_optimized.foreachPartition(send_partition_to_redis)
        logger.info("Successfully loaded co-visitation matrix to Redis!")
        
        spark.stop()

    def get_covisitation(self, aid: int | str, top_k: int = 20) -> dict:
        """
        Retrieve related products (candidates) for a single product (aid) from Redis.
        """
        key = f"covis:{aid}"
        raw_list = self.redis.lrange(key, 0, top_k - 1)
        raw_list = [int(x) for x in raw_list]
        orders = raw_list[:2]
        carts = raw_list[2:4] if len(raw_list) > 5 else []
        clicks = raw_list[4:top_k] if len(raw_list) > 10 else []
        return {
            "orders": orders,
            "carts": carts,
            "clicks": clicks,
        }

    def _key(self, session_id: int | str) -> str:
        return f"session:{session_id}"

    def append_event(
        self, session_id: int | str, aid: int, event_type: str, ts: Optional[int] = None
    ) -> int:
        """
        Append an event to a session. Returns the new session length.
        """
        key = self._key(session_id)
        event = {
            "aid": aid,
            "type": event_type,
            "ts": ts or int(time.time() * 1000),
        }
        pipe = self.redis.pipeline()
        pipe.rpush(key, json.dumps(event))
        pipe.expire(key, SESSION_TTL_SECONDS)
        results = pipe.execute()
        return results[0]  # length after rpush

    def get_session(self, session_id: int | str) -> List[Dict[str, Any]]:
        """Get all events in a session."""
        key = self._key(session_id)
        raw_events = self.redis.lrange(key, 0, -1)
        return [json.loads(e) for e in raw_events]

    def get_session_aids(self, session_id: int | str) -> List[int]:
        """Get just the aid list for a session (for model input)."""
        events = self.get_session(session_id)
        return [e["aid"] for e in events]

    def get_session_length(self, session_id: int | str) -> int:
        """Get the number of events in a session."""
        return self.redis.llen(self._key(session_id))

    def delete_session(self, session_id: int | str) -> None:
        """Delete a session."""
        self.redis.delete(self._key(session_id))
        self.redis.delete(f"recs:{session_id}")

    def store_recommendations(
        self, session_id: int | str, recommendations: Dict[str, List[int]]
    ) -> None:
        """Store the latest recommendations for a session for evaluation."""
        key = f"recs:{session_id}"
        self.redis.setex(key, SESSION_TTL_SECONDS, json.dumps(recommendations))

    def get_last_recommendations(
        self, session_id: int | str
    ) -> Optional[Dict[str, List[int]]]:
        """Get the cached recommendations for a session."""
        key = f"recs:{session_id}"
        data = self.redis.get(key)
        return json.loads(data) if data else None

    def get_active_session_count(self) -> int:
        """Get approximate count of active sessions."""
        cursor = 0
        count = 0
        while True:
            cursor, keys = self.redis.scan(cursor, match="session:*", count=100)
            count += len(keys)
            if cursor == 0:
                break
        return count
