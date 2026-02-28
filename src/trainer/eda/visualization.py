import os

from matplotlib import pyplot as plt
from pyspark.sql import DataFrame
from pyspark.sql.functions import col, from_unixtime, hour

from src.core.constant import (
    EDA_OUTPUT_PATH,
    EVENTS_COUNT_BY_TYPE_BAR_GRAPH,
    EVENTS_COUNT_BY_TYPE_PIE_CHART,
    HOURLY_EVENTS_TREND_LINE_GRAPH
)


def events_count_by_type_pie_chart(df: DataFrame):
    """Plot distribution of event types: clicks, carts, orders."""
    print("Generating event type pie chart...")
    type_counts = df.groupBy("type").count().toPandas()

    plt.figure(figsize=(8, 8))
    plt.pie(
        type_counts['count'],
        labels=type_counts['type'],
        autopct='%1.1f%%',
        explode=[0.05] * len(type_counts)
    )
    plt.title("Distribution of Event Types")

    os.makedirs(EDA_OUTPUT_PATH, exist_ok=True)
    save_path = str(EDA_OUTPUT_PATH / EVENTS_COUNT_BY_TYPE_PIE_CHART)
    plt.savefig(save_path)
    print(f"Pie chart saved to: {save_path}")


def events_count_by_type_bar_graph(df: DataFrame):
    """Bar plot of event counts by type."""
    print("Generating event type bar graph...")
    type_counts = df.groupBy("type").count().toPandas()

    plt.figure(figsize=(10, 6))
    plt.bar(type_counts["type"].astype(str), type_counts["count"])
    plt.xlabel("Event Type")
    plt.ylabel("Count")
    plt.title("Event Counts by Type")
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()

    os.makedirs(EDA_OUTPUT_PATH, exist_ok=True)
    save_path = str(EDA_OUTPUT_PATH / EVENTS_COUNT_BY_TYPE_BAR_GRAPH)
    plt.savefig(save_path)
    print(f"Bar graph saved to: {save_path}")


def hourly_events_trend_line_graph(df: DataFrame):
    """Plot hourly trend of events using timestamps (ms)."""
    print("Generating hourly event activity trend...")
    hourly_df = df.withColumn("hour", hour(from_unixtime(col("ts") / 1000))) \
                  .groupBy("hour").count() \
                  .orderBy("hour")
    pdf = hourly_df.toPandas()

    plt.figure(figsize=(12, 6))
    plt.plot(pdf["hour"], pdf["count"], marker='o', linestyle='-')
    plt.xlabel("Hour of Day")
    plt.ylabel("Event Count")
    plt.title("Hourly Event Activity Trend")
    plt.xticks(range(0, 24))
    plt.grid(True, alpha=0.3)
    plt.tight_layout()

    os.makedirs(EDA_OUTPUT_PATH, exist_ok=True)
    save_path = str(EDA_OUTPUT_PATH / HOURLY_EVENTS_TREND_LINE_GRAPH)
    plt.savefig(save_path)
    print(f"Hourly trend saved to: {save_path}")
