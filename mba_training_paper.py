"""
MBA Training - Exact Paper Config for Taobao
Paper: "Improving Implicit Feedback-Based Recommendation through Multi-Behavior Alignment" (SIGIR 2023)
Taobao Config: alpha=1, C_1=1, C_2=1, lambda0=1e-4, beta=0.8
"""

import sys
import os
from collections import defaultdict
import pandas as pd
import numpy as np
import scipy.sparse as sp
import torch
import shutil
from tqdm import tqdm
import time

# ==================== CONFIG ====================
MBA_CODE_DIR = "/kaggle/input/datasets/hngphongkiu/rs-mba"
DATA_DIR = "/kaggle/input/datasets/hngphongkiu/rs-mba/data/taobao"
OUTPUT_DIR = "/kaggle/working"
FILE_PREFIX = 'taobao'
TRAINING_DATADIR = os.path.join(OUTPUT_DIR, "data")
TRAINING_DATA_DIR = os.path.join(OUTPUT_DIR, "data", FILE_PREFIX)

# Setup paths
sys.path.insert(0, MBA_CODE_DIR)
os.chdir(MBA_CODE_DIR)

print("\n" + "="*70)
print("MBA Training - Paper Config (Taobao)")
print("="*70)

# Verify directories
if not os.path.exists(MBA_CODE_DIR):
    raise FileNotFoundError(f"Code dir not found: {MBA_CODE_DIR}")
if not os.path.exists(DATA_DIR):
    raise FileNotFoundError(f"Data dir not found: {DATA_DIR}")

print(f"✓ Paths verified")

# ==================== PREPARE DATA ====================
TRAIN_PV_FILE = f"{FILE_PREFIX}_pv_train.csv"
TRAIN_BUY_FILE = f"{FILE_PREFIX}_buy_train.csv"
TEST_PV_FILE = f"{FILE_PREFIX}_pv_test.csv"
TEST_BUY_FILE = f"{FILE_PREFIX}_buy_test.csv"

os.makedirs(TRAINING_DATA_DIR, exist_ok=True)

# Create symlinks
for file_name in [TRAIN_PV_FILE, TRAIN_BUY_FILE, TEST_PV_FILE, TEST_BUY_FILE]:
    src = os.path.join(DATA_DIR, file_name)
    dst = os.path.join(TRAINING_DATA_DIR, file_name)
    
    if not os.path.exists(dst):
        try:
            os.symlink(src, dst)
        except:
            shutil.copy2(src, dst)

print(f"✓ Data files linked\n")

# ==================== IMPORT MBA ====================
from main import main
import data_utils
import main as main_module


