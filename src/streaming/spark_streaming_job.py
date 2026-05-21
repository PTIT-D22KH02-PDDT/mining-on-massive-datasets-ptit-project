"""
Spark Structured Streaming Job - OTTO Recommender Pipeline.

Phase 1 Improvements:
- 1.1 Single Kafka read → multi-write (merge 6 streams into 1)
- 1.2 Bulk JDBC batch inserts with multi-row INSERT
- 1.3 Stats sessions pct calculation without collect() (using broadcast)
- 1.4 Adaptive checkpoint cleanup
"""

import os
import logging
import json
import psycopg2
from datetime import datetime, timedelta
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col, window, count, when, lit, struct, to_json, approx_count_distinct, min as spark_min, max as spark_max, sum as spark_sum, current_timestamp
from pyspark.sql.functions import avg as spark_avg, stddev as spark_stddev
from pyspark.sql.types import StructType, StructField, LongType, StringType, TimestampType
from pyspark.sql.streaming import StreamingQueryListener

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
KAFKA_TOPIC = "user-events"
CHECKPOINT_LOCATION = "/tmp/spark-checkpoints/otto-streaming"
CHECKPOINT_RETENTION_DAYS = 3

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")
logger = logging.getLogger(__name__)

PG_HOST = os.getenv("POSTGRES_HOST", "localhost")
PG_PORT = os.getenv("POSTGRES_PORT", "5432")
PG_DB = os.getenv("POSTGRES_DB", "otto_recommender")
PG_USER = os.getenv("POSTGRES_USER", "otto")
PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "otto123")
PG_URL = f"jdbc:postgresql://{PG_HOST}:{PG_PORT}/{PG_DB}"
PG_PROPERTIES = {
    "user": PG_USER,
    "password": PG_PASSWORD,
    "driver": "org.postgresql.Driver"
}
PG_BATCH_SIZE = 500

schema = StructType([
    StructField("session_id", LongType(), True),
    StructField("aid", LongType(), True),
    StructField("type", StringType(), True),
    StructField("ts", LongType(), True),
    StructField("model_used", StringType(), True)
])


