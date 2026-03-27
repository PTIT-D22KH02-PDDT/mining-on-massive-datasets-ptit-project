# # 1. Config

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

DATASET_DIR = Path(__file__).parent.parent.parent / 'datasets' / 'otto-parquet'
TRAIN_JSON = DATASET_DIR / 'train.jsonl'
TEST_JSON = DATASET_DIR / 'test.jsonl'


# # Convert JSONL to parquet

# OUTPUT_PATH = Path(__file__).parent.parent.parent / 'datasets' / 'otto-recommender-system')
# TRAIN_PARQUET = OUTPUT_PATH / 'train.parquet'
# TEST_PARQUET = OUTPUT_PATH / 'test.parquet'


# def json_to_parquet(file_path, output_path):
# 	df = pl.scan_ndjson(file_path) \
#     .sink_parquet(output_path, compression='zstd', compression_level=3)

# json_to_parquet(
# 	str(TRAIN_JSON),
# 	str(TRAIN_PARQUET)
# )

# json_to_parquet(
# 	str(TEST_JSON), str(TEST_PARQUET)
# )


# # 1. EDA

PARQUET_DIR = Path(__file__).parent.parent.parent / 'datasets' / 'otto-parquet'
TRAIN_PARQUET = PARQUET_DIR / 'train.parquet'
TEST_PARQUET = PARQUET_DIR / 'test.parquet'


train_df = pl.scan_parquet(TRAIN_PARQUET)
test_df = pl.scan_parquet(TEST_PARQUET)


# ## 1.1. Xem dữ liệu train và test

# schema
train_df.schema


# Xem một vài dữ liệu đầu tiên trong tập train và tập test
print('Tập train:')
print(train_df.head(3).collect())

print('-'*50)

print('Tập test:')
print(test_df.head(3).collect())


train_df.head(1).collect() \
    .explode("events") \
    .unnest("events")


test_df.head(1).collect().explode('events').unnest('events')


# ## 1.2. Thống kê đơn giản

def get_events_stats(df, name):
    n_events_per_session = df.collect().select(pl.col('events').list.len().alias('n_events'))['n_events']
    return {
        'Dataset': name,
        'mean': f'{n_events_per_session.mean():.2f}',
        'std': f'{n_events_per_session.std():.2f}',
        'min': n_events_per_session.min(),
        '50%': n_events_per_session.quantile(0.5),
        '75%': n_events_per_session.quantile(0.75),
        '90%': n_events_per_session.quantile(0.9),
        '95%': n_events_per_session.quantile(0.95),
        'max': n_events_per_session.max(),
    }


print('Thống kê về số events của từng phiên trong tập train')

print(get_events_stats(train_df, 'train'))

print('-'*50)
print('Thống kê về số events của từng phiên trong tập test')

print(get_events_stats(test_df, 'test'))


# Đếm số session, items, events, clicks, carts, orders, và Density
def dataset_stats(df, name):
    df = df.collect()
    n_session = df.height

    events = df.select(pl.col('events').list.explode().alias('event')).unnest('event')
    n_events = events.height
    n_items = events.select(pl.col('aid')).unique().height

    type_counts_df = events.group_by('type').count()
    type_dict = dict(zip(type_counts_df['type'], type_counts_df['count']))

    n_clicks = type_dict.get('clicks', 0)
    n_carts = type_dict.get('carts', 0)
    n_orders = type_dict.get('orders', 0)

    density = (n_events / (n_session * n_items) * 100) if (n_session * n_items) > 0 else 0

    return {
        'Dataset': name,
        '#sessions': n_session,
        '#items': n_items,
        '#events': n_events,
        '#clicks': n_clicks,
        '#carts': n_carts,
        '#orders': n_orders,
        'Density': density
    }


print('Thống kê dataset trong tập train:')

print(dataset_stats(train_df, 'train'))

print('-'*50)
print('Thống kê dataset trong tập test:')
print(dataset_stats(test_df, 'test'))


# ## 1.3. Số lượng các loại hành vi trong tập huấn luyện và tập kiểm tra

def count_event_types(df, name):
    return df.collect() \
            .explode('events') \
            .unnest('events') \
            .group_by('type') \
            .count() \
            .sort('count', descending=True)


train_events = count_event_types(train_df, 'train')
test_events = count_event_types(test_df, 'test')


print('Số lượng event type trong tập train:')
print(train_events)

print('-'*50)
print('Số lượng event type trong tập test:')
print(test_events)


def make_chart(df, title, color):
    return alt.Chart(df).mark_bar(color=color).encode(
        x=alt.X('type:N', title='Loại sự kiện'),
        y=alt.Y('count:Q', title='Số lượng'),
        tooltip=['type', 'count']
    ).properties(
        width=500,
        height=400,
        title=title
    )

chart_train = make_chart(train_events, 'Biểu đồ số lượng các loại hành vi trong tập train', '#66c2a5')
chart_test  = make_chart(test_events,  'Biểu đồ số lượng các loại hành vi trong tập test',  '#fc8d62')

(chart_train | chart_test).show()


# ## 1.4. Xét phân phối longtail của sản phẩm trong tập train

item_counts = train_df.collect() \
                .explode('events') \
                .unnest('events') \
                .group_by('aid') \
                .agg(pl.len().alias('count')) \
                .sort('count', descending=True) \
                .with_row_index('rank')

longtail_chart = alt.Chart(item_counts.head(5000)).mark_area(
    line={'strokeWidth': 2.5},
    opacity=0.4
).encode(
    x=alt.X('rank:Q', title='Xếp hạng sản phẩm (Item rank)'),
    y=alt.Y('count:Q', title='Số lượng tương tác'),
    tooltip=['aid', 'count', 'rank']
).properties(
    width=700, height=400,
    title=alt.TitleParams(
        text='Số lượng tương tác theo sản phẩm trong tập train (top 5000 item)',
        fontSize=16
    )
).configure_axis(
    labelFontSize=12,
    titleFontSize=13
)

longtail_chart.show()


# ## 1.5. Xét hành vi người dùng theo khung giờ trong ngày

hourly_counts = train_df.collect() \
                    .explode('events') \
                    .unnest('events') \
                    .with_columns(
                        pl.from_epoch('ts', time_unit='ms').dt.hour().alias('hour')
                    ) \
                    .group_by(['hour', 'type']) \
                    .agg(pl.len().alias('count')) \
                    .sort('hour')


chart = alt.Chart(hourly_counts).mark_line(strokeWidth=2.5, point=True).encode(
    x=alt.X('hour:O', title='Giờ trong ngày'),
    y=alt.Y('count:Q', title='Số lượng hành vi'),
    color=alt.Color('type:N', title='Loại hành vi'),
    tooltip=['hour', 'type', 'count']
).properties(
    width=700,
    height=400,
    title=alt.TitleParams(
        text='Hành vi người dùng theo khung giờ trong ngày (Train)',
        fontSize=16,
    )
).configure_axis(
    labelFontSize=12,
    titleFontSize=13
)

chart.show()