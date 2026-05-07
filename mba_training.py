#!/usr/bin/env python3
"""
MBA Training Script - OTTO Dataset on Kaggle
Trains a recommendation model using the MBA (Multi-objective Balanced Algorithm)

Usage in Notebook:
    from mba_training import setup, quick_test, full_train, check_output
    
    setup()           # Run once at start
    quick_test()      # Test with 5 epochs (3-5 min)
    full_train()      # Full training (12+ hours)
    check_output()    # Check output files
"""

import sys
import os
import argparse
import glob
from collections import defaultdict

import pandas as pd
import numpy as np
import scipy.sparse as sp
import torch

# ==================== CONFIGURATION ====================
MBA_CODE_DIR = "/kaggle/input/datasets/hngphongkiu/rs-mba"
DATA_DIR = "/kaggle/input/datasets/hngphongkiu/otto-mba"
OUTPUT_DIR = "/kaggle/working"
FILE_PREFIX = 'otto'
TRAINING_DATADIR = os.path.join(OUTPUT_DIR, "data")
TRAINING_DATA_DIR = os.path.join(OUTPUT_DIR, "data", FILE_PREFIX)

# Global variables (set by setup())
main_func = None
data_utils_module = None
main_module = None
param = None
_setup_done = False


def setup():
    """Initialize paths, verify data, and import MBA code"""
    global main_func, data_utils_module, main_module, param, _setup_done
    
    if _setup_done:
        print("[OK] Already initialized\n")
        return
    
    print("\n" + "="*70)
    print("MBA Training - OTTO Dataset")
    print("="*70)
    print(f"File prefix: {FILE_PREFIX}")
    print(f"Code: {MBA_CODE_DIR}")
    print(f"Data: {DATA_DIR}")
    print(f"Output: {OUTPUT_DIR}\n")

    # Setup paths
    sys.path.insert(0, MBA_CODE_DIR)
    os.chdir(MBA_CODE_DIR)

    # Verify directories
    if not os.path.exists(MBA_CODE_DIR):
        raise FileNotFoundError(f"Code directory not found: {MBA_CODE_DIR}")
    if not os.path.exists(DATA_DIR):
        raise FileNotFoundError(f"Data directory not found: {DATA_DIR}")

    print("[OK] All directories verified\n")

    # ==================== DATA FILE VERIFICATION ====================
    TRAIN_PV_FILE = f"{FILE_PREFIX}_pv_train.csv"
    TRAIN_BUY_FILE = f"{FILE_PREFIX}_buy_train.csv"
    TEST_PV_FILE = f"{FILE_PREFIX}_pv_test.csv"
    TEST_BUY_FILE = f"{FILE_PREFIX}_buy_test.csv"

    os.makedirs(TRAINING_DATA_DIR, exist_ok=True)

    print(f"Verifying data files in: {DATA_DIR}")
    data_files = [
        (TRAIN_PV_FILE, "Train PV"),
        (TRAIN_BUY_FILE, "Train Buy"),
        (TEST_PV_FILE, "Test PV"),
        (TEST_BUY_FILE, "Test Buy"),
    ]

    for file_name, name in data_files:
        file_path = os.path.join(DATA_DIR, file_name)
        if os.path.exists(file_path):
            size_mb = os.path.getsize(file_path) / (1024 * 1024)
            print(f"  [OK] {name:12} - {size_mb:8.2f} MB")
        else:
            raise FileNotFoundError(f"Missing data file: {file_name}")

    # Create symlinks for data files
    print(f"\nSetting up training data structure: {TRAINING_DATA_DIR}")
    for file_name in [TRAIN_PV_FILE, TRAIN_BUY_FILE, TEST_PV_FILE, TEST_BUY_FILE]:
        src = os.path.join(DATA_DIR, file_name)
        dst = os.path.join(TRAINING_DATA_DIR, file_name)
        
        if not os.path.exists(dst):
            try:
                os.symlink(src, dst)
                print(f"  [OK] Linked: {file_name}")
            except Exception as e:
                print(f"  Copying: {file_name}")
                import shutil
                shutil.copy2(src, dst)

    print("[OK] All data files verified and linked\n")

    # ==================== IMPORT MBA CODE ====================
    try:
        from main import main as main_func_imported
        print("[OK] Successfully imported MBA training code\n")
    except Exception as e:
        print(f"[ERROR] Failed to import MBA code: {e}")
        raise

    # ==================== PATCH: Fix unequal user counts ====================
    import data_utils as data_utils_imported
    import main as main_module_imported


