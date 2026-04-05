import os
import pandas as pd

from pathlib import Path

from dotenv import load_dotenv
import polars as pl

import seaborn as sns
import matplotlib.pyplot as plt
import altair as alt
from datetime import datetime
import random


# # Convert JSONL to parquet
DATASET_DIR = Path(__file__).parent.parent.parent.parent / 'datasets' / 'otto-recommender-system'
TRAIN_JSON = DATASET_DIR / 'train.jsonl'
TEST_JSON = DATASET_DIR / 'test.jsonl'

TRAIN_PARQUET = DATASET_DIR / 'train.parquet'
TEST_PARQUET = DATASET_DIR / 'test.parquet'


def json_to_parquet(file_path, output_path):
	df = pl.scan_ndjson(file_path) \
    .sink_parquet(output_path, compression='zstd', compression_level=3)

json_to_parquet(
	str(TRAIN_JSON),
	str(TRAIN_PARQUET)
)

json_to_parquet(
	str(TEST_JSON), str(TEST_PARQUET)
)
