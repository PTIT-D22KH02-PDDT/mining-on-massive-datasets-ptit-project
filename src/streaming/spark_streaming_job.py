"""
Spark Structured Streaming Job - OTTO Recommender Pipeline.
- Consumes from Kafka
- Aggregates stats by 1-minute window: PostgreSQL (stats_hourly)
- Real-time Funnel Analysis
- Detects anomalies (Bot traffic)
- Streaming Metrics Listener: PostgreSQL (spark_metrics)
"""

import os
import logging
import json
import psycopg2
from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col, window, count, when, expr, lit, struct, to_json, approx_count_distinct
from pyspark.sql.types import StructType, StructField, LongType, StringType, TimestampType
from pyspark.sql.streaming import StreamingQueryListener

# --- Configuration ---
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
KAFKA_TOPIC = "user-events"
CHECKPOINT_LOCATION = "/tmp/spark-checkpoints/otto-streaming"

PG_HOST = os.getenv("POSTGRES_HOST", "localhost")
PG_URL = f"jdbc:postgresql://{PG_HOST}:5432/otto_recommender"
PG_PROPERTIES = {
    "user": "otto",
    "password": "otto123",
    "driver": "org.postgresql.Driver"
}

# Define Schema for OTTO events
schema = StructType([
    StructField("session_id", LongType(), True),
    StructField("aid", LongType(), True),
    StructField("type", StringType(), True),
    StructField("ts", LongType(), True)
])

# --- Metrics Listener ---
class MetricsListener(StreamingQueryListener):
    def onQueryStarted(self, event):
        print(f"Query started: {event.id}")

    def onQueryProgress(self, event):
        """Called whenever a batch completes."""
        progress = event.progress
        try:
            # Extract metrics from the progress object
            conn = psycopg2.connect(
                host=os.getenv("POSTGRES_HOST", "localhost"), port=5432, dbname="otto_recommender", 
                user="otto", password="otto123"
            )
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO spark_metrics (
                        query_id, query_name, batch_id, 
                        input_rows_per_second, process_rows_per_second, batch_duration_ms
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(progress.id),
                        progress.name or "Unnamed Query",
                        progress.batchId,
                        progress.inputRowsPerSecond,
                        progress.processedRowsPerSecond,
                        progress.durationMs.get("triggerExecution", 0)
                    )
                )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error logging metrics: {e}")

    def onQueryTerminated(self, event):
        print(f"Query terminated: {event.id}")