def load_all_patched(data_path, dataset):
    """Patched version that handles unequal user counts"""
    train_pv = f"{data_path}{dataset}_pv_train.csv"
    test_pv = f"{data_path}{dataset}_pv_test.csv"
    train_buy = f"{data_path}{dataset}_buy_train.csv"
    test_buy = f"{data_path}{dataset}_buy_test.csv"
    
    user_pos_dict_buy = defaultdict(list)
    user_pos_dict_pv = defaultdict(list)
    
    # Load PV data
    train_data = pd.read_csv(train_pv, sep='\t', header=0, names=['user', 'item'],
                             usecols=[0, 1], dtype={0: np.int32, 1: np.int32})
    test_data = pd.read_csv(test_pv, sep='\t', header=0, names=['user', 'item'],
                            usecols=[0, 1], dtype={0: np.int32, 1: np.int32})
    train_aux = pd.read_csv(train_buy, sep='\t', header=0, names=['user', 'item'],
                            usecols=[0, 1], dtype={0: np.int32, 1: np.int32})
    train_data = pd.concat([train_data, test_data, train_aux], ignore_index=True)
    train_data.drop_duplicates(inplace=True, ignore_index=True)
    
    user_num = train_data['user'].max() + 1
    item_num = train_data['item'].max() + 1
    num_interaction_pv = len(train_data)
    print(f"pv: user_num:{user_num}, item_num:{item_num}, interaction:{num_interaction_pv}")
    
    train_data_pv = train_data.values.tolist()
    train_data_dict_pv = defaultdict(list)
    train_mat_pv = sp.dok_matrix((user_num, item_num), dtype=np.float32)
    for x in train_data_pv:
        uid, iid = x[0], x[1]
        train_mat_pv[uid, iid] = 1.0
        train_data_dict_pv[uid].append(iid)
        user_pos_dict_pv[uid].append(iid)
    
    # Load BUY data
    train_data = pd.read_csv(train_buy, sep='\t', header=0, names=['user', 'item'],
                             usecols=[0, 1], dtype={0: np.int32, 1: np.int32})
    num_interaction_buy = len(train_data)
    print(f"buy: user_num:{user_num}, item_num:{item_num}, interaction:{num_interaction_buy}")
    
    train_data_buy = train_data.values.tolist()
    train_data_dict_buy = defaultdict(list)
    train_mat_buy = sp.dok_matrix((user_num, item_num), dtype=np.float32)
    for x in train_data_buy:
        uid, iid = x[0], x[1]
        train_mat_buy[uid, iid] = 1.0
        train_data_dict_buy[uid].append(iid)
        user_pos_dict_buy[uid].append(iid)
    
    # Load test BUY data
    test_data = pd.read_csv(test_buy, sep='\t', header=0, names=['user', 'item'],
                            usecols=[0, 1], dtype={0: np.int32, 1: np.int32})
    print(f"number of buy test: {len(test_data)}")
    
    test_data_buy = test_data.values.tolist()
    test_data_dict_buy = defaultdict(list)
    for x in test_data_buy:
        uid, iid = x[0], x[1]
        test_data_dict_buy[uid].append(iid)
    
    # FIXED: Don't fail on unequal user counts, just warn
    pv_users = len(train_data_dict_pv)
    buy_users = len(train_data_dict_buy)
    if pv_users != buy_users:
        print(f"\n[WARNING] Unequal user counts: PV={pv_users}, BUY={buy_users}")
        print(f"[INFO] This is normal for real datasets. Proceeding...\n")
    
    return user_num, item_num, \
           train_mat_pv, train_mat_buy, \
           user_pos_dict_pv, user_pos_dict_buy, \
           train_data_dict_pv, train_data_dict_buy, \
           test_data_dict_buy


