"""
Cold-start recommendation strategies.
Used when session is too short for SASRec (< 3 events).
"""

import logging
from typing import Dict, List, Optional

from src.api.db import Database

logger = logging.getLogger(__name__)

# Fallback popular items if DB is empty or unavailable
FALLBACK_POPULAR = list(range(1, 21))  # placeholder


class ColdStartRecommender:
    """Handles cold-start recommendations using popular items from DB."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db
        self._popular_cache: Dict[str, List[int]] = {}

    def _get_popular(self, event_type: str, top_k: int = 20) -> List[int]:
        """Get popular items, with caching."""
        cache_key = f"{event_type}_{top_k}"
        if cache_key not in self._popular_cache:
            if self.db is not None:
                items = self.db.get_popular_items(event_type, top_k)
                self._popular_cache[cache_key] = (
                    items if items else FALLBACK_POPULAR[:top_k]
                )
            else:
                self._popular_cache[cache_key] = FALLBACK_POPULAR[:top_k]
        return self._popular_cache[cache_key]

    def recommend_empty_session(self, top_k: int = 20) -> Dict[str, List[int]]:
        """Session with 0 events: global popular items."""
        return {
            "clicks": self._get_popular("clicks", top_k),
            "carts": self._get_popular("carts", top_k),
            "orders": self._get_popular("orders", top_k),
        }
