"""
Advanced Funnel Analysis (Batch Job) - OTTO Recommender System.
Calculates session-level funnels, session segmentation, and advanced item-level metrics.
"""

import logging
import os
import sys
from pathlib import Path

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    avg,
    col,
    count,
    current_timestamp,
    explode,
    lit,
    max,
    when,
)
from pyspark.sql.functions import sum as spark_sum

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s"
)
logger = logging.getLogger(__name__)

# --- Configuration ---
root_dir = Path(__file__).resolve().parents[2]
DATA_PATH = str(root_dir / "datasets" / "otto" / "train_sessions.parquet")

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
        SparkSession.builder.master(os.getenv("SPARK_MASTER_URL", "local[*]"))
        .appName("OTTO-Funnel-Analysis")
        .config("spark.jars.packages", "org.postgresql:postgresql:42.7.1")
        .config("spark.driver.memory", os.getenv("SPARK_DRIVER_MEMORY", "4g"))
        .config("spark.sql.session.timeZone", "GMT+7")
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
    events_df = raw_df.select(
        col("session").alias("session_id"), explode("events").alias("event")
    ).select(
        "session_id",
        col("event.aid").alias("aid"),
        col("event.ts").alias("ts"),
        col("event.type").alias("type"),
    )

    # 3. Aggregate at Session Level
    logger.info("Computing Session-Level Metrics...")
    session_agg = (
        events_df.groupBy("session_id")
        .agg(
            count("*").alias("session_length"),
            max(when(col("type") == "clicks", 1).otherwise(0)).alias("has_clicks"),
            max(when(col("type") == "carts", 1).otherwise(0)).alias("has_carts"),
            max(when(col("type") == "orders", 1).otherwise(0)).alias("has_orders"),
        )
        .cache()
    )

    # 4. Calculate FUNNEL STATS (for 'funnel_stats' table)
    logger.info("Calculating Funnel Stats...")
    total_sessions = session_agg.count()

    if total_sessions == 0:
        logger.warning("No sessions found. Skipping table updates.")
        spark.stop()
        return

    funnel_metrics = session_agg.agg(
        spark_sum("has_clicks").alias("sessions_with_clicks"),
        spark_sum("has_carts").alias("sessions_with_carts"),
        spark_sum("has_orders").alias("sessions_with_orders"),
    ).withColumn("total_sessions", lit(total_sessions))

    # Calculate rates safely
    funnel_stats_df = funnel_metrics.select(
        col("total_sessions"),
        col("sessions_with_clicks"),
        col("sessions_with_carts"),
        col("sessions_with_orders"),
        (
            when(
                col("sessions_with_clicks") > 0,
                col("sessions_with_carts") / col("sessions_with_clicks"),
            ).otherwise(0)
        ).alias("click_to_cart_rate"),
        (
            when(
                col("sessions_with_carts") > 0,
                col("sessions_with_orders") / col("sessions_with_carts"),
            ).otherwise(0)
        ).alias("cart_to_order_rate"),
        (
            when(
                col("sessions_with_clicks") > 0,
                col("sessions_with_orders") / col("sessions_with_clicks"),
            ).otherwise(0)
        ).alias("click_to_order_rate"),
    )

    # 5. Calculate SESSION SEGMENTATION (for 'stats_sessions' table)
    logger.info("Calculating Session Segmentation...")
    # Logic: buyer > cart_abandoner > browse_only
    segmented_sessions = session_agg.withColumn(
        "session_type",
        when(col("has_orders") == 1, "buyer")
        .when(col("has_carts") == 1, "cart_abandoner")
        .otherwise("browse_only"),
    )

    stats_sessions_df = (
        segmented_sessions.groupBy("session_type")
        .agg(count("*").alias("count"), avg("session_length").alias("avg_length"))
        .withColumn("pct_of_total", (col("count") / total_sessions) * 100)
    )

    # 6. Advanced Analytics (Optional/Extra)
    advanced_funnel_df = (
        session_agg.agg(
            lit("Batch Analysis (test.jsonl)").alias("model_used"),
            count("*").alias("total_sessions"),
            spark_sum("has_clicks").alias("sessions_with_clicks"),
            spark_sum("has_carts").alias("sessions_with_carts"),
            spark_sum("has_orders").alias("sessions_with_orders"),
        )
        .withColumn(
            "click_to_order_rate",
            when(
                col("sessions_with_clicks") > 0,
                col("sessions_with_orders").cast("double")
                / col("sessions_with_clicks").cast("double"),
            ).otherwise(0.0),
        )
        .withColumn("last_updated", current_timestamp())
    )

    # Ensure columns are in the exact order as the DB table
    advanced_funnel_df = advanced_funnel_df.select(
        "model_used",
        "total_sessions",
        "sessions_with_clicks",
        "sessions_with_carts",
        "sessions_with_orders",
        "click_to_order_rate",
        "last_updated",
    )

    # --- SAVE TO POSTGRESQL ---
    logger.info("Writing results to PostgreSQL...")

    # Add computed_at for API ordering
    funnel_stats_df = funnel_stats_df.withColumn("computed_at", current_timestamp())

    try:
        # Table 1: funnel_stats (append-only for historical trend tracking)
        funnel_stats_df.write.format("jdbc").option("url", PG_URL).option(
            "dbtable", "funnel_stats"
        ).options(**PG_PROPERTIES).mode("append").save()
        logger.info("Saved to 'funnel_stats'")

        # Table 2: stats_sessions (overwrite — only 3 rows: buyer/cart_abandoner/browse_only)
        stats_sessions_df.write.format("jdbc").option("url", PG_URL).option(
            "dbtable", "stats_sessions"
        ).option("truncate", "true").options(**PG_PROPERTIES).mode("overwrite").save()
        logger.info("Saved to 'stats_sessions'")

        # Table 3: advanced_funnel_stats (overwrite — batch baseline only)
        advanced_funnel_df.write.format("jdbc").option("url", PG_URL).option(
            "dbtable", "advanced_funnel_stats"
        ).option("truncate", "true").options(**PG_PROPERTIES).mode("overwrite").save()
        logger.info("Saved to 'advanced_funnel_stats'")

    except Exception as e:
        logger.error(f"Failed to write to DB: {e}")

    spark.stop()


if __name__ == "__main__":
    main()