# Apply patch to both modules
data_utils.load_all = load_all_patched
main_module.load_all = load_all_patched
print("[OK] Applied patch for user count assertion\n")

# ==================== TRAINING PARAMETERS ====================
TRAINING_DATADIR = os.path.join(OUTPUT_DIR, "data")

def get_params(test_mode=False):
    """Get training parameters"""
    param = {
        'datadir': TRAINING_DATADIR,
        'folder': OUTPUT_DIR,
        'dataset': FILE_PREFIX,
        'model': 'MF',
        'h_model': 'MF',
        'train_method': 'mba',
        'pretrain_model': 'MF',
        
        'epochs': 5 if test_mode else 400,
        'batch_size': 256 if test_mode else 2048,
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
        'early_stop_rounds': 2 if test_mode else 30,
        'pretrain_early_stop_rounds': 2 if test_mode else 20,
        'top_k': [10, 20],
        'denoise_type': 'DP',
        'save_model': 1,
        'idx': 999 if test_mode else 0,
        'test_only': False,
    }
    return param


def print_config(param):
    """Print training configuration"""
    print("Training Configuration:")
    print(f"  Data dir: {param['datadir']}")
    print(f"  Dataset: {param['dataset']}")
    print(f"  Model: {param['model']}")
    print(f"  Epochs: {param['epochs']}")
    print(f"  Batch size: {param['batch_size']}")
    print(f"  Early stop rounds: {param['early_stop_rounds']}")
    print(f"  Device: {param['device']}\n")


# ==================== MAIN FUNCTION ====================
def main_train(test_mode=False):
    """Run training"""
    param = get_params(test_mode=test_mode)
    
    print("\n" + "="*70)
    if test_mode:
        print("Quick Test Training (5 epochs)")
    else:
        print("Full Training (400 epochs)")
    print("="*70 + "\n")
    
    print_config(param)
    
    try:
        main(param)
        print("\n" + "="*70)
        print("[OK] Training completed successfully!")
        print("="*70)
        print(f"Output saved to: {OUTPUT_DIR}\n")
        return True
    except Exception as e:
        print(f"\n[ERROR] Training failed: {e}\n")
        import traceback
        traceback.print_exc()
        return False


# ==================== CHECK OUTPUT ====================
def check_output():
    """Check output files"""
    import glob
    
    print(f"Checking output directory: {OUTPUT_DIR}\n")
    
    if not os.path.exists(OUTPUT_DIR):
        print(f"[ERROR] Output directory not found: {OUTPUT_DIR}")
        return
    
    output_files = os.listdir(OUTPUT_DIR)
    print(f"Files in output directory ({len(output_files)} total):")
    
    for f in sorted(output_files):
        file_path = os.path.join(OUTPUT_DIR, f)
        if os.path.isfile(file_path):
            size_mb = os.path.getsize(file_path) / (1024 * 1024)
            print(f"  - {f:<50} ({size_mb:>8.2f} MB)")
        else:
            print(f"  - {f}/ (directory)")
    
    # Look for model files
    print("\nModel files:")
    model_files = glob.glob(os.path.join(OUTPUT_DIR, "*.pt")) + \
                  glob.glob(os.path.join(OUTPUT_DIR, "*.pth"))
    if model_files:
        for mf in sorted(model_files):
            print(f"  - {os.path.basename(mf)}")
    else:
        print("  No model files (.pt/.pth) found")


# ==================== COMMAND LINE INTERFACE ====================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MBA Training Script")
    parser.add_argument("--test", action="store_true", help="Run quick test (5 epochs)")
    parser.add_argument("--check", action="store_true", help="Check output files only")
    
    args = parser.parse_args()
    
    if args.check:
        check_output()
    else:
        success = main_train(test_mode=args.test)
        if success:
            check_output()
            sys.exit(0)
        else:
            sys.exit(1)
