# # 2. Create validation set

import polars as pl
from pathlib import Path
import psutil
import random
from copy import deepcopy
from tqdm.auto import tqdm


OUTPUT_DIR = Path(__file__).parent.parent.parent / 'datasets' / 'otto-train-val'
TRAIN_PARQUET = Path(__file__).parent.parent.parent / 'datasets' / 'otto-parquet' / 'train.parquet'
TRAIN_SESSIONS_PARQUET = OUTPUT_DIR / 'train_sessions.parquet'
VALID_PARQUET = OUTPUT_DIR / 'valid_inputs.parquet'
VALID_LABELS_PARQUET = OUTPUT_DIR / 'valid_labels.parquet'

def _ground_truth(events: list[dict]):
    prev_labels = {"clicks": None, "carts": set(), "orders": set()}
    for event in reversed(events):
        event["labels"] = {}
        for label in ['clicks', 'carts', 'orders']:
            if prev_labels[label]:
                if label != 'clicks':
                    event["labels"][label] = prev_labels[label].copy()
                else:
                    event["labels"][label] = prev_labels[label]
        if event["type"] == "clicks":
            prev_labels['clicks'] = event["aid"]
        elif event["type"] == "carts":
            prev_labels['carts'].add(event["aid"])
        elif event["type"] == "orders":
            prev_labels['orders'].add(event["aid"])
    return events[:-1]


def check_ram_available(min_gb=2):
    available = psutil.virtual_memory().available / (1024**3)
    total = psutil.virtual_memory().total / (1024**3)
    print(f"\nRAM CHECK:")
    print(f"  Total:     {total:.1f} GB")
    print(f"  Available: {available:.1f} GB")
    if available < min_gb:
        print(f"  WARNING: chỉ còn {available:.1f}GB (cần >= {min_gb}GB)")
        return False
    print(f"  OK")
    return True