def load_all_patched(data_path, dataset, max_users=None):
    """Patched version with optional downsampling + user/item remapping"""
    train_pv = f"{data_path}{dataset}_pv_train.csv"
    test_pv = f"{data_path}{dataset}_pv_test.csv"
    train_buy = f"{data_path}{dataset}_buy_train.csv"
    test_buy = f"{data_path}{dataset}_buy_test.csv"
    
    user_pos_dict_buy = defaultdict(list)
    user_pos_dict_pv = defaultdict(list)
    
    # Load PV data
    print(f"  Loading PV data...")
    train_data_pv_full = pd.read_csv(train_pv, sep='\t', header=0, names=['user', 'item'],
                             usecols=[0, 1], dtype={0: np.int32, 1: np.int32})
    test_data = pd.read_csv(test_pv, sep='\t', header=0, names=['user', 'item'],
                            usecols=[0, 1], dtype={0: np.int32, 1: np.int32})
    
    # Load BUY data
    print(f"  Loading BUY data...")
    train_data_buy_full = pd.read_csv(train_buy, sep='\t', header=0, names=['user', 'item'],
                             usecols=[0, 1], dtype={0: np.int32, 1: np.int32})
    
    # Get users that have BOTH PV and BUY interactions
    pv_users_set = set(train_data_pv_full['user'].unique()) | set(test_data['user'].unique())
    buy_users_set = set(train_data_buy_full['user'].unique())
    
    print(f"  PV users: {len(pv_users_set):,}, BUY users: {len(buy_users_set):,}")
    
    # For downsampling: only keep users with both PV and BUY
    if max_users:
        common_users = pv_users_set & buy_users_set
        if len(common_users) > max_users:
            common_users = set(np.random.choice(list(common_users), max_users, replace=False))
            print(f"  [DOWNSAMPLE] Using {len(common_users):,} users")
        else:
            print(f"  [INFO] Only {len(common_users):,} users have both PV & BUY data")
    else:
        common_users = pv_users_set & buy_users_set
        print(f"  [INFO] Using {len(common_users):,} users (have both PV & BUY)")
    
    # Remap user IDs to 0, 1, 2, ...
    print(f"  [REMAP] Remapping user IDs...")
    common_users_list = sorted(list(common_users))
    user_id_map = {orig_id: new_id for new_id, orig_id in enumerate(common_users_list)}
    
    train_data_pv_full = train_data_pv_full[train_data_pv_full['user'].isin(common_users)].copy()
    train_data_pv_full['user'] = train_data_pv_full['user'].map(user_id_map)
    
    test_data = test_data[test_data['user'].isin(common_users)].copy()
    test_data['user'] = test_data['user'].map(user_id_map)
    
    train_data_buy_full = train_data_buy_full[train_data_buy_full['user'].isin(common_users)].copy()
    train_data_buy_full['user'] = train_data_buy_full['user'].map(user_id_map)
    
    # Remap items to compact range
    print(f"  [REMAP] Remapping item IDs...")
    all_items = set(train_data_pv_full['item'].unique()) | set(test_data['item'].unique()) | set(train_data_buy_full['item'].unique())
    items_list = sorted(list(all_items))
    item_id_map = {orig_id: new_id for new_id, orig_id in enumerate(items_list)}
    
    train_data_pv_full['item'] = train_data_pv_full['item'].map(item_id_map)
    test_data['item'] = test_data['item'].map(item_id_map)
    train_data_buy_full['item'] = train_data_buy_full['item'].map(item_id_map)
    
    # Combine PV data
    train_data = pd.concat([train_data_pv_full, test_data], ignore_index=True)
    train_data.drop_duplicates(inplace=True, ignore_index=True)
    
    user_num = len(common_users_list)
    item_num = len(items_list)
    print(f"  [REMAP] After mapping: {user_num} users, {item_num} items\n")
    
    num_interaction_pv = len(train_data)
    print(f"  pv: {user_num} users, {item_num} items, {num_interaction_pv} interactions")
    
    train_data_pv = train_data.values.tolist()
    train_data_dict_pv = defaultdict(list)
    train_mat_pv = sp.dok_matrix((user_num, item_num), dtype=np.float32)
    print(f"  Building PV sparse matrix...")
    for x in tqdm(train_data_pv, desc="    PV matrix", ncols=80):
        uid, iid = int(x[0]), int(x[1])
        train_mat_pv[uid, iid] = 1.0
        train_data_dict_pv[uid].append(iid)
        user_pos_dict_pv[uid].append(iid)
    
    num_interaction_buy = len(train_data_buy_full)
    print(f"  buy: {user_num} users, {item_num} items, {num_interaction_buy} interactions")
    
    train_data_buy = train_data_buy_full.values.tolist()
    train_data_dict_buy = defaultdict(list)
    train_mat_buy = sp.dok_matrix((user_num, item_num), dtype=np.float32)
    print(f"  Building BUY sparse matrix...")
    for x in tqdm(train_data_buy, desc="    BUY matrix", ncols=80):
        uid, iid = int(x[0]), int(x[1])
        train_mat_buy[uid, iid] = 1.0
        train_data_dict_buy[uid].append(iid)
        user_pos_dict_buy[uid].append(iid)
    
    # Load test BUY data
    print(f"  Loading test BUY data...")
    test_data_buy = pd.read_csv(test_buy, sep='\t', header=0, names=['user', 'item'],
                            usecols=[0, 1], dtype={0: np.int32, 1: np.int32})
    test_data_buy = test_data_buy[test_data_buy['user'].isin(common_users)].copy()
    test_data_buy['user'] = test_data_buy['user'].map(user_id_map)
    test_data_buy['item'] = test_data_buy['item'].map(item_id_map)
    test_data_buy = test_data_buy[test_data_buy['item'].notna()].copy()
    
    test_data_buy = test_data_buy.values.tolist()
    test_data_dict_buy = defaultdict(list)
    print(f"  Processing test BUY data...")
    for x in tqdm(test_data_buy, desc="    Test BUY", ncols=80):
        uid, iid = int(x[0]), int(x[1])
        test_data_dict_buy[uid].append(iid)
    
    pv_users_final = len(train_data_dict_pv)
    buy_users_final = len(train_data_dict_buy)
    print(f"\n  Final: PV users={pv_users_final}, BUY users={buy_users_final}\n")
    
    return user_num, item_num, \
           train_mat_pv, train_mat_buy, \
           user_pos_dict_pv, user_pos_dict_buy, \
           train_data_dict_pv, train_data_dict_buy, \
           test_data_dict_buy


# Apply patch
data_utils.load_all = load_all_patched
main_module.load_all = load_all_patched
original_load_all = load_all_patched

print(f"✓ Patch applied\n")


# ==================== PAPER CONFIG FOR TAOBAO ====================
def get_paper_config(train_method='pre', epochs=3, idx=999):
    """
    Paper config for Taobao + MF
    From README: alpha=1, C_1=1, C_2=1, lambda0=1e-4, beta=0.8
    """
    return {
        'datadir': TRAINING_DATADIR,
        'folder': OUTPUT_DIR,
        'dataset': FILE_PREFIX,
        'model': 'MF',
        'h_model': 'MF',
        'train_method': train_method,
        'pretrain_model': 'MF',
        
        'epochs': epochs,
        'batch_size': 256,
        'test_batch_size': 3190,
        'C_1': 1,  # PAPER CONFIG
        'C_2': 1,
        'alpha': 1,  # PAPER CONFIG
        'lambda0': 1e-4,
        'lambda1': 1e-6,
        'beta': 0.8,  # PAPER CONFIG
        
        'seed': 2020,
        'device': 'cuda',
        'dropout': 0.0,
        'lr': 0.001,
        'factor_num': 32,
        'num_layers': 3,
        'NSR': 1,
        'emb_dim': 32,
        'early_stop_rounds': 30,
        'pretrain_early_stop_rounds': 20,  # PAPER CONFIG
        'top_k': [10, 20],
        'denoise_type': 'DP',
        'save_model': 1,
        'idx': idx,
        'test_only': False,
    }


