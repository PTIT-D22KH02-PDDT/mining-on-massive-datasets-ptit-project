from pathlib import Path

# Project Root (point to the directory containing src/)
ROOT_DIR = Path(__file__).resolve().parents[2]

APP_NAME = "mining_on_massive_datasets_project"

# Paths relative to Root
##########
#CONFIG  #
##########
CONFIG_PATH = ROOT_DIR / "config"
CONFIG_FILE_NAME = "config.yml"

##########
#DATASET #
##########
DATASETS_DIR = ROOT_DIR / "datasets"
DATASETS_FILEPATH = DATASETS_DIR / "data.parquet"

##########
# EDA    #
##########
EDA_OUTPUT_PATH = ROOT_DIR / "output" / "eda"
EVENTS_COUNT_BY_TYPE_BAR_GRAPH = "events_count_by_type_bar_graph.png"
EVENTS_COUNT_BY_TYPE_PIE_CHART = "events_count_by_type_pie_chart.png"
HOURLY_EVENTS_TREND_LINE_GRAPH = "hourly_events_trend.png"