def main():
    # 1. Initialize Spark Session
    spark = SparkSession.builder \
        .appName("OTTO-Streaming-Processor") \
        .config("spark.sql.streaming.checkpointLocation", CHECKPOINT_LOCATION) \
        .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.postgresql:postgresql:42.7.1") \
        .config("spark.sql.session.timeZone", "GMT+7") \
        .getOrCreate()

    spark.sparkContext.setLogLevel("WARN")

    # 2. Add Metrics Listener
    spark.streams.addListener(MetricsListener())

    # Debug: Print Versions
    print("=" * 40)
    print(f"DEBUG: Spark Version: {spark.version}")
    print("=" * 40)

    # Note: DB schema and constraints are now managed via postgres-init/01_create_tables.sql

    # 3. Read from Kafka
    raw_df = spark.readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS) \
        .option("subscribe", KAFKA_TOPIC) \
        .option("startingOffsets", "latest") \
        .load()

    # 4. Parse JSON and Convert Timestamp
    events_df = raw_df.selectExpr("CAST(value AS STRING)") \
        .select(from_json(col("value"), schema).alias("data")) \
        .select("data.*") \
        .withColumn("timestamp", (col("ts") / 1000).cast(TimestampType())) \
        .withWatermark("timestamp", "2 minutes")

    # --- PIPELINE A: Global Stats Aggregation (Real-time Funnel) ---
    stats_df = events_df \
        .groupBy(window(col("timestamp"), "5 minutes")) \
        .agg(
            count("*").alias("total_events"),
            approx_count_distinct("session_id").alias("total_sessions"),
            count(when(col("type") == "clicks", 1)).alias("total_clicks"),
            count(when(col("type") == "carts", 1)).alias("total_carts"),
            count(when(col("type") == "orders", 1)).alias("total_orders"),
            approx_count_distinct("aid").alias("unique_items")
        ) \
        .select(
            col("window.start").alias("window_start"),
            col("window.end").alias("window_end"),
            col("total_events"),
            col("total_sessions"),
            col("total_sessions").alias("unique_sessions"),
            col("total_clicks"),
            col("total_carts"),
            col("total_orders"),
            col("unique_items")
        ) \
        .withColumn("click_to_cart_rate", 
            when(col("total_clicks") > 0, col("total_carts").cast("double") / col("total_clicks").cast("double")).otherwise(0.0)) \
        .withColumn("cart_to_order_rate", 
            when(col("total_carts") > 0, col("total_orders").cast("double") / col("total_carts").cast("double")).otherwise(0.0))

    # --- PIPELINE B: Anomaly Detection (Bot Traffic) ---
    anomalies_df = events_df \
        .groupBy(window(col("timestamp"), "1 minute"), "session_id") \
        .count() \
        .filter("count > 50") \
        .select(
            col("session_id"),
            lit("BOT_TRAFFIC").alias("anomaly_type"),
            to_json(struct(col("count").alias("event_count_per_min"))).alias("details"),
            col("window.start").alias("detected_at")
        )

    # --- PIPELINE C: Real-time Popularity (Per Action Type) ---
    # We aggregate by type and aid to keep track of popularity for clicks, carts, and orders separately.
    popular_df = events_df \
        .groupBy("type", "aid") \
        .count() \
        .select(
            lit("all_time").alias("time_scope"),
            col("type").alias("event_type"),
            col("aid"),
            col("count"),
            lit(0).alias("rank")
        )

    # --- PIPELINE D: Real-time Item Performance (stats_items) ---
    items_stats_df = events_df \
        .groupBy("aid") \
        .agg(
            count(when(col("type") == "clicks", 1)).alias("clicks"),
            count(when(col("type") == "carts", 1)).alias("carts"),
            count(when(col("type") == "orders", 1)).alias("orders")
        )

    # --- PIPELINE E: Model Performance (Advanced Funnel) ---
    # Lưu ý: Pipeline này cần Join với Postgres nên logic Join sẽ nằm trong hàm xử lý Batch
    def process_model_performance(batch_df, batch_id):
        # 1. Đọc mapping session -> model mới nhất từ Postgres
        predictions_log_df = spark.read.jdbc(url=PG_URL, table="predictions_log", properties=PG_PROPERTIES) \
            .select("session_id", "model_used").dropDuplicates(["session_id"])
        
        # 2. Join luồng sự kiện với mapping model
        enriched_df = batch_df.join(predictions_log_df, "session_id")
        
        # 3. Tính toán phễu theo từng Model
        model_funnel_df = enriched_df.groupBy("model_used").agg(
            approx_count_distinct("session_id").alias("total_sessions"),
            approx_count_distinct(when(col("type") == "clicks", col("session_id"))).alias("sessions_with_clicks"),
            approx_count_distinct(when(col("type") == "carts", col("session_id"))).alias("sessions_with_carts"),
            approx_count_distinct(when(col("type") == "orders", col("session_id"))).alias("sessions_with_orders")
        ).withColumn("click_to_order_rate", 
            when(col("sessions_with_clicks") > 0, col("sessions_with_orders").cast("float") / col("sessions_with_clicks").cast("float")).otherwise(0.0))
        
        # 4. Ghi vào Postgres (UPSERT)
        write_all_to_postgres(model_funnel_df, batch_id, "advanced_funnel_stats")

    # 5. Write to PostgreSQL using foreachBatch
    def write_all_to_postgres(batch_df, batch_id, table_name):
        try:
            if table_name == "stats_hourly":
                # Đảm bảo chỉ chọn đúng các cột có trong DB để tránh lỗi thừa cột
                target_columns = [
                    "window_start", "window_end", "total_events", "total_sessions", 
                    "unique_sessions", "total_clicks", "total_carts", "total_orders", 
                    "unique_items", "click_to_cart_rate", "cart_to_order_rate"
                ]
                batch_df.select(*target_columns).write \
                    .jdbc(url=PG_URL, table=table_name, mode="append", properties=PG_PROPERTIES)
            
            elif table_name == "popular_items":
                # Real-time UPSERT logic using psycopg2 for efficiency in micro-batches
                def upsert_popularity(rows):
                    import psycopg2
                    import os
                    conn = psycopg2.connect(
                        host=os.getenv("POSTGRES_HOST", "localhost"), port=5432, dbname="otto_recommender", 
                        user="otto", password="otto123"
                    )
                    with conn.cursor() as cur:
                        for row in rows:
                            cur.execute(
                                """
                                INSERT INTO popular_items (time_scope, event_type, aid, count, rank)
                                VALUES (%s, %s, %s, %s, %s)
                                ON CONFLICT (time_scope, event_type, aid)
                                DO UPDATE SET 
                                    count = popular_items.count + EXCLUDED.count
                                """,
                                (row['time_scope'], row['event_type'], row['aid'], row['count'], row['rank'])
                            )
                    conn.commit()
                    conn.close()

                batch_df.foreachPartition(upsert_popularity)

            elif table_name == "stats_items":
                # UPSERT logic for per-item performance metrics
                def upsert_items(rows):
                    import psycopg2
                    conn = psycopg2.connect(
                        host=os.getenv("POSTGRES_HOST", "localhost"), port=5432, dbname="otto_recommender", 
                        user="otto", password="otto123"
                    )
                    with conn.cursor() as cur:
                        for row in rows:
                            cur.execute(
                                """
                                INSERT INTO stats_items (aid, total_clicks, total_carts, total_orders, last_updated)
                                VALUES (%s, %s, %s, %s, NOW())
                                ON CONFLICT (aid) DO UPDATE SET
                                    total_clicks = stats_items.total_clicks + EXCLUDED.total_clicks,
                                    total_carts = stats_items.total_carts + EXCLUDED.total_carts,
                                    total_orders = stats_items.total_orders + EXCLUDED.total_orders,
                                    last_updated = NOW(),
                                    click_to_cart_rate = CASE 
                                        WHEN (stats_items.total_clicks + EXCLUDED.total_clicks) > 0 
                                        THEN CAST((stats_items.total_carts + EXCLUDED.total_carts) AS FLOAT) / (stats_items.total_clicks + EXCLUDED.total_clicks)
                                        ELSE 0 END,
                                    cart_to_order_rate = CASE 
                                        WHEN (stats_items.total_carts + EXCLUDED.total_carts) > 0 
                                        THEN CAST((stats_items.total_orders + EXCLUDED.total_orders) AS FLOAT) / (stats_items.total_carts + EXCLUDED.total_carts)
                                        ELSE 0 END,
                                    click_to_order_rate = CASE 
                                        WHEN (stats_items.total_clicks + EXCLUDED.total_clicks) > 0 
                                        THEN CAST((stats_items.total_orders + EXCLUDED.total_orders) AS FLOAT) / (stats_items.total_clicks + EXCLUDED.total_clicks)
                                        ELSE 0 END
                                """,
                                (row['aid'], row['clicks'], row['carts'], row['orders'])
                            )
                    conn.commit()
                    conn.close()

                batch_df.foreachPartition(upsert_items)

            elif table_name == "advanced_funnel_stats":
                # Logic ghi UPSERT đơn giản cho bảng advanced_funnel_stats
                def upsert_advanced_funnel(rows):
                    import psycopg2
                    conn = psycopg2.connect(
                        host=os.getenv("POSTGRES_HOST", "localhost"), port=5432, dbname="otto_recommender", 
                        user="otto", password="otto123"
                    )
                    with conn.cursor() as cur:
                        for row in rows:
                            cur.execute(
                                """
                                INSERT INTO advanced_funnel_stats 
                                    (model_used, total_sessions, sessions_with_clicks, sessions_with_carts, sessions_with_orders, click_to_order_rate, last_updated)
                                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                                ON CONFLICT (model_used) DO UPDATE SET
                                    total_sessions = advanced_funnel_stats.total_sessions + EXCLUDED.total_sessions,
                                    sessions_with_clicks = advanced_funnel_stats.sessions_with_clicks + EXCLUDED.sessions_with_clicks,
                                    sessions_with_carts = advanced_funnel_stats.sessions_with_carts + EXCLUDED.sessions_with_carts,
                                    sessions_with_orders = advanced_funnel_stats.sessions_with_orders + EXCLUDED.sessions_with_orders,
                                    click_to_order_rate = CASE 
                                        WHEN (advanced_funnel_stats.sessions_with_clicks + EXCLUDED.sessions_with_clicks) > 0 
                                        THEN CAST((advanced_funnel_stats.sessions_with_orders + EXCLUDED.sessions_with_orders) AS FLOAT) / (advanced_funnel_stats.sessions_with_clicks + EXCLUDED.sessions_with_clicks)
                                        ELSE 0 END,
                                    last_updated = NOW()
                                """,
                                (row['model_used'], row['total_sessions'], row['sessions_with_clicks'], row['sessions_with_carts'], row['sessions_with_orders'], 0.0)
                            )
                    conn.commit()
                    conn.close()

                batch_df.foreachPartition(upsert_advanced_funnel)
            
            else:
                # Các bảng khác như anomaly_logs
                batch_df.write \
                    .jdbc(url=PG_URL, table=table_name, mode="append", properties=PG_PROPERTIES)
        
        except Exception as e:
            print(f"!!! ERROR writing to {table_name}: {e}")
            # Có thể in thêm schema của batch_df để debug
            print(f"Current Batch Schema for {table_name}:")
            batch_df.printSchema()

    # Start Streams
    query_stats = stats_df.writeStream \
        .outputMode("update") \
        .queryName("Global-Stats-Query") \
        .foreachBatch(lambda df, epoch_id: write_all_to_postgres(df, epoch_id, "stats_hourly")) \
        .start()

    query_anomalies = anomalies_df.writeStream \
        .outputMode("update") \
        .queryName("Anomaly-Detection-Query") \
        .foreachBatch(lambda df, epoch_id: write_all_to_postgres(df, epoch_id, "anomaly_logs")) \
        .start()

    query_popular = popular_df.writeStream \
        .outputMode("update") \
        .queryName("Popularity-Query") \
        .foreachBatch(lambda df, epoch_id: write_all_to_postgres(df, epoch_id, "popular_items")) \
        .start()

    query_items = items_stats_df.writeStream \
        .outputMode("update") \
        .queryName("Items-Stats-Query") \
        .foreachBatch(lambda df, epoch_id: write_all_to_postgres(df, epoch_id, "stats_items")) \
        .start()

    # Pipeline: Dùng chính events_df để phân tích hiệu năng model (Advanced Funnel)
    query_model_performance = events_df.writeStream \
        .outputMode("update") \
        .queryName("Model-Performance-Query") \
        .foreachBatch(process_model_performance) \
        .start()

    print(f"Spark Streaming Job with Metrics Listener started.")
    spark.streams.awaitAnyTermination()

if __name__ == "__main__":
    main()