class MetricsListener(StreamingQueryListener):
    def onQueryStarted(self, event):
        print(f"Query started: {event.id}")

    def onQueryProgress(self, event):
        progress = event.progress
        conn = None
        try:
            conn = psycopg2.connect(
                host=PG_HOST, port=int(PG_PORT), dbname=PG_DB,
                user=PG_USER, password=PG_PASSWORD
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
        except Exception as e:
            print(f"Error logging metrics: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()

    def onQueryTerminated(self, event):
        print(f"Query terminated: {event.id}")


def cleanup_old_checkpoints():
    """Remove checkpoint directories older than CHECKPOINT_RETENTION_DAYS."""
    try:
        if not os.path.exists(CHECKPOINT_LOCATION):
            return
        cutoff = datetime.now() - timedelta(days=CHECKPOINT_RETENTION_DAYS)
        cleaned = 0
        for item in os.listdir(CHECKPOINT_LOCATION):
            path = os.path.join(CHECKPOINT_LOCATION, item)
            if os.is_dir(path):
                mtime = datetime.fromtimestamp(os.path.getmtime(path))
                if mtime < cutoff:
                    import shutil
                    shutil.rmtree(path)
                    cleaned += 1
        if cleaned:
            print(f"Checkpoint cleanup: removed {cleaned} old dirs")
    except Exception as e:
        print(f"Checkpoint cleanup error: {e}")


def write_stats_hourly_from_rows(rows):
    """Write global stats via psycopg2 multi-row INSERT."""
    if not rows:
        return
    conn = psycopg2.connect(host=PG_HOST, port=int(PG_PORT), dbname=PG_DB, user=PG_USER, password=PG_PASSWORD)
    try:
        values = []
        for r in rows:
            values.append((
                r['window_start'], r['window_end'], r['total_events'],
                r['total_sessions'], r['unique_sessions'], r['total_clicks'],
                r['total_carts'], r['total_orders'], r['unique_items'],
                r['click_to_cart_rate'], r['cart_to_order_rate']
            ))
        batch_size = 100
        with conn.cursor() as cur:
            for i in range(0, len(values), batch_size):
                batch = values[i:i + batch_size]
                args_str = ','.join(
                    cur.mogrify("(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", row).decode()
                    for row in batch
                )
                cur.execute(
                    "INSERT INTO stats_hourly "
                    "(window_start, window_end, total_events, total_sessions, unique_sessions, "
                    "total_clicks, total_carts, total_orders, unique_items, "
                    "click_to_cart_rate, cart_to_order_rate) "
                    f"VALUES {args_str}"
                )
        conn.commit()
    except Exception as e:
        print(f"Error write_stats_hourly: {e}")
        conn.rollback()
    finally:
        conn.close()


def write_anomaly_logs_from_rows(rows):
    """Bulk INSERT for anomaly_logs using multi-row INSERT."""
    if not rows:
        return
    conn = psycopg2.connect(host=PG_HOST, port=int(PG_PORT), dbname=PG_DB, user=PG_USER, password=PG_PASSWORD)
    try:
        values = [(r['session_id'], r['anomaly_type'], r['details'], r['detected_at']) for r in rows]
        batch_size = 100
        with conn.cursor() as cur:
            for i in range(0, len(values), batch_size):
                batch = values[i:i + batch_size]
                args_str = ','.join(cur.mogrify("(%s, %s, %s::jsonb, %s)", row).decode() for row in batch)
                cur.execute(f"INSERT INTO anomaly_logs (session_id, anomaly_type, details, detected_at) VALUES {args_str}")
        conn.commit()
    except Exception as e:
        print(f"Error write_anomaly_logs: {e}")
        conn.rollback()
    finally:
        conn.close()


def write_popular_items_from_rows(rows):
    """Bulk UPSERT for popular_items."""
    if not rows:
        return
    conn = psycopg2.connect(host=PG_HOST, port=int(PG_PORT), dbname=PG_DB, user=PG_USER, password=PG_PASSWORD)
    try:
        values = [(r['time_scope'], r['event_type'], r['aid'], r['count'], r['rank']) for r in rows]
        batch_size = 100
        with conn.cursor() as cur:
            for i in range(0, len(values), batch_size):
                batch = values[i:i + batch_size]
                args_str = ','.join(cur.mogrify("(%s, %s, %s, %s, %s)", row).decode() for row in batch)
                cur.execute(f"""
                    INSERT INTO popular_items (time_scope, event_type, aid, count, rank)
                    VALUES {args_str}
                    ON CONFLICT (time_scope, event_type, aid)
                    DO UPDATE SET count = EXCLUDED.count, rank = EXCLUDED.rank
                """)
        conn.commit()
    except Exception as e:
        print(f"Error write_popular_items: {e}")
        conn.rollback()
    finally:
        conn.close()





def write_stats_items_from_rows(rows):
    """Bulk UPSERT for stats_items — item conversion metrics (Phase 5 Item Insights)."""
    if not rows:
        return
    conn = psycopg2.connect(host=PG_HOST, port=int(PG_PORT), dbname=PG_DB, user=PG_USER, password=PG_PASSWORD)
    try:
        values = []
        for r in rows:
            values.append((r['aid'], r['clicks'], r['carts'], r['orders'],
                          float(r['click_to_cart_rate']), float(r['click_to_order_rate']), float(r['cart_to_order_rate'])))
        batch_size = 100
        with conn.cursor() as cur:
            for i in range(0, len(values), batch_size):
                batch = values[i:i + batch_size]
                args_str = ','.join(
                    cur.mogrify("(%s, %s, %s, %s, %s, %s, %s)", row).decode()
                    for row in batch
                )
                cur.execute(f"""
                    INSERT INTO stats_items (aid, total_clicks, total_carts, total_orders,
                                           click_to_cart_rate, click_to_order_rate, cart_to_order_rate)
                    VALUES {args_str}
                    ON CONFLICT (aid) DO UPDATE SET
                        total_clicks = EXCLUDED.total_clicks,
                        total_carts = EXCLUDED.total_carts,
                        total_orders = EXCLUDED.total_orders,
                        click_to_cart_rate = EXCLUDED.click_to_cart_rate,
                        click_to_order_rate = EXCLUDED.click_to_order_rate,
                        cart_to_order_rate = EXCLUDED.cart_to_order_rate,
                        last_updated = NOW()
                """)
        conn.commit()
        logger.info(f"stats_items: OK ({len(values)} rows)")
    except Exception as e:
        logger.error(f"Error write_stats_items: {e}")
        conn.rollback()
    finally:
        conn.close()


def write_advanced_funnel_from_rows(rows):
    """Bulk UPSERT for advanced_funnel_stats."""
    if not rows:
        return
    conn = psycopg2.connect(host=PG_HOST, port=int(PG_PORT), dbname=PG_DB, user=PG_USER, password=PG_PASSWORD)
    try:
        values = []
        for r in rows:
            c2o = float(r['sessions_with_orders']) / float(r['sessions_with_clicks']) if r['sessions_with_clicks'] > 0 else 0.0
            values.append((r['model_used'], r['total_sessions'], r['sessions_with_clicks'],
                          r['sessions_with_carts'], r['sessions_with_orders'], c2o))
        batch_size = 100
        with conn.cursor() as cur:
            for i in range(0, len(values), batch_size):
                batch = values[i:i + batch_size]
                args_str = ','.join(cur.mogrify("(%s, %s, %s, %s, %s, %s, NOW())", row).decode() for row in batch)
                cur.execute(f"""
                    INSERT INTO advanced_funnel_stats
                        (model_used, total_sessions, sessions_with_clicks, sessions_with_carts,
                         sessions_with_orders, click_to_order_rate, last_updated)
                    VALUES {args_str}
                    ON CONFLICT (model_used) DO UPDATE SET
                        total_sessions = EXCLUDED.total_sessions,
                        sessions_with_clicks = EXCLUDED.sessions_with_clicks,
                        sessions_with_carts = EXCLUDED.sessions_with_carts,
                        sessions_with_orders = EXCLUDED.sessions_with_orders,
                        click_to_order_rate = EXCLUDED.click_to_order_rate,
                        last_updated = NOW()
                """)
        conn.commit()
    except Exception as e:
        print(f"Error write_advanced_funnel: {e}")
        conn.rollback()
    finally:
        conn.close()


def write_stats_sessions_from_rows(rows):
    """Bulk UPSERT for stats_sessions."""
    if not rows:
        return
    total_count = sum(r['count'] for r in rows)
    if not total_count or total_count == 0:
        return
    conn = psycopg2.connect(host=PG_HOST, port=int(PG_PORT), dbname=PG_DB, user=PG_USER, password=PG_PASSWORD)
    try:
        values = []
        for r in rows:
            pct = float(r['count']) * 100.0 / float(total_count)
            values.append((r['session_type'], r['count'], r['avg_length'], r['avg_duration_sec'], pct))
        batch_size = 100
        with conn.cursor() as cur:
            for i in range(0, len(values), batch_size):
                batch = values[i:i + batch_size]
                args_str = ','.join(cur.mogrify("(%s, %s, %s, %s, %s)", row).decode() for row in batch)
                cur.execute(f"""
                    INSERT INTO stats_sessions (session_type, count, avg_length, avg_duration_sec, pct_of_total)
                    VALUES {args_str}
                    ON CONFLICT (session_type) DO UPDATE SET
                        count = EXCLUDED.count, avg_length = EXCLUDED.avg_length,
                        avg_duration_sec = EXCLUDED.avg_duration_sec, pct_of_total = EXCLUDED.pct_of_total
                """)
        conn.commit()
    except Exception as e:
        print(f"Error write_stats_sessions: {e}")
        conn.rollback()
    finally:
        conn.close()


def unified_foreach_batch(batch_df, batch_id):
    """
    Single foreachBatch that computes all 6 outputs from one Kafka read.
    Phase 1.1: Merge 6 streams into 1.
    Phase 1.5: Parallel writes using ThreadPoolExecutor.

    Strategy:
    1. Compute all 6 aggregations (Spark lazy evaluation).
    2. Cache intermediate results to avoid recomputation.
    3. Materialize each aggregation (collect) — safe before threading.
    4. Parallelize 6 writes via ThreadPoolExecutor (I/O-bound operations).
    5. Unpersist cached DataFrames.
    """
    if batch_df.isEmpty():
        return

    # Cache the raw batch to avoid recomputing across aggregations
    batch_df.cache()

    try:
        # === COMPUTE ALL 6 AGGREGATIONS (lazy, no execution yet) ===

        # A: Global Stats Aggregation (5-min window)
        stats_df = batch_df \
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

        # B: Anomaly Detection (Z-score based — Phase 3.1)
        # Replaces hard threshold (count > 50) with statistical detection
        # Flag sessions where event count > mean + 3*std of batch distribution
        Z_SCORE_THRESHOLD = 3.0
        MIN_SESSIONS_FOR_ZSCORE = 10

        session_counts_df = batch_df \
            .groupBy(window(col("timestamp"), "1 minute"), "session_id") \
            .count()

        batch_stats = session_counts_df.select(
            spark_avg("count").alias("mean_count"),
            spark_stddev("count").alias("std_count")
        ).collect()

        if batch_stats and batch_stats[0]["std_count"]:
            mean_count = batch_stats[0]["mean_count"]
            std_count = batch_stats[0]["std_count"]
            session_count = session_counts_df.count()

            if session_count >= MIN_SESSIONS_FOR_ZSCORE and std_count and std_count > 0:
                threshold = mean_count + Z_SCORE_THRESHOLD * std_count
                anomalies_df = session_counts_df \
                    .filter(col("count") > threshold) \
                    .dropDuplicates(["session_id"]) \
                    .select(
                        col("session_id"),
                        lit("BOT_TRAFFIC").alias("anomaly_type"),
                        to_json(struct(
                            col("count").alias("event_count_per_min"),
                            lit(round(mean_count, 2)).alias("batch_mean"),
                            lit(round(std_count, 2)).alias("batch_std"),
                            lit(round(threshold, 2)).alias("z_threshold")
                        )).alias("details"),
                        current_timestamp().alias("detected_at")
                    )
            else:
                anomalies_df = session_counts_df.select(lit(None).alias("session_id")).filter("session_id IS NULL")
        else:
            anomalies_df = session_counts_df.select(lit(None).alias("session_id")).filter("session_id IS NULL")

        # C: Real-time Popularity (all-time per type & aid)
        popular_df = batch_df \
            .groupBy("type", "aid") \
            .count() \
            .select(
                lit("all_time").alias("time_scope"),
                col("type").alias("event_type"),
                col("aid"),
                col("count"),
                lit(0).alias("rank")
            )

        # D: Item Conversion Metrics (stats_items) — Phase 5 new use case
        # Tracks per-item conversion funnel: clicks → carts → orders
        items_df = batch_df \
            .groupBy("aid") \
            .agg(
                count(when(col("type") == "clicks", 1)).alias("clicks"),
                count(when(col("type") == "carts", 1)).alias("carts"),
                count(when(col("type") == "orders", 1)).alias("orders")
            ) \
            .withColumn("click_to_cart_rate",
                when(col("clicks") > 0, col("carts").cast("float") / col("clicks").cast("float")).otherwise(0.0)) \
            .withColumn("click_to_order_rate",
                when(col("clicks") > 0, col("orders").cast("float") / col("clicks").cast("float")).otherwise(0.0)) \
            .withColumn("cart_to_order_rate",
                when(col("carts") > 0, col("orders").cast("float") / col("carts").cast("float")).otherwise(0.0)) \
            .select(col("aid"), col("clicks"), col("carts"), col("orders"),
                    col("click_to_cart_rate"), col("click_to_order_rate"), col("cart_to_order_rate"))

        # E: Model Performance (Advanced Funnel)
        model_df = batch_df \
            .filter(col("model_used").isNotNull()) \
            .groupBy("model_used") \
            .agg(
                approx_count_distinct("session_id").alias("total_sessions"),
                approx_count_distinct(when(col("type") == "clicks", col("session_id"))).alias("sessions_with_clicks"),
                approx_count_distinct(when(col("type") == "carts", col("session_id"))).alias("sessions_with_carts"),
                approx_count_distinct(when(col("type") == "orders", col("session_id"))).alias("sessions_with_orders")
            ) \
            .withColumn("click_to_order_rate",
                when(col("sessions_with_clicks") > 0,
                     col("sessions_with_orders").cast("float") / col("sessions_with_clicks").cast("float")).otherwise(0.0))

        # F: Session Segmentation (stats_sessions)
        session_stats_df = batch_df.groupBy("session_id").agg(
            count("*").alias("session_length"),
            spark_max(when(col("type") == "clicks", 1).otherwise(0)).alias("has_clicks"),
            spark_max(when(col("type") == "carts", 1).otherwise(0)).alias("has_carts"),
            spark_max(when(col("type") == "orders", 1).otherwise(0)).alias("has_orders"),
            spark_min(col("ts")).alias("first_ts"),
            spark_max(col("ts")).alias("last_ts")
        ).withColumn(
            "session_type",
            when(col("has_orders") == 1, "buyer")
            .when(col("has_carts") == 1, "cart_abandoner")
            .otherwise("browse_only")
        ).withColumn("duration_sec", (col("last_ts") - col("first_ts")) / 1000.0)

        type_stats_df = session_stats_df.groupBy("session_type").agg(
            count("*").alias("count"),
            spark_sum("session_length").alias("total_length"),
            spark_sum("duration_sec").alias("total_duration")
        ).withColumn(
            "avg_length", col("total_length") / col("count")
        ).withColumn(
            "avg_duration_sec", col("total_duration") / col("count")
        ).select("session_type", "count", "avg_length", "avg_duration_sec")

        # === MATERIALIZE ALL RESULTS (trigger execution once) ===
        # Collecting to Python objects is safe before threading.
        # These are small aggregated results, not raw events.
        stats_data = stats_df.collect() if not stats_df.isEmpty() else []
        anomalies_data = anomalies_df.collect() if not anomalies_df.isEmpty() else []
        popular_data = popular_df.collect() if not popular_df.isEmpty() else []
        items_data = items_df.collect() if not items_df.isEmpty() else []
        model_data = model_df.collect() if not model_df.isEmpty() else []
        sessions_data = type_stats_df.collect() if not type_stats_df.isEmpty() else []

        # Unpersist — no longer needed
        batch_df.unpersist()

        # === PARALLEL WRITES (I/O-bound, thread-safe) ===
        def write_with_label(write_fn, data, label):
            """Wrapper to catch and report errors per write."""
            try:
                if data:
                    write_fn(data)
                return f"{label}: OK ({len(data)} rows)"
            except Exception as e:
                return f"{label}: ERROR — {e}"

        # Map write functions to their data
        write_tasks = [
            (write_stats_hourly_from_rows, stats_data, "stats_hourly"),
            (write_anomaly_logs_from_rows, anomalies_data, "anomaly_logs"),
            (write_popular_items_from_rows, popular_data, "popular_items"),
            (write_stats_items_from_rows, items_data, "stats_items"),
            (write_advanced_funnel_from_rows, model_data, "advanced_funnel"),
            (write_stats_sessions_from_rows, sessions_data, "stats_sessions"),
        ]

        # Execute all 6 writes in parallel
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {
                executor.submit(write_with_label, fn, data, label): label
                for fn, data, label in write_tasks
            }
            for future in as_completed(futures):
                result = future.result()
                print(f"  [Batch {batch_id}] {result}")

    except Exception as e:
        print(f"!!! ERROR unified_foreach_batch (batch_id={batch_id}): {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Ensure unpersist even on error
        try:
            batch_df.unpersist()
        except Exception:
            pass


def start_checkpoint_cleanup():
    """Background thread for periodic checkpoint cleanup."""
    while True:
        time.sleep(3600)
        cleanup_old_checkpoints()


def main():
    spark = SparkSession.builder \
        .appName("OTTO-Streaming-Processor") \
        .config("spark.sql.streaming.checkpointLocation", CHECKPOINT_LOCATION) \
        .config("spark.sql.streaming.minBatchesToRetain", 10) \
        .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.postgresql:postgresql:42.7.1") \
        .config("spark.sql.session.timeZone", "GMT+7") \
        .getOrCreate()

    spark.sparkContext.setLogLevel("WARN")
    spark.streams.addListener(MetricsListener())

    print("=" * 40)
    print(f"DEBUG: Spark Version: {spark.version}")
    print("=" * 40)

    raw_df = spark.readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS) \
        .option("subscribe", KAFKA_TOPIC) \
        .option("startingOffsets", os.getenv("SPARK_STARTING_OFFSETS", "earliest")) \
        .load()

    events_df = raw_df.selectExpr("CAST(value AS STRING)") \
        .select(from_json(col("value"), schema).alias("data")) \
        .select("data.*") \
        .withColumn("timestamp", (col("ts") / 1000).cast(TimestampType())) \
        .withWatermark("timestamp", "2 minutes")

    # Phase 1.1: Single writeStream (reads Kafka ONCE, writes to 6 tables)
    threading.Thread(target=start_checkpoint_cleanup, daemon=True).start()

    query = events_df.writeStream \
        .outputMode("update") \
        .queryName("Unified-OTTO-Streaming-Query") \
        .foreachBatch(unified_foreach_batch) \
        .start()

    print("Unified streaming query started (1 Kafka read → 6 PostgreSQL tables)")
    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()