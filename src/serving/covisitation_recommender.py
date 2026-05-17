import json
from pathlib import Path
from typing import List, Dict, Optional
import pandas as pd
from collections import defaultdict


class CovisitationRecommender:
    """Lightweight covisitation-based recommender (no GPU needed)."""

    def __init__(self, matrix_dir: str = "datasets"):
        self.matrix_dir = Path(matrix_dir)
        self.clicks_matrix = None
        self.carts_orders_matrix = None
        self.buy2buy_matrix = None
        self._load_matrices()

    def _load_matrices(self):
        """Load pre-computed covisitation matrices."""
        try:
            clicks_path = self.matrix_dir / "clicks_matrix.parquet"
            if clicks_path.exists():
                df = pd.read_parquet(clicks_path)
                self.clicks_matrix = self._build_lookup(df, "aid1", "aid2", "weight")
        except Exception as e:
            print(f"Error loading clicks matrix: {e}")

        try:
            carts_orders_path = self.matrix_dir / "carts_orders_matrix.parquet"
            if carts_orders_path.exists():
                df = pd.read_parquet(carts_orders_path)
                self.carts_orders_matrix = self._build_lookup(df, "aid1", "aid2", "weight")
        except Exception as e:
            print(f"Error loading carts_orders matrix: {e}")

        try:
            buy2buy_path = self.matrix_dir / "buy2buy_matrix.parquet"
            if buy2buy_path.exists():
                df = pd.read_parquet(buy2buy_path)
                self.buy2buy_matrix = self._build_lookup(df, "aid1", "aid2", "weight")
        except Exception as e:
            print(f"Error loading buy2buy matrix: {e}")

    def _build_lookup(self, df, key_col: str, value_col: str, weight_col: str) -> Dict[int, List[tuple]]:
        """Build a lookup dictionary from DataFrame using efficient groupby."""
        lookup = defaultdict(list)
        for key, group in df.groupby(key_col):
            lookup[key] = list(zip(group[value_col].tolist(), group[weight_col].tolist()))
        return dict(lookup)

    def recommend(
        self,
        session_items: List[int],
        event_type: str = "clicks",
        top_k: int = 20,
    ) -> List[int]:
        """
        Recommend items based on session history.

        Args:
            session_items: List of item IDs in the current session
            event_type: Type of prediction (clicks, carts, orders)
            top_k: Number of recommendations to return

        Returns:
            List of recommended item IDs
        """
        scores = defaultdict(float)

        for item in session_items:
            if event_type in ["carts", "orders"] and self.carts_orders_matrix:
                candidates = self.carts_orders_matrix.get(item, [])
                for candidate, weight in candidates:
                    scores[candidate] += weight

            if event_type == "clicks" and self.clicks_matrix:
                candidates = self.clicks_matrix.get(item, [])
                for candidate, weight in candidates:
                    scores[candidate] += weight

            if event_type in ["carts", "orders"] and self.buy2buy_matrix:
                candidates = self.buy2buy_matrix.get(item, [])
                for candidate, weight in candidates:
                    scores[candidate] += weight * 2

        for item in session_items:
            scores.pop(item, None)

        sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [item for item, _ in sorted_items[:top_k]]

    def recommend_multi_objective(
        self,
        session_items: List[int],
        top_k: int = 20,
    ) -> Dict[str, List[int]]:
        """
        Multi-objective recommendation for clicks, carts, and orders.

        Returns recommendations per event type with OTTO weights:
        - clicks: 0.1
        - carts: 0.3
        - orders: 0.6
        """
        return {
            "clicks": self.recommend(session_items, "clicks", top_k),
            "carts": self.recommend(session_items, "carts", top_k),
            "orders": self.recommend(session_items, "orders", top_k),
        }