# ==================== TRAINING FUNCTIONS ====================
def pretrain(epochs=3):
    """Pretrain PV and BUY models (Paper config)"""
    
    print("="*70)
    print(f"PRETRAIN: Full data, {epochs} epochs")
    print("="*70)
    print("Config: alpha=1, C_1=1, C_2=1, beta=0.8 (PAPER)")
    print("="*70 + "\n")
    
    start_time = time.time()
    
    param = get_paper_config(train_method='pre', epochs=epochs, idx=999)
    
    # Use full data
    data_utils.load_all = original_load_all
    main_module.load_all = original_load_all
    
    try:
        print(f"[1/3] Loading full Taobao data...")
        print(f"[2/3] Training PV and BUY models...\n")
        main(param)
        
        elapsed = time.time() - start_time
        print("\n" + "="*70)
        print(f"✓ PRETRAIN COMPLETED in {elapsed/60:.1f} minutes")
        print("="*70 + "\n")
        return True
    except Exception as e:
        print("\n" + "="*70)
        print(f"✗ PRETRAIN FAILED: {e}")
        print("="*70 + "\n")
        import traceback
        traceback.print_exc()
        return False


def train(epochs=400):
    """Full training with MBA (Paper config)"""
    
    print("="*70)
    print(f"FULL TRAINING: Full data, {epochs} epochs")
    print("="*70)
    print("Config: alpha=1, C_1=1, C_2=1, beta=0.8 (PAPER)")
    print("="*70 + "\n")
    
    # Check pretrained models
    pv_model_path = os.path.join(OUTPUT_DIR, f'pretrain_pv_MF_{FILE_PREFIX}_2020_0.0001_999.pt')
    buy_model_path = os.path.join(OUTPUT_DIR, f'pretrain_buy_MF_{FILE_PREFIX}_2020_0.0001_999.pt')
    
    if not os.path.exists(pv_model_path) or not os.path.exists(buy_model_path):
        print("⚠️ Pretrained models not found! Running pretrain first...\n")
        if not pretrain(epochs=3):
            print("✗ Pretraining failed!")
            return False
        print("\n" + "="*70)
        print("✓ Pretraining complete. Starting full training...")
        print("="*70 + "\n")
    
    start_time = time.time()
    
    param = get_paper_config(train_method='mba', epochs=epochs, idx=999)
    
    # Use full data
    data_utils.load_all = original_load_all
    main_module.load_all = original_load_all
    
    try:
        print(f"[1/3] Loading full Taobao data...")
        print(f"[2/3] Training MBA model ({epochs} epochs)...\n")
        main(param)
        
        elapsed = time.time() - start_time
        print("\n" + "="*70)
        print(f"✓ FULL TRAINING COMPLETED in {elapsed/3600:.1f} hours")
        print("="*70 + "\n")
        return True
    except Exception as e:
        print("\n" + "="*70)
        print(f"✗ TRAINING FAILED: {e}")
        print("="*70 + "\n")
        import traceback
        traceback.print_exc()
        return False


def check_output():
    """List output files"""
    import glob
    
    print(f"\nChecking output: {OUTPUT_DIR}\n")
    
    if not os.path.exists(OUTPUT_DIR):
        print(f"✗ Output directory not found")
        return
    
    files = [f for f in os.listdir(OUTPUT_DIR) 
             if os.path.isfile(os.path.join(OUTPUT_DIR, f))]
    
    if files:
        print(f"Files in output ({len(files)} total):")
        for f in sorted(files):
            fpath = os.path.join(OUTPUT_DIR, f)
            size_mb = os.path.getsize(fpath) / (1024 * 1024)
            print(f"  {f:<50} {size_mb:>8.2f} MB")
    
    # Model files
    models = glob.glob(os.path.join(OUTPUT_DIR, "*.pt"))
    if models:
        print(f"\n✓ Model files ({len(models)} found):")
        for m in sorted(models):
            print(f"  {os.path.basename(m)}")
    else:
        print("\n✗ No model files found")


print("\n" + "="*70)
print("PAPER CONFIG TRAINING")
print("="*70)
print("\nUsage:")
print("  pretrain(epochs=3)           # Pretrain models")
print("  train(epochs=400)            # Full training")
print("  check_output()               # List files")
print("\nExample:")
print("  pretrain(epochs=3)")
print("  train(epochs=400)")
print("="*70 + "\n")
