"""
Seed Popular Items (Spark Batch Job) - OTTO Recommender System.
Pre-computes top items per event type and saves to PostgreSQL.
Provides data for the Cold Start recommendation strategy.
"""

import logging
import os
import sys
from pathlib import Path

from pyspark.sql import SparkSession, Window
from pyspark.sql.functions import col, count, explode, lit, row_number

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s"
)
logger = logging.getLogger(__name__)

# --- Configuration ---
root_dir = Path(__file__).resolve().parents[2]
DATA_PATH = str(root_dir / "datasets" / "otto" / "train_sessions.parquet")
TOP_K = 100

PG_HOST = os.getenv("POSTGRES_HOST", "localhost")
PG_PORT = os.getenv("POSTGRES_PORT", "5432")
PG_DB = os.getenv("POSTGRES_DB", "otto_recommender")
PG_USER = os.getenv("POSTGRES_USER", "otto")
PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "otto123")
PG_URL = f"jdbc:postgresql://{PG_HOST}:{PG_PORT}/{PG_DB}"
PG_PROPERTIES = {
    "user": PG_USER,
    "password": PG_PASSWORD,
    "driver": "org.postgresql.Driver",
}


def main():
    spark = (
        SparkSession.builder.appName("OTTO-Seed-Popular-Items")
        .config("spark.jars.packages", "org.postgresql:postgresql:42.7.1")
        .config("spark.driver.memory", "4g")
        .getOrCreate()
    )

    spark.sparkContext.setLogLevel("WARN")
    logger.info("Spark Session Initialized.")

    logger.info(f"Reading data from {DATA_PATH}...")
    if not Path(DATA_PATH).exists():
        logger.error(f"Data path {DATA_PATH} does not exist.")
        sys.exit(1)

    try:
        raw_df = spark.read.parquet(DATA_PATH)
    except Exception as e:
        logger.error(f"Cannot read data: {e}")
        sys.exit(1)

    # Flatten events (schema embedded in parquet)
    events_df = raw_df.select(explode("events").alias("event")).select(
        col("event.aid").alias("aid"), col("event.type").alias("event_type")
    )

    # 3. Aggregate counts per type and aid
    logger.info("Calculating popular items...")
    agg_df = events_df.groupBy("event_type", "aid").agg(count("*").alias("count"))

    # 4. Rank items within each event type using Window function
    window_spec = Window.partitionBy("event_type").orderBy(col("count").desc())

    ranked_df = (
        agg_df.withColumn("rank", row_number().over(window_spec))
        .filter(col("rank") <= TOP_K)
        .withColumn("time_scope", lit("all_time"))
    )

    # Select columns in the order expected by the DB table
    # Schema: (time_scope, event_type, aid, count, rank)
    final_df = ranked_df.select("time_scope", "event_type", "aid", "count", "rank")

    # 5. Write to PostgreSQL
    logger.info(f"Writing top {TOP_K} items to PostgreSQL...")
    try:
        # Use overwrite mode with truncate to preserve constraints (like UNIQUE)
        final_df.write.format("jdbc").option("url", PG_URL).option(
            "dbtable", "popular_items"
        ).option("truncate", "true").options(**PG_PROPERTIES).mode("overwrite").save()
        logger.info("Successfully seeded 'popular_items' table.")
    except Exception as e:
        logger.error(f"Failed to write to DB: {e}")

    spark.stop()


if __name__ == "__main__":
    main()