def simple_split_parquet(train_parquet_path, output_dir, test_days=7, seed=42):
    random.seed(seed)
    check_ram_available(min_gb=2)

    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)

    print(f"\n{'='*60}")
    print("OTTO TRAIN/VALID SPLIT")
    print(f"{'='*60}")

    # Bước 1: Tính split_ts
    print("\n[1/6] Tính split timestamp...")
    events_df = pl.scan_parquet(train_parquet_path).explode('events').unnest('events')

    max_ts = events_df.select(pl.col('ts').max()).collect().item()
    split_ts = max_ts - test_days * 24 * 60 * 60 * 1000
    print(f"      max_ts   = {max_ts}")
    print(f"      split_ts = {split_ts}")
    print(f"      test period = {test_days} days")

    # Bước 2: Chia session train/test
    print("\n[2/6] Phân loại sessions...")
    session_first_ts = (
        events_df
        .group_by('session')
        .agg(pl.col('ts').min().alias('first_ts'))
    )

    train_session_ids_df = session_first_ts.filter(pl.col('first_ts') <= split_ts).select('session')
    test_session_ids_df  = session_first_ts.filter(pl.col('first_ts') >  split_ts).select('session')

    n_train_sessions = train_session_ids_df.collect().height
    n_test_sessions  = test_session_ids_df.collect().height
    print(f"      Train sessions: {n_train_sessions:,}")
    print(f"      Test sessions:  {n_test_sessions:,}")

    # Bước 3: Tạo train_sessions
    print("\n[3/6] Tạo train sessions (trim events sau split_ts)...")
    with tqdm(total=1, desc="      Building train sessions") as pbar:
        train_sessions = (
            events_df
            .join(train_session_ids_df, on='session', how='semi')
            .filter(pl.col('ts') < split_ts)
            .group_by('session')
            .agg(
                pl.struct(['aid', 'ts', 'type'])
                .sort_by('ts')
                .alias('events')
            )
            .filter(pl.col('events').list.len() >= 2)
            .collect()
        )
        pbar.update(1)
    print(f"      Train sessions sau filter: {train_sessions.height:,}")

    # Bước 4: Lọc unknown items trong test
    print("\n[4/6] Filter unknown items trong test sessions...")

    with tqdm(total=1, desc="      Collecting train aids") as pbar:
        train_items_df = (
            events_df
            .join(train_session_ids_df, on='session', how='semi')
            .filter(pl.col('ts') < split_ts)
            .select('aid')
            .unique()
            .collect()
        )
        train_aids_set = set(train_items_df['aid'].to_list())
        pbar.update(1)
    print(f"      Train unique aids: {len(train_aids_set):,}")

    with tqdm(total=1, desc="      Collecting test events") as pbar:
        test_events_raw = (
            events_df
            .join(test_session_ids_df, on='session', how='semi')
            .collect()
        )
        pbar.update(1)

    # Eager join sau collect
    with tqdm(total=1, desc="      Filtering & grouping test sessions") as pbar:
        test_sessions_filtered = (
            test_events_raw
            .join(train_items_df, on='aid', how='semi')
            .group_by('session')
            .agg(
                pl.struct(['aid', 'ts', 'type'])
                .sort_by('ts')
                .alias('events')
            )
            .filter(pl.col('events').list.len() >= 2)
        )
        pbar.update(1)

    print(f"      Test sessions sau filter: {test_sessions_filtered.height:,}")

    # Bước 5: Tạo valid input/label pairs
    print("\n[5/6] Tạo valid input/label pairs...")
    valid_inputs_list = []
    valid_labels_list = []
    skipped = 0

    for row in tqdm(test_sessions_filtered.iter_rows(named=True),
                    total=test_sessions_filtered.height,
                    desc="      Processing sessions"):
        session_id = row['session']
        events = [dict(e) for e in row['events']]

        if len(events) < 2:
            skipped += 1
            continue

        test_events = _ground_truth(deepcopy(events))
        if not test_events:
            skipped += 1
            continue

        split_idx = random.randint(1, len(test_events))
        test_events_trimmed = test_events[:split_idx]
        raw_labels = test_events_trimmed[-1]['labels']

        clean_clicks = raw_labels.get('clicks')
        if clean_clicks is not None and clean_clicks not in train_aids_set:
            clean_clicks = None

        clean_carts  = [a for a in raw_labels.get('carts',  set()) if a in train_aids_set]
        clean_orders = [a for a in raw_labels.get('orders', set()) if a in train_aids_set]

        if not any([clean_clicks, clean_carts, clean_orders]):
            skipped += 1
            continue

        history = [{k: v for k, v in e.items() if k != 'labels'}
                   for e in test_events_trimmed]

        valid_inputs_list.append({'session': session_id, 'events': history})
        valid_labels_list.append({
            'session': session_id,
            'labels': {
                'clicks': clean_clicks,
                'carts':  clean_carts,
                'orders': clean_orders,
            }
        })

    print(f"      Valid pairs tạo được: {len(valid_inputs_list):,}")
    print(f"      Skipped: {skipped:,}")

    # Bước 6: Ghi parquet
    print("\n[6/6] Ghi parquet...")

    files = {
        'train_sessions.parquet': train_sessions,
        'valid_inputs.parquet':   pl.DataFrame(valid_inputs_list),
        'valid_labels.parquet':   pl.DataFrame(valid_labels_list),
    }

    for fname, df in tqdm(files.items(), desc="      Writing files"):
        df.write_parquet(
            str(output_dir / fname),
            compression='zstd',
            compression_level=3
        )

    print(f"\n{'='*60}")
    print("DONE!")
    print(f"{'='*60}")
    print(f"\n  Train sessions : {train_sessions.height:,}")
    print(f"  Valid sessions : {len(valid_inputs_list):,}")
    print(f"\n  Files saved to: {output_dir}")
    for fname in files:
        path = output_dir / fname
        size_mb = path.stat().st_size / (1024**2)
        print(f"    {fname:<30} {size_mb:.1f} MB")


simple_split_parquet(
    train_parquet_path=TRAIN_PARQUET,
    output_dir=OUTPUT_DIR,
    test_days=7,
    seed=42
)

OUTPUT_DIR = Path(__file__).parent.parent.parent / 'datasets' / 'otto-train-val'
TRAIN_SESSIONS_PARQUET = OUTPUT_DIR / 'train_sessions.parquet'
VALID_PARQUET          = OUTPUT_DIR / 'valid_inputs.parquet'
VALID_LABELS_PARQUET   = OUTPUT_DIR / 'valid_labels.parquet'

train  = pl.read_parquet(TRAIN_SESSIONS_PARQUET)
inputs = pl.read_parquet(VALID_PARQUET)
labels = pl.read_parquet(VALID_LABELS_PARQUET)

print("=" * 60)
print("1. SCHEMA & SHAPE")
print("=" * 60)
print(f"\ntrain_sessions : {train.shape}")
print(train.schema)
print(f"\nvalid_inputs   : {inputs.shape}")
print(inputs.schema)
print(f"\nvalid_labels   : {labels.shape}")
print(labels.schema)

print("\n" + "=" * 60)
print("2. SAMPLE DATA")
print("=" * 60)
print("\n-- train (1 row) --")
print(train.head(1))
print("\n-- valid_inputs (1 row) --")
print(inputs.head(1))
print("\n-- valid_labels (1 row) --")
print(labels.head(1))

