"""
Simple Kaggle training script
Code: /kaggle/input/datasets/hngphongkiu/rs-mba
Data: /kaggle/input/datasets/hngphongkiu/otto-mba
"""
import sys
import os

# Kaggle paths
MBA_CODE_DIR = "/kaggle/input/datasets/hngphongkiu/rs-mba"
DATA_DIR = "/kaggle/input/datasets/hngphongkiu/otto-mba"
OUTPUT_DIR = "/kaggle/working"

# Add MBA to path
sys.path.insert(0, MBA_CODE_DIR)

# Change to MBA directory
os.chdir(MBA_CODE_DIR)

print("\n" + "="*70)
print("MBA Training on Kaggle")
print("="*70)
print(f"Code directory: {MBA_CODE_DIR}")
print(f"Data directory: {DATA_DIR}")
print(f"Output directory: {OUTPUT_DIR}")

# Check if directories exist
if not os.path.exists(MBA_CODE_DIR):
    print(f"[ERROR] Code directory not found: {MBA_CODE_DIR}")
    sys.exit(1)

if not os.path.exists(DATA_DIR):
    print(f"[ERROR] Data directory not found: {DATA_DIR}")
    sys.exit(1)

# Import training code
try:
    from main import main
    print("[OK] Successfully imported MBA training code\n")
except Exception as e:
    print(f"[ERROR] Failed to import MBA code: {e}")
    sys.exit(1)

# Parse arguments (handle Jupyter/Kaggle notebook environment)
import argparse

parser = argparse.ArgumentParser(description='MBA Training on Kaggle')
parser.add_argument('--model', type=str, default='MF', help='Model: MF or lgn')
parser.add_argument('--h_model', type=str, default='MF')
parser.add_argument('--epochs', type=int, default=400)
parser.add_argument('--C_1', type=int, default=1000)
parser.add_argument('--C_2', type=int, default=1)
parser.add_argument('--alpha', type=float, default=1000)
parser.add_argument('--lambda0', type=float, default=1e-4)
parser.add_argument('--lambda1', type=float, default=1e-6)
parser.add_argument('--beta', type=float, default=0.7)
parser.add_argument('--seed', type=int, default=2020)
parser.add_argument('--batch_size', type=int, default=2048)
parser.add_argument('--device', type=str, default='cuda')
parser.add_argument('--train_method', type=str, default='mba', help='mba or pre')
parser.add_argument('--pretrain_model', type=str, default='MF')
parser.add_argument('--pretrain_early_stop_rounds', type=int, default=20)
parser.add_argument('--test_only', action='store_true')

# Use parse_known_args to ignore extra arguments from Jupyter kernel
args, unknown = parser.parse_known_args()

# Prepare training parameters
param = {
    'datadir': DATA_DIR,
    'folder': OUTPUT_DIR,
    'model': args.model,
    'h_model': args.h_model,
    'dataset': 'otto',
    'epochs': args.epochs,
    'top_k': [10, 20],
    'C_2': args.C_2,
    'C_1': args.C_1,
    'alpha': args.alpha,
    'lambda0': args.lambda0,
    'lambda1': args.lambda1,
    'save_model': 1,
    'seed': args.seed,
    'dropout': 0.0,
    'lr': 0.001,
    'batch_size': args.batch_size,
    'factor_num': 32,
    'num_layers': 3,
    'NSR': 1,
    'device': args.device,
    'emb_dim': 32,
    'early_stop_rounds': 30,
    'train_method': args.train_method,
    'pretrain_early_stop_rounds': args.pretrain_early_stop_rounds,
    'idx': 0,
    'pretrain_model': args.pretrain_model,
    'denoise_type': 'DP',
    'beta': args.beta,
    'test_only': args.test_only,
}

print("Training Configuration:")
print(f"   Dataset: {param['dataset']}")
print(f"   Model: {param['model']}")
print(f"   Train method: {param['train_method']}")
print(f"   Epochs: {param['epochs']}")
print(f"   Batch size: {param['batch_size']}")
print(f"   Alpha: {param['alpha']}")
print(f"   C_1: {param['C_1']}, C_2: {param['C_2']}")
print(f"   Lambda0: {param['lambda0']}, Lambda1: {param['lambda1']}")
print(f"   Device: {param['device']}\n")

# Run training
try:
    main(param)
    print("\n" + "="*70)
    print("[OK] Training completed successfully!")
    print("="*70)
    print(f"Output saved to: {OUTPUT_DIR}\n")
except Exception as e:
    print(f"\n[ERROR] Training failed: {e}\n")
    import traceback
    traceback.print_exc()
    sys.exit(1)
