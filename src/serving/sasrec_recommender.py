import logging
import os
from typing import Dict, List

import httpx

logger = logging.getLogger(__name__)

SASREC_REMOTE_URL = os.getenv("SASREC_REMOTE_URL", "")

class SASRecRecommender:
    def __init__(self, remote_url: str = SASREC_REMOTE_URL):
        self.remote_url = remote_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=10)
        logger.info(f"SASRec initialized in REMOTE mode via {self.remote_url}")

    async def aclose(self):
        await self._client.aclose()

    async def _predict_remote(self, session_aids: List[int], top_k: int) -> List[int]:
        try:
            resp = await self._client.post(
                f"{self.remote_url}/recommend",
                json={
                    "click_sequence": session_aids,
                    "k": top_k,
                    "exclude_clicked": True,
                },
            )
            resp.raise_for_status()
            return resp.json().get("top_aids", [])
        except Exception as e:
            logger.error(f"Remote SASRec call failed: {e}")
            return []

    async def predict(self, session_aids: List[int], top_k: int = 20) -> List[int]:
        if not session_aids:
            return []
        return await self._predict_remote(session_aids, top_k)

    async def recommend_multi_objective(self, session_aids: List[int], top_k: int = 20) -> Dict[str, List[int]]:
        base_recs = await self.predict(session_aids, top_k)
        return {
            "clicks": base_recs[10 : top_k],
            "carts": base_recs[5 : 10],
            "orders": base_recs[0:5],
        }
