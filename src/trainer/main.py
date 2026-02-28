from pyspark.sql.functions import explode, col

from src.core import _start_spark
from src.core.constant import DATASETS_FILEPATH
from src.trainer.eda.visualization import (
    events_count_by_type_pie_chart,
    events_count_by_type_bar_graph,
    hourly_events_trend_line_graph,
)


def main():
    spark, logger = _start_spark()
    logger.info("Spark session started successfully!")
    
    # Load dataset
    data_path = str(DATASETS_FILEPATH)
    logger.info(f"Loading data from: {data_path}")
    df = spark.read.parquet(data_path)
    
    # Extract events while keeping 'session' for session-level analysis
    # explode creates 'col' by default, then we select session and col.*
    events = df.select(col("session"), explode(col("events"))).select("session", "col.*")
    
    # Run EDA Visualizations
    logger.info("Starting EDA visualizations...")
    
    # 1. Distribution of event types
    events_count_by_type_pie_chart(events)
    events_count_by_type_bar_graph(events)
    
    # 2. Activity Trends
    hourly_events_trend_line_graph(events)
    
    logger.info("EDA visualizations completed.")
    spark.stop()


if __name__ == '__main__':
    main()