"""
Spark Batch Analysis — OTTO Recommender Pipeline.
Performs heavy-duty EDA and pre-computations using PySpark.
"""

import os
import sys
from pathlib import Path
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, count, when, window, from_json, explode, desc, row_number, avg, lit
from pyspark.sql.types import StructType, StructField, LongType, StringType, ArrayType, TimestampType
from pyspark.sql.window import Window

# --- Configuration ---
PG_URL = "jdbc:postgresql://localhost:5432/otto_recommender"
PG_PROPERTIES = {
    "user": "otto",
    "password": "otto123",
    "driver": "org.postgresql.Driver"
}

# Define Schema for JSONL (Session-based)
json_schema = StructType([
    StructField("session", LongType(), True),
    StructField("events", ArrayType(StructType([
        StructField("aid", LongType(), True),
        StructField("ts", LongType(), True),
        StructField("type", StringType(), True)
    ])), True)
])

def main(input_path: str):
    spark = SparkSession.builder \
        .appName("OTTO-Batch-Analysis") \
        .config("spark.jars.packages", "org.postgresql:postgresql:42.7.1") \
        .config("spark.driver.memory", "4g") \
        .getOrCreate()

    spark.sparkContext.setLogLevel("WARN")
    print(f"Reading data from: {input_path}")

    # 1. Load Data
    raw_df = spark.read.json(input_path, schema=json_schema)
    
    # Explode events to get flat structure
    events_df = raw_df.select(
        col("session").alias("session_id"),
        explode("events").alias("event")
    ).select(
        "session_id",
        col("event.aid").alias("aid"),
        col("event.type").alias("type"),
        (col("event.ts") / 1000).cast(TimestampType()).alias("timestamp")
    )
    
    events_df.cache()
    print(f"Total events to process: {events_df.count()}")

    # --- 2. Popular Items (for Cold Start) ---
    print("Computing Popular Items...")
    popular_df = events_df.groupBy("type", "aid").count()
    
    # Get top 100 per type using Window function
    window_spec = Window.partitionBy("type").orderBy(desc("count"))
    top_popular_df = popular_df.withColumn("rank", row_number().over(window_spec)) \
        .filter(col("rank") <= 100) \
        .select(
            lit("all_time").alias("time_scope"),
            col("type").alias("event_type"),
            "aid",
            "count",
            "rank"
        )

    # Save to popular_items (Overwrite all_time scope)
    top_popular_df.write.jdbc(url=PG_URL, table="popular_items", mode="append", properties=PG_PROPERTIES)

    # --- 3. Session Stats (Segmentation) ---
    print("Computing Session Stats...")
    session_stats = events_df.groupBy("session_id").agg(
        count("*").alias("length"),
        count(when(col("type") == "carts", True)).alias("carts"),
        count(when(col("type") == "orders", True)).alias("orders")
    )
    
    # Define session types
    session_types_df = session_stats.withColumn(
        "session_type",
        when(col("orders") > 0, "buyer")
        .when(col("carts") > 0, "cart_abandoner")
        .otherwise("browse_only")
    )
    
    final_session_dist = session_types_df.groupBy("session_type").agg(
        count("*").alias("count"),
        avg("length").alias("avg_length")
    )
    
    # Save to stats_sessions
    final_session_dist.write.jdbc(url=PG_URL, table="stats_sessions", mode="overwrite", properties=PG_PROPERTIES)

    # --- 4. Hourly Stats ---
    print("Computing Hourly Stats...")
    hourly_df = events_df.groupBy(window("timestamp", "1 hour")).agg(
        count("*").alias("total_events"),
        count(when(col("type") == "clicks", True)).alias("total_clicks"),
        count(when(col("type") == "carts", True)).alias("total_carts"),
        count(when(col("type") == "orders", True)).alias("total_orders")
    ).select(
        col("window.start").alias("window_start"),
        col("window.end").alias("window_end"),
        "total_events", "total_clicks", "total_carts", "total_orders"
    )
    
    hourly_df.write.jdbc(url=PG_URL, table="stats_hourly", mode="append", properties=PG_PROPERTIES)

    # --- 5. Funnel Analysis ---
    print("Computing Funnel Stats...")
    # total_sessions already known from raw_df but let's be precise
    total_sessions = raw_df.count()
    sessions_with_clicks = session_types_df.count() # all sessions in explode have at least one event
    sessions_with_carts = session_types_df.filter("carts > 0").count()
    sessions_with_orders = session_types_df.filter("orders > 0").count()
    
    funnel_df = spark.createDataFrame([(
        total_sessions,
        sessions_with_clicks,
        sessions_with_carts,
        sessions_with_orders,
        sessions_with_carts / sessions_with_clicks if sessions_with_clicks > 0 else 0.0,
        sessions_with_orders / sessions_with_carts if sessions_with_carts > 0 else 0.0,
        sessions_with_orders / sessions_with_clicks if sessions_with_clicks > 0 else 0.0
    )], ["total_sessions", "sessions_with_clicks", "sessions_with_carts", "sessions_with_orders", 
         "click_to_cart_rate", "cart_to_order_rate", "click_to_order_rate"])
    
    funnel_df.write.jdbc(url=PG_URL, table="funnel_stats", mode="append", properties=PG_PROPERTIES)

    print("✅ Batch Analysis completed successfully.")
    spark.stop()

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "datasets/otto/train.jsonl"
    main(path)
