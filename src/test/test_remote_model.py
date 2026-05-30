## python -m  src.test.test_remote_model

import requests
import os
from dotenv import load_dotenv

load_dotenv()
# SASREC_REMOTE_URL
REMOTE_MODEL_URL = os.getenv("REMOTE_MODEL_URL")

# Health check
print(requests.get(f"{REMOTE_MODEL_URL}/health").json())
# {"status": "ok", "device": "cuda", "max_len": 200, "num_items": ...}

# Recommend
r = requests.post(f"{REMOTE_MODEL_URL}/recommend", json={
    "click_sequence": [1492293, 910862, 1491172,  424964],
    "type_sequence":  ["clicks", "clicks", "carts", "orders"],
    "ts_sequence": [1, 2, 3, 4],
    "model": "lbmrerank",
    "k": 20
})
print(r.json()["recommend"])
print(r.json()["model_used"])