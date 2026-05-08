"""
Spark Structured Streaming Job — OTTO Recommender Pipeline.
- Consumes from Kafka
- Aggregates stats by 1-minute window -> PostgreSQL (stats_hourly)
- Detects anomalies (Bot traffic) -> PostgreSQL (anomaly_logs)
"""

import os
import logging
from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col, window, count, when, expr, lit, struct, to_json, approx_count_distinct
from pyspark.sql.types import StructType, StructField, LongType, StringType, TimestampType

# --- Configuration ---
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
KAFKA_TOPIC = "user-events"
CHECKPOINT_LOCATION = "/tmp/spark-checkpoints/otto-streaming"

PG_URL = "jdbc:postgresql://localhost:5432/otto_recommender"
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

def main():
    # 1. Initialize Spark Session with auto-loading jars
    spark = SparkSession.builder \
        .appName("OTTO-Streaming-Processor") \
        .config("spark.sql.streaming.checkpointLocation", CHECKPOINT_LOCATION) \
        .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.postgresql:postgresql:42.7.1") \
        .getOrCreate()

    spark.sparkContext.setLogLevel("WARN")

    # Debug: Print Versions
    print("=" * 40)
    print(f"DEBUG: Spark Version: {spark.version}")
    try:
        scala_version = spark._jvm.scala.util.Properties.versionString()
        print(f"DEBUG: Scala Version: {scala_version}")
    except:
        print("DEBUG: Could not determine Scala version via JVM")
    print("=" * 40)

    # 2. Read from Kafka
    raw_df = spark.readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS) \
        .option("subscribe", KAFKA_TOPIC) \
        .option("startingOffsets", "latest") \
        .load()

    # 3. Parse JSON and Convert Timestamp
    events_df = raw_df.selectExpr("CAST(value AS STRING)") \
        .select(from_json(col("value"), schema).alias("data")) \
        .select("data.*") \
        .withColumn("timestamp", (col("ts") / 1000).cast(TimestampType())) \
        .withWatermark("timestamp", "2 minutes")

    # --- PIPELINE A: Global Stats Aggregation ---
    stats_df = events_df \
        .groupBy(window(col("timestamp"), "1 minute")) \
        .agg(
            count("*").alias("total_events"),
            count(when(col("type") == "clicks", True)).alias("total_clicks"),
            count(when(col("type") == "carts", True)).alias("total_carts"),
            count(when(col("type") == "orders", True)).alias("total_orders"),
            approx_count_distinct("session_id").alias("unique_sessions"),
            approx_count_distinct("aid").alias("unique_items")
        ) \
        .select(
            col("window.start").alias("window_start"),
            col("window.end").alias("window_end"),
            "total_events",
            "total_clicks",
            "total_carts",
            "total_orders",
            "unique_sessions",
            "unique_items"
        )

    # --- PIPELINE B: Anomaly Detection (Bot Traffic) ---
    # Threshold: > 50 events per minute for a single session
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

    # 4. Write to PostgreSQL using foreachBatch
    def write_all_to_postgres(batch_df, batch_id, table_name):
        batch_df.write \
            .jdbc(url=PG_URL, table=table_name, mode="append", properties=PG_PROPERTIES)

    # Start Stats Stream
    query_stats = stats_df.writeStream \
        .outputMode("update") \
        .foreachBatch(lambda df, epoch_id: write_all_to_postgres(df, epoch_id, "stats_hourly")) \
        .queryName("Global-Stats") \
        .start()

    # Start Anomaly Stream
    query_anomalies = anomalies_df.writeStream \
        .outputMode("update") \
        .foreachBatch(lambda df, epoch_id: write_all_to_postgres(df, epoch_id, "anomaly_logs")) \
        .queryName("Anomaly-Detection") \
        .start()

    # 5. Add Streaming Query Listener to log performance metrics
    from pyspark.sql.streaming import StreamingQueryListener
    import psycopg2

    class MetricsListener(StreamingQueryListener):
        def onQueryStarted(self, event):
            pass
        def onQueryProgress(self, event):
            progress = event.progress
            try:
                # Direct write to Postgres using psycopg2 (since it's a small insert)
                conn = psycopg2.connect(
                    host="localhost", port=5432, dbname="otto_recommender", 
                    user="otto", password="otto123"
                )
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO spark_metrics 
                            (query_name, input_rows_per_second, processed_rows_per_second, batch_duration_ms, num_input_rows)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (
                        progress.name or "unnamed",
                        progress.inputRowsPerSecond,
                        progress.processedRowsPerSecond,
                        progress.durationMs.get('triggerExecution', 0),
                        progress.numInputRows
                    ))
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"Error logging spark metrics: {e}")
        def onQueryTerminated(self, event):
            pass

    spark.streams.addListener(MetricsListener())

    print(f"🚀 Spark Streaming Job (Stats + Anomalies) started with Metrics Listener.")
    spark.streams.awaitAnyTermination()

if __name__ == "__main__":
    main()
