import logging
import os
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

REMOTE_MODEL_URL = os.getenv("REMOTE_MODEL_URL", "")

class RemoteModelRecommender:
    def __init__(self, remote_url: str = REMOTE_MODEL_URL):
        self.remote_url = remote_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=10)
        logger.info(f"Model Recs initialized in REMOTE mode via {self.remote_url}")

    async def aclose(self):
        await self._client.aclose()

    async def predict_remote(self, top_k: int, session_aids: List[int], 
                            type_sequence: Optional[List[str]] = None, 
                            ts_sequence: Optional[List[int]] = None,
                            model: str = "lbmrerank",
                            exclude_clicked = True) -> Dict[str, List[int]]:
        try:
            payload = {
                "click_sequence": session_aids,
                "type_sequence": type_sequence,
                "ts_sequence": ts_sequence,
                "k": top_k,
                "exclude_clicked": exclude_clicked,
                "model": model,
            }

            resp = await self._client.post(
                f"{self.remote_url}/recommend",
                json=payload
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("recommend", {"clicks": [], "carts": [], "orders": []})

        except Exception as e:
            logger.error(f"Remote Model call failed: {e}")
            return {"clicks": [], "carts": [], "orders": []}

