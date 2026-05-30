"""
Redis-based session manager.
Stores session events as a list in Redis with TTL auto-cleanup.
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
from collections import Counter
import redis as redis_sync
import redis.asyncio as redis

logger = logging.getLogger(__name__)

SESSION_TTL_SECONDS = 30 * 60  # 30 minutes


class SessionManager:
    """Manages user sessions in Redis."""

    def __init__(self, host: str = None, port: int = None, db: int = 0):
        host = host or os.getenv("REDIS_HOST", "localhost")
        port = port or int(os.getenv("REDIS_PORT", "6379"))
        self.redis = redis.Redis(host=host, port=port, db=db, decode_responses=True)

    async def get_covisitation_recommendations(self, aids: List[int], top_k: int = 20) -> Dict[str, List[int]]:
        # nhận nhiều aid đã tương tác vào, rồi trả về topk 
        # dùng pipeline() thay vì N round-trip Redis (mỗi await 1 lần), giờ chỉ còn 1 round-trip duy nhất. Kết quả trả về là list các list, đúng thứ tự các lrange bạn push vào pipeline.

        freq: Counter = Counter()
        pipe = self.redis.pipeline()     # dùng pipeline() thay cho N lần gọi await lrange
        for aid in set(aids):  #  tránh đếm trùng từ một sản phẩm gốc
            pipe.lrange(f"covis:{aid}", 0, top_k - 1)
        
        results = await pipe.execute()

        for raw in results:
            #  chỉ mục để biết vị trí của item trong danh sách co-visitation
            for rank, x in enumerate(raw):
                item_id = int(x)
                # Tính điểm cộng giảm dần theo vị trí: vị trí 0 được +1.0, vị trí 1 được +0.5, ...
                weight = 1.0 / (rank + 1)
                freq[item_id] += weight
                
        clicked = set(aids)
        #  bỏ các aid người dùng đã tương tác trong session này
        # freq.most_common(top_k) sắp xếp dựa trên tổng số điểm 
        merged = [aid for aid, _ in freq.most_common(top_k + len(clicked)) if aid not in clicked]
        
        n = len(merged)
        if n == 0:
            return {"orders": [], "carts": [], "clicks": []}
        size = n // 3
        remainder = n % 3
        idx1 = size + (1 if remainder > 0 else 0)
        idx2 = idx1 + size + (1 if remainder > 1 else 0)
        
        return {
            "orders": merged[:idx1],
            "carts": merged[idx1:idx2],
            "clicks": merged[idx2:],
        }

    def _key(self, session_id: int | str) -> str:
        return f"session:{session_id}"

    async def append_event(
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
        results = await pipe.execute()
        return results[0]  # length after rpush

    async def get_session(self, session_id: int | str) -> List[Dict[str, Any]]:
        """Get all events in a session."""
        key = self._key(session_id)
        raw_events =await self.redis.lrange(key, 0, -1)
        return [json.loads(e) for e in raw_events]

    async def get_session_aids(self, session_id: int | str) -> List[int]:
        """Get just the aid list for a session (for model input)."""
        events = await self.get_session(session_id)
        return [e["aid"] for e in events]

    async def get_session_sequences(self, session_id: int | str):
        # lấy list toàn bộ các aid, type, ts của 1 session 
        events = await self.get_session(session_id)
        aids = [e["aid"] for e in events]
        types = [e["type"] for e in events]
        tss = [e["ts"] for e in events]
        return aids, types, tss

    async def store_recommendations(
        self, session_id: int | str, recommendations: Dict[str, List[int]]
    ) -> None:
        """Store the latest recommendations for a session for evaluation."""
        key = f"recs:{session_id}"
        await self.redis.setex(key, SESSION_TTL_SECONDS, json.dumps(recommendations))

    async def get_last_recommendations(self, session_id: int | str) -> Optional[Dict[str, List[int]]]:
        """Get the cached recommendations for a session."""
        key = f"recs:{session_id}"
        data =  await self.redis.get(key)
        return json.loads(data) if data else None

    async def get_active_session_count(self) -> int:
        """Get approximate count of active sessions."""
        cursor = 0
        count = 0
        while True:
            cursor, keys = await self.redis.scan(cursor, match="session:*", count=100000)
            count += len(keys)
            if cursor == 0:
                break
        return count
