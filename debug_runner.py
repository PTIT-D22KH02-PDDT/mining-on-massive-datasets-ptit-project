#!/usr/bin/env python3
"""
Debug wrapper for MBA training - Shows what's happening at each step
"""
import sys
import os
import argparse
import logging
from datetime import datetime
import json

# Setup comprehensive logging
def setup_logging(output_folder):
    log_dir = os.path.join(output_folder, "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"debug_{timestamp}.log")
    
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    
    # File handler (detailed)
    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s'
    )
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    
    # Console handler (less verbose)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter_console = logging.Formatter(
        '%(levelname)s - %(message)s'
    )
    ch.setFormatter(formatter_console)
    logger.addHandler(ch)
    
    return logger, log_file

def main():
    parser = argparse.ArgumentParser(description="Debug runner for MBA recommender system")
    
    # Original parameters
    parser.add_argument("--datadir", default="/kaggle/working/data", help="Data directory")
    parser.add_argument("--folder", default="/kaggle/working/output", help="Output folder")
    parser.add_argument("--dataset", default="otto", help="Dataset name (otto, beibei, taobao)")
    parser.add_argument("--train_method", default="pre", help="Training method (pre, mba)")
    parser.add_argument("--model", default="MF", help="Model type (MF, lgn)")
    parser.add_argument("--pretrain_model", default="MF", help="Pretrain model type")
    parser.add_argument("--lambda0", type=float, default=1e-4, help="Regularization parameter")
    parser.add_argument("--lambda1", type=float, default=1e-4, help="Regularization parameter for MBA")
    parser.add_argument("--pretrain_early_stop_rounds", type=int, default=20, help="Early stopping rounds")
    parser.add_argument("--idx", type=int, default=0, help="Experiment index")
    parser.add_argument("--seed", type=int, default=0, help="Random seed")
    parser.add_argument("--batch_size", type=int, default=2048, help="Batch size")
    parser.add_argument("--emb_dim", type=int, default=64, help="Embedding dimension")
    parser.add_argument("--num_layers", type=int, default=3, help="Number of layers (for LightGCN)")
    parser.add_argument("--dropout", type=float, default=0.0, help="Dropout rate")
    parser.add_argument("--device", default="cuda", help="Device (cuda or cpu)")
    parser.add_argument("--test_only", action="store_true", help="Only run evaluation")
    
    args = parser.parse_args()
    
    # Setup logging first
    logger, log_file = setup_logging(args.folder)
    logger.info("=" * 80)
    logger.info("MBA RECOMMENDER SYSTEM - DEBUG MODE")
    logger.info("=" * 80)
    
    # Log all parameters
    logger.info("\nCONFIGURATION PARAMETERS:")
    config_dict = vars(args)
    for key, value in config_dict.items():
        logger.info(f"  {key}: {value}")
    
    # Log file path
    logger.info(f"\nLog file: {log_file}")
    
    # Check data directory
    logger.info(f"\nCHECKING DATA DIRECTORY: {args.datadir}")
    data_path = os.path.join(args.datadir, args.dataset)
    if os.path.exists(data_path):
        logger.info(f"Found: {data_path}")
        files = os.listdir(data_path)
        logger.info(f"  Files ({len(files)}):")
        for f in sorted(files)[:10]:  # Show first 10 files
            logger.info(f"    - {f}")
        if len(files) > 10:
            logger.info(f"    ... and {len(files) - 10} more files")
    else:
        logger.warning(f"NOT FOUND: {data_path}")
    
    # Check output directory
    logger.info(f"\nOUTPUT DIRECTORY: {args.folder}")
    os.makedirs(args.folder, exist_ok=True)
    logger.info(f"Output directory created/verified")
    
    # Import MBA modules with error handling
    logger.info("\nIMPORTING MBA MODULES...")
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "MBA"))
        
        logger.info("  Importing utils...")
        from utils import set_seed
        
        logger.info("  Importing datasets...")
        from datasets import MultiDataset, train_collate_fn
        
        logger.info("  Importing data_utils...")
        from data_utils import create_adj_mat, load_all, load_pretrain
        
        logger.info("  Importing models...")
        from model import MF
        from LightGCN import LightGCN
        
        logger.info("  Importing train module...")
        from train import TrainModel
        
        logger.info("  Importing evaluate...")
        import evaluate
        
        logger.info("All modules imported successfully!")
        
    except ImportError as e:
        logger.error(f"Failed to import modules: {e}")
        raise
    
    # Now run the actual training
    logger.info("\n" + "=" * 80)
    logger.info("STARTING TRAINING PIPELINE")
    logger.info("=" * 80)
    
    # Create parameter dict for original main function
    param = {
        'datadir': args.datadir,
        'folder': args.folder,
        'dataset': args.dataset,
        'train_method': args.train_method,
        'model': args.model,
        'pretrain_model': args.pretrain_model,
        'lambda0': args.lambda0,
        'lambda1': args.lambda1,
        'pretrain_early_stop_rounds': args.pretrain_early_stop_rounds,
        'idx': args.idx,
        'seed': args.seed,
        'batch_size': args.batch_size,
        'emb_dim': args.emb_dim,
        'num_layers': args.num_layers,
        'dropout': args.dropout,
        'device': args.device,
        'test_only': args.test_only,
    }
    
    logger.info(f"\nPIPELINE STAGES:")
    logger.info(f"  1. Prepare dataset and load data")
    logger.info(f"  2. Create adjacency matrices")
    logger.info(f"  3. Initialize models")
    logger.info(f"  4. Train/Evaluate based on method: {args.train_method}")
    
    try:
        # Stage 1: Load data
        logger.info(f"\n{'='*80}")
        logger.info(f"STAGE 1: LOADING DATA")
        logger.info(f"{'='*80}")
        
        logger.info(f"Loading dataset: {args.dataset} from {data_path}")
        
        set_seed(param['seed'])
        import torch
        import torch.backends.cudnn as cudnn
        import numpy as np
        
        cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True
        
        if param['train_method'] == "pre":
            logger.info(f"Loading pretrain data...")
            user_num, item_num, \
            train_mat_pv, train_mat_buy, \
            user_pos_dict_pv, user_pos_dict_buy, \
            train_data_dict_pv, train_data_dict_buy, \
            test_data_dict_pv, test_data_dict_buy = load_pretrain(data_path, param['dataset'])
            logger.info(f"Pretrain data loaded")
        else:
            logger.info(f"Loading full data...")
            user_num, item_num, \
            train_mat_pv, train_mat_buy, \
            user_pos_dict_pv, user_pos_dict_buy, \
            train_data_dict_pv, train_data_dict_buy, \
            test_data_dict_buy = load_all(data_path, param['dataset'])
            logger.info(f"Full data loaded")
        
        logger.info(f"\nDataset Statistics:")
        logger.info(f"  Users: {user_num}")
        logger.info(f"  Items: {item_num}")
        logger.info(f"  Train PV density: {train_mat_pv.nnz / (user_num * item_num) * 100:.4f}%")
        logger.info(f"  Train BUY density: {train_mat_buy.nnz / (user_num * item_num) * 100:.4f}%")
        
        # Stage 2: Create datasets and loaders
        logger.info(f"\n{'='*80}")
        logger.info(f"STAGE 2: CREATING TRAINING DATASET")
        logger.info(f"{'='*80}")
        
        train_dataset = MultiDataset(user_num=user_num, item_num=item_num,
                                     train_mat_pv=train_mat_pv, train_mat_buy=train_mat_buy,
                                     user_pos_dict_pv=user_pos_dict_pv, user_pos_dict_buy=user_pos_dict_buy,
                                     train_data_dict_pv=train_data_dict_pv, train_data_dict_buy=train_data_dict_buy,
                                     is_pretrain=(param['train_method'] == "pre"))
        
        import torch.utils.data as data
        train_loader = data.DataLoader(train_dataset, batch_size=param.get('batch_size', 2048),
                                       shuffle=True, num_workers=0, pin_memory=True,
                                       collate_fn=train_collate_fn)
        
        logger.info(f"Dataset created")
        logger.info(f"  Batch size: {param.get('batch_size', 2048)}")
        logger.info(f"  Total batches: {len(train_loader)}")
        
        # Stage 3: Create models
        logger.info(f"\n{'='*80}")
        logger.info(f"STAGE 3: INITIALIZING MODELS")
        logger.info(f"{'='*80}")
        
        logger.info(f"Model type: {param['pretrain_model']}")
        logger.info(f"Embedding dim: {param['emb_dim']}")
        
        # Load adjacency matrices
        logger.info(f"\nLoading/Creating adjacency matrices...")
        try:
            import scipy.sparse as sp
            norm_adj_buy = sp.load_npz(data_path + param['dataset'] + '_s_pre_adj_mat_buy.npz')
            norm_adj_pv = sp.load_npz(data_path + param['dataset'] + '_s_pre_adj_mat_pv.npz')
            logger.info(f"Loaded pre-computed adjacency matrices")
        except:
            logger.info(f"Creating adjacency matrices...")
            norm_adj_buy = create_adj_mat(train_dataset.train_mat_buy,
                                          train_dataset.user_num, train_dataset.item_num,
                                          data_path, dataset=param['dataset'], mode="buy")
            norm_adj_pv = create_adj_mat(train_dataset.train_mat_pv,
                                         train_dataset.user_num, train_dataset.item_num,
                                         data_path, dataset=param['dataset'], mode="pv")
            logger.info(f"Adjacency matrices created")
        
        param['norm_adj_buy'] = norm_adj_buy
        param['norm_adj_pv'] = norm_adj_pv
        
        # Create models
        if param['pretrain_model'] == 'MF':
            logger.info(f"Creating MF (Matrix Factorization) models...")
            model_buy = MF(user_num, item_num, param.get("factor_num", 32))
            model_pv = MF(user_num, item_num, param.get("factor_num", 32))
        elif param['pretrain_model'] == 'lgn':
            logger.info(f"Creating LightGCN models (layers={param['num_layers']})...")
            model_buy = LightGCN(user_num, item_num,
                                norm_adj_buy, latent_dim=param['emb_dim'], n_layers=param['num_layers'],
                                device=param['device'], dropout=param['dropout'])
            model_pv = LightGCN(user_num, item_num,
                               norm_adj_pv, latent_dim=param['emb_dim'], n_layers=param['num_layers'],
                               device=param['device'], dropout=param['dropout'])
        
        logger.info(f"Models initialized")
        logger.info(f"  PV Model parameters: {sum(p.numel() for p in model_pv.parameters()):,}")
        logger.info(f"  BUY Model parameters: {sum(p.numel() for p in model_buy.parameters()):,}")
        
        # Stage 4: Training
        logger.info(f"\n{'='*80}")
        logger.info(f"STAGE 4: TRAINING")
        logger.info(f"{'='*80}")
        
        logger.info(f"Training method: {param['train_method'].upper()}")
        logger.info(f"Lambda0 (regularization): {param['lambda0']}")
        logger.info(f"Early stop rounds: {param['pretrain_early_stop_rounds']}")
        
        train_model = TrainModel(param=param,
                                user_num=user_num, item_num=item_num,
                                train_mat_buy=train_dataset.train_mat_buy,
                                train_mat_pv=train_dataset.train_mat_pv)
        
        logger.info(f"TrainModel initialized")
        
        # Generate model paths
        data_name = param['dataset']
        lambda0_str = str(param['lambda0'])
        idx = param['idx']
        pv_model_path = os.path.join(param['folder'],
                                     f"pretrain_pv_{param['pretrain_model']}_{data_name}_{param['seed']}_{lambda0_str}_{idx}.pt")
        buy_model_path = os.path.join(param['folder'],
                                      f"pretrain_buy_{param['pretrain_model']}_{data_name}_{param['seed']}_{lambda0_str}_{idx}.pt")
        
        logger.info(f"\nModel save paths:")
        logger.info(f"  PV:  {pv_model_path}")
        logger.info(f"  BUY: {buy_model_path}")
        
        if param['train_method'] == "pre":
            logger.info(f"\nPRETRAINING MODE")
            logger.info(f"Training PV (Page View) model...")
            train_model.pretrain(model=model_pv, train_loader=train_loader,
                                train_mode="pv",
                                test_data_pos=test_data_dict_pv, user_pos=user_pos_dict_pv,
                                model_name=param['pretrain_model'],
                                early_stop_rounds=param['pretrain_early_stop_rounds'],
                                model_save_path=pv_model_path)
            
            logger.info(f"\nTraining BUY (Purchase) model...")
            set_seed(param['seed'])
            train_model.pretrain(model=model_buy, train_loader=train_loader,
                                train_mode="buy",
                                test_data_pos=test_data_dict_buy, user_pos=user_pos_dict_buy,
                                model_name=param['pretrain_model'],
                                early_stop_rounds=param['pretrain_early_stop_rounds'],
                                model_save_path=buy_model_path)
            
            logger.info(f"\nPRETRAINING COMPLETE")
            logger.info(f"Models saved to {param['folder']}")
        
        logger.info(f"\n{'='*80}")
        logger.info(f"TRAINING FINISHED SUCCESSFULLY")
        logger.info(f"{'='*80}")
        
    except Exception as e:
        logger.error(f"ERROR DURING TRAINING: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    main()
