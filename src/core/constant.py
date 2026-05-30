from pathlib import Path

# Project Root (point to the directory containing src/)
ROOT_DIR = Path(__file__).resolve().parents[2]

# Paths relative to Root
DATASETS_DIR = ROOT_DIR / "datasets"
DATASETS_FILEPATH = DATASETS_DIR / "train_sessions.parquet"

# COLUMN NAME
SESSION_COLUMN_NAME = "session"
AID_COLUMN_NAME = "aid"
TS_COLUMN_NAME = "ts"
TYPE_COLUMN_NAME = "type"

# ACTION_TYPE
CART_TYPE = "carts"
CLICK_TYPE = "clicks"
ORDER_TYPE = "orders"