print("\n" + "=" * 60)
print("3. NULL CHECK")
print("=" * 60)
print(f"\ntrain  nulls: {train.null_count().row(0)}")
print(f"inputs nulls: {inputs.null_count().row(0)}")
print(f"labels nulls: {labels.null_count().row(0)}")

print("\n" + "=" * 60)
print("4. SESSION ID CHECKS")
print("=" * 60)

input_sessions = set(inputs['session'].to_list())
label_sessions = set(labels['session'].to_list())
train_session_ids = set(train['session'].to_list())

print(f"\ninputs sessions : {len(input_sessions):,}")
print(f"labels sessions : {len(label_sessions):,}")
print(f"inputs == labels: {input_sessions == label_sessions}")

overlap = input_sessions & train_session_ids
print(f"\nTrain/valid session overlap: {len(overlap):,}  (phải = 0)")

print("\n" + "=" * 60)
print("5. EVENTS SANITY CHECK")
print("=" * 60)

train_event_lens = train.with_columns(
    pl.col('events').list.len().alias('n_events')
)['n_events']
input_event_lens = inputs.with_columns(
    pl.col('events').list.len().alias('n_events')
)['n_events']

print(f"\ntrain  events/session — min:{train_event_lens.min()}, mean:{train_event_lens.mean():.1f}, max:{train_event_lens.max()}")
print(f"inputs events/session — min:{input_event_lens.min()}, mean:{input_event_lens.mean():.1f}, max:{input_event_lens.max()}")
print(f"Any session with 0 events (train) : {(train_event_lens == 0).sum()}")
print(f"Any session with 0 events (inputs): {(input_event_lens == 0).sum()}")

print("\n" + "=" * 60)
print("6. LABEL SANITY CHECK")
print("=" * 60)

label_df = labels.with_columns([
    pl.col('labels').struct.field('clicks').alias('clicks'),
    pl.col('labels').struct.field('carts').alias('carts'),
    pl.col('labels').struct.field('orders').alias('orders'),
])

n_has_clicks = label_df['clicks'].drop_nulls().len()
n_has_carts  = label_df.filter(pl.col('carts').list.len() > 0).height
n_has_orders = label_df.filter(pl.col('orders').list.len() > 0).height
total        = labels.height

print(f"\nSessions có clicks label : {n_has_clicks:,} ({100*n_has_clicks/total:.1f}%)")
print(f"Sessions có carts  label : {n_has_carts:,}  ({100*n_has_carts/total:.1f}%)")
print(f"Sessions có orders label : {n_has_orders:,} ({100*n_has_orders/total:.1f}%)")
print(f"Sessions không có label nào: "
      f"{label_df.filter(pl.col('clicks').is_null() & (pl.col('carts').list.len()==0) & (pl.col('orders').list.len()==0)).height:,}")

print("\n" + "=" * 60)
print("7. ITEM LEAKAGE CHECK")
print("=" * 60)

# So sánh với train_sessions — đúng nguồn model được train
train_aids = set(
    train
    .explode('events')
    .unnest('events')
    ['aid'].to_list()
)
valid_aids = set(
    inputs
    .explode('events')
    .unnest('events')
    ['aid'].to_list()
)

leaked = valid_aids - train_aids
print(f"\nTrain unique aids : {len(train_aids):,}")
print(f"Valid unique aids  : {len(valid_aids):,}")
print(f"Unknown aids in valid (phải = 0): {len(leaked):,}")

print("\n" + "=" * 60)
print("8. TIMESTAMP ORDER CHECK (sample 1000 sessions)")
print("=" * 60)

sample = inputs.sample(min(1000, inputs.height), seed=42)
n_unsorted = 0
for row in sample.iter_rows(named=True):
    ts_list = [e['ts'] for e in row['events']]
    if ts_list != sorted(ts_list):
        n_unsorted += 1

print(f"\nSessions có events không theo thứ tự ts: {n_unsorted} (phải = 0)")

print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
checks = {
    "inputs == labels session ids" : input_sessions == label_sessions,
    "No train/valid overlap"       : len(overlap) == 0,
    "No 0-event sessions (train)"  : (train_event_lens == 0).sum() == 0,
    "No 0-event sessions (inputs)" : (input_event_lens == 0).sum() == 0,
    "No unknown aids in valid"     : len(leaked) == 0,
    "Events sorted by ts"          : n_unsorted == 0,
}
for check, passed in checks.items():
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {check}")

