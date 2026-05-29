#python -m src.test.test_sasrec_recommender

from src.serving.sasrec_recommender import SASRecRecommender
import os
from dotenv import load_dotenv
import asyncio 

load_dotenv()
SASREC_REMOTE_URL = os.getenv("SASREC_REMOTE_URL")

if __name__ == "__main__":
    async def main():
        sasrec = SASRecRecommender(remote_url=SASREC_REMOTE_URL)
        session_aids = [1492293,910862,1491172,424964,1515526,440486,109488]
        print("Test predict (top_aids):")
        print(await sasrec.predict(session_aids, top_k=20))
        print("Test recommend_multi_objective:")
        print(await sasrec.recommend_multi_objective(session_aids, top_k=20))
        await sasrec.aclose()
    asyncio.run(main()) 

# {'clicks': [1084785, 1721019, 1781681, 152974, 485465, 165903, 1466188, 1360395, 905594, 730762], 
#  'carts': [594465, 1353221, 595525, 511946, 819232], 
#  'orders': [1220971, 1789921, 1812934, 943662, 26203]}

# {'clicks': [1135711, 1471212, 1182024, 1553344, 219758, 1211286, 663062, 1717294, 595525, 1812934], 
#  'carts': [1074263, 926198, 1005368, 594465, 391942], 
#  'orders': [517341, 450281, 89935, 1084785, 1220971]}
