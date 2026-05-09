"""
Cold-start recommendation strategies.
Used when session is too short for SASRec (< 3 events).
"""

import logging
from typing import Dict, List
from collections import defaultdict

from src.api.db import Database

logger = logging.getLogger(__name__)

# Fallback popular items if DB is empty
FALLBACK_POPULAR = list(range(1, 21))  # placeholder


class ColdStartRecommender:
    """Handles cold-start recommendations using popular items and covisitation."""

    def __init__(self, db: Database, covisitation_recommender=None):
        self.db = db
        self.covisitation = covisitation_recommender
        self._popular_cache: Dict[str, List[int]] = {}

    def _get_popular(self, event_type: str, top_k: int = 20) -> List[int]:
        """Get popular items, with caching."""
        cache_key = f"{event_type}_{top_k}"
        if cache_key not in self._popular_cache:
            items = self.db.get_popular_items(event_type, top_k)
            self._popular_cache[cache_key] = items if items else FALLBACK_POPULAR[:top_k]
        return self._popular_cache[cache_key]

    def recommend_empty_session(self, top_k: int = 20) -> Dict[str, List[int]]:
        """Session with 0 events: global popular items."""
        return {
            "clicks": self._get_popular("clicks", top_k),
            "carts": self._get_popular("carts", top_k),
            "orders": self._get_popular("orders", top_k),
        }

    def recommend_short_session(
        self, session_aids: List[int], top_k: int = 20
    ) -> Dict[str, List[int]]:
        """
        Session with 1-2 events: covisitation + popular items fallback.
        """
        result = {"clicks": [], "carts": [], "orders": []}

        # Try covisitation first
        if self.covisitation:
            try:
                covis_result = self.covisitation.recommend_multi_objective(session_aids, top_k)
                result = covis_result
            except Exception as e:
                logger.warning(f"Covisitation failed: {e}")

        # Fill with popular items if not enough
        for event_type in ["clicks", "carts", "orders"]:
            if len(result[event_type]) < top_k:
                popular = self._get_popular(event_type, top_k * 2)
                existing = set(result[event_type]) | set(session_aids)
                for item in popular:
                    if item not in existing and len(result[event_type]) < top_k:
                        result[event_type].append(item)

        return result

    def recommend(
        self, session_aids: List[int], top_k: int = 20
    ) -> Dict[str, List[int]]:
        """Main entry: route to empty or short session strategy."""
        if len(session_aids) == 0:
            return self.recommend_empty_session(top_k)
        else:
            return self.recommend_short_session(session_aids, top_k)
