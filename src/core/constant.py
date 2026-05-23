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



# COLUMN NAME
SESSION_COLUMN_NAME = "session"
AID_COLUMN_NAME = "aid"
TS_COLUMN_NAME = "ts"
TYPE_COLUMN_NAME = "type"
EVENTS_COLUMN_NAME = "events"


#ACTION_TYPE
CART_TYPE = "carts"
CLICK_TYPE = "clicks"
ORDER_TYPE = "orders"


# Intermediate results saved
EVENT_PAIRS_PARQUET_FILE = DATASETS_DIR / "event_pairs.parquet"
COVISITATION_MATRIX_PARQUET_FILE = DATASETS_DIR / "covisitation.parquet"

# Intermediate pair file
PAIRS_24H_PARQUET_FILE = DATASETS_DIR / "pairs_24h.parquet"
PAIRS_14D_BUY2BUY_PARQUET_FILE = DATASETS_DIR / "pairs_14d_buy2buy.parquet"

# New covisitation matrix
CARTS_ORDERS_MATRIX_PARQUET_FILE = DATASETS_DIR / "carts_orders_matrix.parquet"
BUY2BUY_MATRIX_PARQUET_FILE = DATASETS_DIR / "buy2buy_matrix.parquet"
CLICKS_MATRIX_PARQUET_FILE = DATASETS_DIR / "clicks_matrix.parquet"

# OTHER CONSTANT
TAIL_SIZE = 30
ONE_DAY_IN_SECONDS = 60 * 60 * 24
FOURTEEN_DAYS_IN_SECONDS = 60 * 60 * 24 * 14
WEIGHT_INTERMEDIATE_COLUMN = "weight"

