## python -m  src.test.test_remote_model

import requests
import os
from dotenv import load_dotenv
load_dotenv()

SASREC_REMOTE_URL = os.getenv("SASREC_REMOTE_URL")

# Health check
print(requests.get(f"{SASREC_REMOTE_URL}/health").json())
# {"status": "ok", "device": "cuda", "max_len": 200, "num_items": ...}

# Recommend
res = requests.post(f"{SASREC_REMOTE_URL}/recommend", json={
    "click_sequence": [1492293,910862,1491172,424964,1515526,440486,109488,1507622,1734061,854637,718983,215311,718983,711125,50049,105393,959544,1734061,1842593,1464360,207905,1628317],
    "k": 20,
    "exclude_clicked": True
})
data = res.json()
print(data["top_aids"])    
print(data["top_scores"]) 