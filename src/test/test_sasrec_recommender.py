#python -m src.test.test_sasrec_recommender

from src.serving.sasrec_recommender import RemoteModelRecommender
import os
from dotenv import load_dotenv
import asyncio 

load_dotenv()
REMOTE_MODEL_URL = os.getenv("REMOTE_MODEL_URL")

if __name__ == "__main__":
    async def main():
        remote_model = RemoteModelRecommender(remote_url=REMOTE_MODEL_URL)
        click_sequence = [1492293, 910862, 1491172, 424964]
        type_sequence =   ["clicks", "clicks", "carts", "orders"]# 2 click, 1 cart, 1 buy
        ts_sequence = [1, 2,3, 4]
        exclude_clicked = True
        model = "lbmrerank"
        k = 5
        print("Test predict (top_aids):")
        print(await remote_model.predict_remote(k, click_sequence, type_sequence, ts_sequence, model, exclude_clicked))
       
        await remote_model.aclose()
    asyncio.run(main()) 
