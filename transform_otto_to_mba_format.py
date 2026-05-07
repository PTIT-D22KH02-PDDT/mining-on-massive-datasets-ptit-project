"""
Transform OTTO parquet data format to MBA format (Beibei/Taobao style)
- clicks → pv (page view)
- orders → buy
Output: TSV files with uid(session), sid(article_id)

OTTO data structure:
  - train_parquet/: 100 parquet files with session, aid, ts, type (clicks/carts/orders)
  - test_parquet/: similar structure
  - test_labels.parquet: ground truth for test sessions
"""

import pandas as pd
import os
from pathlib import Path

# Paths
# For local development
# OTTO_TRAIN_DIR = "./datasets/OTTO/train_parquet"
# OTTO_TEST_DIR = "./datasets/OTTO/test_parquet"
# OUTPUT_DIR = "./MBA/data/otto"

# For Kaggle
KAGGLE_MODE = True  # Set to False for local development
if KAGGLE_MODE:
    OTTO_DATASET_DIR = "/kaggle/input/datasets/cdeotte/otto-validation"
    OTTO_TRAIN_DIR = os.path.join(OTTO_DATASET_DIR, "train_parquet")
    OTTO_TEST_DIR = os.path.join(OTTO_DATASET_DIR, "test_parquet")
    OUTPUT_DIR = "/kaggle/working"
else:
    OTTO_TRAIN_DIR = "./datasets/OTTO/train_parquet"
    OTTO_TEST_DIR = "./datasets/OTTO/test_parquet"
    OUTPUT_DIR = "./MBA/data/otto"

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

def load_parquet_folder(folder_path):
    """Load all parquet files from folder"""
    print(f"Loading parquet files from {folder_path}...")
    
    parquet_files = sorted(Path(folder_path).glob("*.parquet"))
    print(f"  Found {len(parquet_files)} parquet files")
    
    dfs = []
    for idx, file_path in enumerate(parquet_files):
        if idx % 20 == 0:
            print(f"  Loading file {idx}/{len(parquet_files)}...")
        df = pd.read_parquet(file_path)
        dfs.append(df)
    
    # Concatenate all dataframes
    combined_df = pd.concat(dfs, ignore_index=True)
    print(f"[OK] Loaded {len(combined_df)} total rows")
    
    return combined_df

def extract_interactions(df, event_type):
    """Extract specific event type interactions"""
    interactions = df[df['type'] == event_type][['session', 'aid']]
    return list(zip(interactions['session'], interactions['aid']))

def save_interactions(interactions, output_path):
    """Save interactions to TSV format"""
    with open(output_path, "w") as f:
        f.write("uid\tsid\n")
        for uid, sid in interactions:
            f.write(f"{uid}\t{sid}\n")

def transform_otto_to_mba():
    """
    Transform OTTO parquet to MBA format CSV
    """
    
    # ==================== LOAD TRAIN DATA ====================
    print("Loading OTTO TRAIN data from parquet...")
    train_df = load_parquet_folder(OTTO_TRAIN_DIR)
    
    print("\nTrain data info:")
    print(f"  Shape: {train_df.shape}")
    print(f"  Event types: {train_df['type'].value_counts().to_dict()}")
    print(f"  Session range: {train_df['session'].min()} - {train_df['session'].max()}")
    
    # Extract clicks and orders from train
    train_clicks = extract_interactions(train_df, 'clicks')
    train_orders = extract_interactions(train_df, 'orders')
    
    print(f"\n[OK] Extracted {len(train_clicks)} clicks, {len(train_orders)} orders from TRAIN")
    
    # ==================== LOAD TEST DATA ====================
    print("\nLoading OTTO TEST data from parquet...")
    test_df = load_parquet_folder(OTTO_TEST_DIR)
    
    print("\nTest data info:")
    print(f"  Shape: {test_df.shape}")
    print(f"  Event types: {test_df['type'].value_counts().to_dict()}")
    print(f"  Session range: {test_df['session'].min()} - {test_df['session'].max()}")
    
    # Extract clicks and orders from test
    test_clicks = extract_interactions(test_df, 'clicks')
    test_orders = extract_interactions(test_df, 'orders')
    
    print(f"\n[OK] Extracted {len(test_clicks)} clicks, {len(test_orders)} orders from TEST")
    
    # ==================== SAVE FILES ====================
    print("\nSaving to TSV format...")
    
    train_pv_path = os.path.join(OUTPUT_DIR, "otto_pv_train.csv")
    save_interactions(train_clicks, train_pv_path)
    print(f"  [OK] Saved {len(train_clicks)} to {train_pv_path}")
    
    train_buy_path = os.path.join(OUTPUT_DIR, "otto_buy_train.csv")
    save_interactions(train_orders, train_buy_path)
    print(f"  [OK] Saved {len(train_orders)} to {train_buy_path}")
    
    test_pv_path = os.path.join(OUTPUT_DIR, "otto_pv_test.csv")
    save_interactions(test_clicks, test_pv_path)
    print(f"  [OK] Saved {len(test_clicks)} to {test_pv_path}")
    
    test_buy_path = os.path.join(OUTPUT_DIR, "otto_buy_test.csv")
    save_interactions(test_orders, test_buy_path)
    print(f"  [OK] Saved {len(test_orders)} to {test_buy_path}")
    
    print("\n[OK] Transformation complete!")
    print("\nFinal Statistics:")
    print(f"  Train PV (clicks):  {len(train_clicks):,}")
    print(f"  Train Buy (orders): {len(train_orders):,}")
    print(f"  Test PV (clicks):   {len(test_clicks):,}")
    print(f"  Test Buy (orders):  {len(test_orders):,}")
    print(f"\nOutput files saved to: {OUTPUT_DIR}")
    print(f"  - otto_pv_train.csv")
    print(f"  - otto_buy_train.csv")
    print(f"  - otto_pv_test.csv")
    print(f"  - otto_buy_test.csv")

if __name__ == "__main__":
    transform_otto_to_mba()
