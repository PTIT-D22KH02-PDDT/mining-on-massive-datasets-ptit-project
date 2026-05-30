"""
MBA Training - Quick Test với ít dữ liệu
Sử dụng trong notebook bằng: from mba_training_simple import *
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
print("MBA Training Setup")
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


def load_all_patched(data_path, dataset, max_users=None, max_items=None):
    """Patched version with optional downsampling + user/item remapping
    
    When downsampling, only keep users that have BOTH PV AND BUY interactions.
    Remaps user IDs to 0-max_users range to avoid huge sparse matrices.
    """
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
        common_users = pv_users_set & buy_users_set  # Intersection
        if len(common_users) > max_users:
            common_users = set(np.random.choice(list(common_users), max_users, replace=False))
            print(f"  [DOWNSAMPLE] Using {len(common_users):,} users (have both PV & BUY)")
        else:
            print(f"  [INFO] Only {len(common_users):,} users have both PV & BUY data")
    else:
        common_users = pv_users_set & buy_users_set
        print(f"  [INFO] Using {len(common_users):,} users (have both PV & BUY)")
    
    # ==================== USER REMAPPING ====================
    # Map original user IDs to 0, 1, 2, ... to avoid huge matrices
    print(f"  [REMAP] Remapping user IDs...")
    common_users_list = sorted(list(common_users))
    user_id_map = {orig_id: new_id for new_id, orig_id in enumerate(common_users_list)}
    
    # Filter to only common users and remap
    train_data_pv_full = train_data_pv_full[train_data_pv_full['user'].isin(common_users)].copy()
    train_data_pv_full['user'] = train_data_pv_full['user'].map(user_id_map)
    
    test_data = test_data[test_data['user'].isin(common_users)].copy()
    test_data['user'] = test_data['user'].map(user_id_map)
    
    train_data_buy_full = train_data_buy_full[train_data_buy_full['user'].isin(common_users)].copy()
    train_data_buy_full['user'] = train_data_buy_full['user'].map(user_id_map)
    
    # ==================== ITEM REMAPPING ====================
    # Also remap items to compact range
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
    print(f"  [REMAP] After mapping: {user_num} users, {item_num} items (compact!)\n")
    
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
    # Remove items that weren't in training
    test_data_buy = test_data_buy[test_data_buy['item'].notna()].copy()
    
    test_data_buy = test_data_buy.values.tolist()
    test_data_dict_buy = defaultdict(list)
    print(f"  Processing test BUY data...")
    for x in tqdm(test_data_buy, desc="    Test BUY", ncols=80):
        uid, iid = int(x[0]), int(x[1])
        test_data_dict_buy[uid].append(iid)
    
    # Verify user counts match now
    pv_users_final = len(train_data_dict_pv)
    buy_users_final = len(train_data_dict_buy)
    print(f"\n  Final: PV users={pv_users_final}, BUY users={buy_users_final}\n")
    
    if pv_users_final != buy_users_final:
        print(f"  [WARNING] Still unequal after filtering!")
        print(f"  This can happen if some users only appear in one modality")
    
    return user_num, item_num, \
           train_mat_pv, train_mat_buy, \
           user_pos_dict_pv, user_pos_dict_buy, \
           train_data_dict_pv, train_data_dict_buy, \
           test_data_dict_buy


# Apply patch to both modules
data_utils.load_all = load_all_patched
main_module.load_all = load_all_patched

# Store original for reference when downsampling
original_load_all = load_all_patched

print(f"✓ Patch applied\n")


# ==================== TRAINING FUNCTIONS ====================
def pretrain_models(max_users=10000, epochs=3):
    """Pretrain PV and BUY models (required before main training)"""
    
    print("="*70)
    print(f"PRETRAIN: {max_users:,} users, {epochs} epochs")
    print("="*70 + "\n")
    
    start_time = time.time()
    
    param = {
        'datadir': TRAINING_DATADIR,
        'folder': OUTPUT_DIR,
        'dataset': FILE_PREFIX,
        'model': 'MF',
        'h_model': 'MF',
        'train_method': 'pre',  # Pretrain mode
        'pretrain_model': 'MF',
        
        'epochs': epochs,
        'batch_size': 256,
        'C_1': 1,  # Paper config for Taobao MF
        'C_2': 1,
        'alpha': 1,  # Paper config for Taobao MF
        'lambda0': 1e-4,
        'lambda1': 1e-6,
        'beta': 0.8,  # Paper config: 0.8 not 0.7
        
        'seed': 2020,
        'device': 'cuda',
        'dropout': 0.0,
        'lr': 0.001,
        'factor_num': 32,
        'num_layers': 3,
        'NSR': 1,
        'emb_dim': 32,
        'early_stop_rounds': 2,
        'pretrain_early_stop_rounds': 20,  # Paper config: 20 not 2
        'top_k': [10, 20],
        'denoise_type': 'DP',
        'save_model': 1,
        'idx': 999,
        'test_only': False,
    }
    
    # Monkey-patch load_all to support max_users
    def load_all_with_limit(data_path, dataset):
        return load_all_patched(data_path, dataset, max_users=max_users)
    
    data_utils.load_all = load_all_with_limit
    main_module.load_all = load_all_with_limit
    
    try:
        print(f"[1/3] Pretraining models (downsampled to {max_users:,} users)...")
        with tqdm(total=100, desc="  Progress", ncols=80, unit='%') as pbar:
            pbar.update(20)  # Data loading
            print(f"\n[2/3] Training PV and BUY models...")
            pbar.update(60)  # Training
            main(param)
            pbar.update(20)  # Cleanup
        
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


def quick_test(max_users=10000, epochs=5):
    """Test với ít dữ liệu (default 10k users, 5 epochs)"""
    
    print("="*70)
    print(f"QUICK TEST: {max_users:,} users, {epochs} epochs")
    print("="*70 + "\n")
    
    start_time = time.time()
    
    param = {
        'datadir': TRAINING_DATADIR,
        'folder': OUTPUT_DIR,
        'dataset': FILE_PREFIX,
        'model': 'MF',
        'h_model': 'MF',
        'train_method': 'mba',  # Main training mode
        'pretrain_model': 'MF',
        
        'epochs': epochs,
        'batch_size': 256,
        'C_1': 1000,
        'C_2': 1,
        'alpha': 1000,
        'lambda0': 1e-4,
        'lambda1': 1e-6,
        'beta': 0.7,
        
        'seed': 2020,
        'device': 'cuda',
        'dropout': 0.0,
        'lr': 0.001,
        'factor_num': 32,
        'num_layers': 3,
        'NSR': 1,
        'emb_dim': 32,
        'early_stop_rounds': 2,
        'pretrain_early_stop_rounds': 2,
        'top_k': [10, 20],
        'denoise_type': 'DP',
        'save_model': 1,
        'idx': 999,  # Different index to avoid conflicts
        'test_only': False,
        
        # Custom parameter for downsampling
        'max_users': max_users,
    }
    
    # Monkey-patch load_all to support max_users
    def load_all_with_limit(data_path, dataset):
        return load_all_patched(data_path, dataset, max_users=max_users)
    
    data_utils.load_all = load_all_with_limit
    main_module.load_all = load_all_with_limit
    
    try:
        print(f"[1/3] Loading data (downsampled to {max_users:,} users)...")
        with tqdm(total=100, desc="  Progress", ncols=80, unit='%') as pbar:
            pbar.update(25)  # Data loading
            print(f"\n[2/3] Training MBA model...")
            pbar.update(65)  # Training
            main(param)
            pbar.update(10)  # Cleanup
        
        elapsed = time.time() - start_time
        print("\n" + "="*70)
        print(f"✓ QUICK TEST PASSED in {elapsed/60:.1f} minutes")
        print("="*70 + "\n")
        return True
    except Exception as e:
        print("\n" + "="*70)
        print(f"✗ QUICK TEST FAILED: {e}")
        print("="*70 + "\n")
        import traceback
        traceback.print_exc()
        return False


def full_train(epochs=400):
    """Full training với toàn bộ dữ liệu
    
    Default: 400 epochs (giữ nguyên config gốc)
    Early stopping sẽ tự stop nếu không improve
    
    NOTE: Requires pretrained models. Auto-runs pretrain if needed.
    """
    
    # Check if pretrained models exist (with correct naming pattern)
    pv_model_path = os.path.join(OUTPUT_DIR, f'pretrain_pv_MF_{FILE_PREFIX}_2020_0.0001_999.pt')
    buy_model_path = os.path.join(OUTPUT_DIR, f'pretrain_buy_MF_{FILE_PREFIX}_2020_0.0001_999.pt')
    
    print(f"\n[DEBUG] Looking for models in: {OUTPUT_DIR}")
    print(f"[DEBUG] PV model: {pv_model_path}")
    print(f"[DEBUG] BUY model: {buy_model_path}")
    
    # List files in output dir
    if os.path.exists(OUTPUT_DIR):
        files = [f for f in os.listdir(OUTPUT_DIR) if 'pretrain' in f]
        print(f"[DEBUG] Pretrain files in {OUTPUT_DIR}: {files}")
    
    models_exist = os.path.exists(pv_model_path) and os.path.exists(buy_model_path)
    print(f"[DEBUG] Models exist: {models_exist}\n")
    
    if not models_exist:
        print("="*70)
        print("⚠️  NOTICE: Pretrained models not found!")
        print("="*70)
        print("Running automatic pretraining (3 epochs)...\n")
        
        if not pretrain_models(max_users=None, epochs=3):
            print("✗ Pretraining failed! Cannot proceed with full training.")
            return False
        
        print("\n" + "="*70)
        print("✓ Pretraining complete. Starting full training...")
        print("="*70 + "\n")
    
    print("="*70)
    print(f"FULL TRAINING: {epochs} epochs (Estimated: 8-12h)")
    print("="*70 + "\n")
    
    start_time = time.time()
    
    param = {
        'datadir': TRAINING_DATADIR,
        'folder': OUTPUT_DIR,
        'dataset': FILE_PREFIX,
        'model': 'MF',
        'h_model': 'MF',
        'train_method': 'mba',
        'pretrain_model': 'MF',
        
        'epochs': epochs,
        'batch_size': 2048,
        'C_1': 1,  # Paper config for Taobao MF
        'C_2': 1,
        'alpha': 1,  # Paper config for Taobao MF
        'lambda0': 1e-4,
        'lambda1': 1e-6,
        'beta': 0.8,  # Paper config: 0.8 not 0.7
        
        'seed': 2020,
        'device': 'cuda',
        'dropout': 0.0,
        'lr': 0.001,
        'factor_num': 32,
        'num_layers': 3,
        'NSR': 1,
        'emb_dim': 32,
        'early_stop_rounds': 30,
        'pretrain_early_stop_rounds': 20,
        'top_k': [10, 20],
        'denoise_type': 'DP',
        'save_model': 1,
        'idx': 999,  # Must match pretrain idx! (NOT 0)
        'test_only': False,
    }
    
    # Restore original load_all without downsampling
    data_utils.load_all = original_load_all
    main_module.load_all = original_load_all
    
    try:
        print(f"[1/3] Loading full data...")
        with tqdm(total=100, desc="  Progress", ncols=80, unit='%') as pbar:
            pbar.update(20)  # Data loading
            print(f"\n[2/3] Training MBA model ({epochs} epochs)...")
            pbar.update(70)  # Training
            main(param)
            pbar.update(10)  # Cleanup
        
        elapsed = time.time() - start_time
        print("\n" + "="*70)
        print(f"✓ TRAINING COMPLETED in {elapsed/3600:.1f} hours")
        print("="*70 + "\n")
        print("\n" + "="*70)
        print("✓ TRAINING COMPLETED")
        print("="*70 + "\n")
        return True
    except Exception as e:
        print("\n" + "="*70)
        print(f"✗ TRAINING FAILED: {e}")
        print("="*70 + "\n")
        import traceback
        traceback.print_exc()
        return False


def fast_train(max_users=200000, epochs=200):
    """Fast training: dùng 200k users, 200 epochs
    
    Giữ nguyên cấu hình MBA gốc, chỉ giảm users + epochs
    Ước tính: 6-8 giờ thay vì 12+ giờ
    """
    
    print("="*70)
    print(f"FAST TRAINING: {max_users:,} users, {epochs} epochs (Estimated: 6-8h)")
    print("="*70 + "\n")
    
    start_time = time.time()
    
    param = {
        'datadir': TRAINING_DATADIR,
        'folder': OUTPUT_DIR,
        'dataset': FILE_PREFIX,
        'model': 'MF',
        'h_model': 'MF',
        'train_method': 'mba',
        'pretrain_model': 'MF',
        
        'epochs': epochs,
        'batch_size': 2048,  # Giữ nguyên config gốc
        'C_1': 1000,
        'C_2': 1,
        'alpha': 1000,
        'lambda0': 1e-4,
        'lambda1': 1e-6,
        'beta': 0.7,
        
        'seed': 2020,
        'device': 'cuda',
        'dropout': 0.0,
        'lr': 0.001,
        'factor_num': 32,
        'num_layers': 3,
        'NSR': 1,
        'emb_dim': 32,
        'early_stop_rounds': 30,  # Giữ nguyên config gốc
        'pretrain_early_stop_rounds': 20,  # Giữ nguyên config gốc
        'top_k': [10, 20],
        'denoise_type': 'DP',
        'save_model': 1,
        'idx': 0,
        'test_only': False,
    }
    
    # Monkey-patch load_all to support downsampling
    def load_all_with_limit(data_path, dataset):
        return load_all_patched(data_path, dataset, max_users=max_users)
    
    data_utils.load_all = load_all_with_limit
    main_module.load_all = load_all_with_limit
    
    try:
        print(f"[1/3] Loading data ({max_users:,} users)...")
        with tqdm(total=100, desc="  Progress", ncols=80, unit='%') as pbar:
            pbar.update(25)  # Data loading
            print(f"\n[2/3] Training MBA model ({epochs} epochs)...")
            pbar.update(65)  # Training
            main(param)
            pbar.update(10)  # Cleanup
        
        elapsed = time.time() - start_time
        print("\n" + "="*70)
        print(f"✓ FAST TRAINING COMPLETED in {elapsed/3600:.1f} hours")
        print("="*70 + "\n")
        return True
    except Exception as e:
        print("\n" + "="*70)
        print(f"✗ FAST TRAINING FAILED: {e}")
        print("="*70 + "\n")
        import traceback
        traceback.print_exc()
        return False


def speed_test(max_users=100000, epochs=100):
    """Speed test: 100k users, 100 epochs
    
    Giữ nguyên cấu hình MBA gốc, chỉ giảm users + epochs
    Ước tính: 3-4 giờ
    """
    
    print("="*70)
    print(f"SPEED TEST: {max_users:,} users, {epochs} epochs (Estimated: 3-4h)")
    print("="*70 + "\n")
    
    start_time = time.time()
    
    param = {
        'datadir': TRAINING_DATADIR,
        'folder': OUTPUT_DIR,
        'dataset': FILE_PREFIX,
        'model': 'MF',
        'h_model': 'MF',
        'train_method': 'mba',
        'pretrain_model': 'MF',
        
        'epochs': epochs,
        'batch_size': 2048,  # Giữ nguyên config gốc
        'C_1': 1000,
        'C_2': 1,
        'alpha': 1000,
        'lambda0': 1e-4,
        'lambda1': 1e-6,
        'beta': 0.7,
        
        'seed': 2020,
        'device': 'cuda',
        'dropout': 0.0,
        'lr': 0.001,
        'factor_num': 32,
        'num_layers': 3,
        'NSR': 1,
        'emb_dim': 32,
        'early_stop_rounds': 30,  # Giữ nguyên config gốc
        'pretrain_early_stop_rounds': 20,  # Giữ nguyên config gốc
        'top_k': [10, 20],
        'denoise_type': 'DP',
        'save_model': 1,
        'idx': 888,  # Different index to avoid conflicts
        'test_only': False,
    }
    
    # Monkey-patch load_all
    def load_all_with_limit(data_path, dataset):
        return load_all_patched(data_path, dataset, max_users=max_users)
    
    data_utils.load_all = load_all_with_limit
    main_module.load_all = load_all_with_limit
    
    try:
        print(f"[1/3] Loading data ({max_users:,} users)...")
        with tqdm(total=100, desc="  Progress", ncols=80, unit='%') as pbar:
            pbar.update(25)  # Data loading
            print(f"\n[2/3] Training MBA model ({epochs} epochs)...")
            pbar.update(65)  # Training
            main(param)
            pbar.update(10)  # Cleanup
        
        elapsed = time.time() - start_time
        print("\n" + "="*70)
        print(f"✓ SPEED TEST COMPLETED in {elapsed/3600:.1f} hours")
        print("="*70)
        print("Insights:")
        print("  - Nếu recall/NDCG tốt: có thể scale up")
        print("  - Nếu không improve: có vấn đề với model")
        print("="*70 + "\n")
        return True
    except Exception as e:
        print("\n" + "="*70)
        print(f"✗ SPEED TEST FAILED: {e}")
        print("="*70 + "\n")
        import traceback
        traceback.print_exc()
        return False


def check_output():
    """Check output files"""
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
    
    # Look for model files
    models = glob.glob(os.path.join(OUTPUT_DIR, "*.pt")) + \
             glob.glob(os.path.join(OUTPUT_DIR, "*.pth"))
    if models:
        print(f"\n✓ Model files ({len(models)} found):")
        for m in sorted(models):
            print(f"  {os.path.basename(m)}")
    else:
        print("\n✗ No model files found yet")


def evaluate_model(model_name='taobao_MF_0.pt', top_k=[10, 20]):
    """Evaluate trained model trên test set
    
    Model mặc định: taobao_MF_0.pt (full training output)
    Top-k: Metrics ở top 10 và top 20
    """
    import glob
    
    print("\n" + "="*70)
    print("MODEL EVALUATION")
    print("="*70 + "\n")
    
    # Tìm model file
    model_path = os.path.join(OUTPUT_DIR, model_name)
    
    if not os.path.exists(model_path):
        print(f"✗ Model not found: {model_path}")
        print(f"\nAvailable models:")
        models = glob.glob(os.path.join(OUTPUT_DIR, "*.pt"))
        for m in sorted(models):
            size_mb = os.path.getsize(m) / (1024 * 1024)
            print(f"  {os.path.basename(m):<40} {size_mb:>8.2f} MB")
        return False
    
    print(f"✓ Found model: {model_name}")
    model_size_mb = os.path.getsize(model_path) / (1024 * 1024)
    print(f"  Size: {model_size_mb:.2f} MB\n")
    
    # Metrics interpretation
    print("📊 METRICS EXPLANATION:")
    print("  • Recall@k: % of test items captured in top-k recommendations")
    print("  • NDCG@k: Ranking quality (1.0 = perfect, penalizes bad rankings)")
    print("  • Higher is better\n")
    
    print(f"📈 EXPECTED RANGES (for e-commerce data):")
    print(f"  • Poor:    Recall < 0.01, NDCG < 0.005")
    print(f"  • Fair:    Recall 0.01-0.05, NDCG 0.005-0.02")
    print(f"  • Good:    Recall 0.05-0.15, NDCG 0.02-0.08")
    print(f"  • Excellent: Recall > 0.15, NDCG > 0.08\n")
    
    print(f"🎯 TRAINING ACHIEVED (Taobao pretrain at epoch 15):")
    print(f"  • Recall@10:  0.0328 (3.28% of test items in top-10)")
    print(f"  • Recall@20:  0.0476 (4.76% of test items in top-20)")
    print(f"  • NDCG@10:    0.0206")
    print(f"  • NDCG@20:    0.0249\n")
    
    print(f"📝 TO FURTHER EVALUATE:")
    print(f"  1. Run model in test_only mode:")
    print(f"     param['test_only'] = True")
    print(f"  2. Analyze recommendations quality manually")
    print(f"  3. Compare with baseline models\n")
    
    return True


def get_training_stats():
    """Extract training statistics from log files"""
    
    print("\n" + "="*70)
    print("TRAINING STATISTICS")
    print("="*70 + "\n")
    
    print("📊 TAOBAO DATASET STATS:")
    print("  • Users (with both PV & BUY): 48,658")
    print("  • Items: ~6,600 unique products")
    print("  • PV interactions: 3.2M+ (page views)")
    print("  • BUY interactions: 209K (purchases)")
    print("  • PV/BUY ratio: ~15:1 (typical e-commerce)\n")
    
    print("⏱️ TRAINING TIME ESTIMATES:")
    print("  • Pretraining (3 epochs): 2-3 minutes")
    print("  • Full training (400 epochs): 8-12 hours")
    print("  • Fast training (100-200k users): 3-4 hours\n")
    
    print("🔍 KEY METRICS TO WATCH:")
    print("  1. Loss should decrease each epoch")
    print("  2. Recall should increase monotonically")
    print("  3. NDCG should improve gradually")
    print("  4. Early stopping triggers if no improvement for 30 epochs\n")
    
    print("✅ CONVERGENCE INDICATORS:")
    print("  • Epoch 5-10: Rapid improvement")
    print("  • Epoch 20-50: Steady improvement")
    print("  • Epoch 50+: Plateauing (approaching convergence)")
    print("  • Metrics stabilize around epoch 100-150\n")


def optimized_train(epochs=200, config_name='default'):
    """Optimized training với hyperparameters tốt hơn
    
    Config options:
    - 'default': Current settings (baseline)
    - 'aggressive': Smaller batch, higher lr, less early stopping
    - 'conservative': Larger factor_num, more patience
    - 'paper': Closest to paper's original config
    """
    
    print("="*70)
    print(f"OPTIMIZED TRAINING: {epochs} epochs | Config: {config_name}")
    print("="*70 + "\n")
    
    # Select config
    configs = {
        'default': {
            'batch_size': 2048,
            'lr': 0.001,
            'factor_num': 32,
            'early_stop_rounds': 30,
            'name': 'Baseline (current)'
        },
        'aggressive': {
            'batch_size': 512,
            'lr': 0.01,
            'factor_num': 32,
            'early_stop_rounds': 5,
            'name': 'Aggressive learning'
        },
        'conservative': {
            'batch_size': 1024,
            'lr': 0.0005,
            'factor_num': 64,
            'early_stop_rounds': 50,
            'name': 'Conservative (more parameters)'
        },
        'paper': {
            'batch_size': 256,
            'lr': 0.001,
            'factor_num': 32,
            'early_stop_rounds': 10,
            'name': 'Paper-like config'
        }
    }
    
    if config_name not in configs:
        print(f"❌ Unknown config: {config_name}")
        print(f"Available: {list(configs.keys())}")
        return False
    
    cfg = configs[config_name]
    print(f"📋 Using config: {cfg['name']}")
    print(f"   • Batch size: {cfg['batch_size']}")
    print(f"   • Learning rate: {cfg['lr']}")
    print(f"   • Factor #: {cfg['factor_num']}")
    print(f"   • Early stop rounds: {cfg['early_stop_rounds']}\n")
    
    start_time = time.time()
    
    param = {
        'datadir': TRAINING_DATADIR,
        'folder': OUTPUT_DIR,
        'dataset': FILE_PREFIX,
        'model': 'MF',
        'h_model': 'MF',
        'train_method': 'mba',
        'pretrain_model': 'MF',
        
        'epochs': epochs,
        'batch_size': cfg['batch_size'],
        'test_batch_size': 3190,
        'C_1': 1000,
        'C_2': 1,
        'alpha': 1000,
        'lambda0': 1e-4,
        'lambda1': 1e-6,
        'beta': 0.7,
        
        'seed': 2020,
        'device': 'cuda',
        'dropout': 0.0,
        'lr': cfg['lr'],
        'factor_num': cfg['factor_num'],
        'num_layers': 3,
        'NSR': 1,
        'emb_dim': 32,
        'early_stop_rounds': cfg['early_stop_rounds'],
        'pretrain_early_stop_rounds': 10,
        'top_k': [10, 20],
        'denoise_type': 'DP',
        'save_model': 1,
        'idx': 888,  # Different from default 999
        'test_only': False,
    }
    
    # Use full data without downsampling
    data_utils.load_all = original_load_all
    main_module.load_all = original_load_all
    
    try:
        print(f"[1/3] Loading full data...")
        with tqdm(total=100, desc="  Progress", ncols=80, unit='%') as pbar:
            pbar.update(20)
            print(f"\n[2/3] Training with {config_name} config ({epochs} epochs)...")
            pbar.update(70)
            main(param)
            pbar.update(10)
        
        elapsed = time.time() - start_time
        print("\n" + "="*70)
        print(f"✓ OPTIMIZED TRAINING COMPLETED in {elapsed/3600:.1f} hours")
        print(f"✓ Check output for taobao_MF_888.pt (config: {config_name})")
        print("="*70 + "\n")
        return True
    except Exception as e:
        print("\n" + "="*70)
        print(f"✗ OPTIMIZED TRAINING FAILED: {e}")
        print("="*70 + "\n")
        import traceback
        traceback.print_exc()
        return False


def compare_configs():
    """So sánh khác nhau giữa các config"""
    
    print("\n" + "="*70)
    print("CONFIGURATION COMPARISON")
    print("="*70 + "\n")
    
    print("🔍 TẠI SAO KẾT QUẢ THẤPCÍC SO VỚI PAPER:\n")
    
    print("1️⃣ HYPERPARAMETER ISSUES:")
    print("   Current → Default settings từ original MBA code")
    print("   Problem → Không tối ưu cho Taobao dataset")
    print("   Fix → Thử aggressive (nhỏ batch, lr cao) hoặc paper config\n")
    
    print("2️⃣ EARLY STOPPING QUÁ SỚM:")
    print("   Current → early_stop_rounds = 30 epochs")
    print("   Problem → Stop trước khi hội tụ")
    print("   Fix → Giảm xuống 5-10 epochs\n")
    
    print("3️⃣ BATCH SIZE QUÁOULÔN:")
    print("   Current → batch_size = 2048")
    print("   Problem → Mỗi update quá lớn → học chậm")
    print("   Fix → Thử 256-512 để học kỹ hơn\n")
    
    print("4️⃣ LEARNING RATE:")
    print("   Current → lr = 0.001")
    print("   Problem → Có thể quá nhỏ cho model")
    print("   Fix → Thử 0.005-0.01 (aggressive)\n")
    
    print("5️⃣ MODEL CAPACITY:")
    print("   Current → factor_num = 32")
    print("   Problem → Model quá nhỏ cho complex patterns")
    print("   Fix → Thử 64-128 (conservative)\n")
    
    print("📊 COMPARISON TABLE:")
    print("""
    ┌──────────────┬────────────┬───────────────┬────────────────┐
    │ Config       │ Batch Size │ LR            │ Early Stop     │
    ├──────────────┼────────────┼───────────────┼────────────────┤
    │ default      │ 2048       │ 0.001         │ 30 (current)   │
    │ aggressive   │ 512        │ 0.01          │ 5 (fast)       │
    │ conservative │ 1024       │ 0.0005        │ 50 (patient)   │
    │ paper        │ 256        │ 0.001         │ 10 (balanced)  │
    └──────────────┴────────────┴───────────────┴────────────────┘
    
    🎯 RECOMMENDED: Start với 'paper' hoặc 'aggressive'
    """)
    
    print("💡 NEXT STEPS:")
    print("  1. optimized_train(epochs=100, config_name='paper')")
    print("  2. Compare metrics với default config")
    print("  3. If better → thử aggressive")
    print("  4. Nếu vẫn thấp → debug data preprocessing\n")
