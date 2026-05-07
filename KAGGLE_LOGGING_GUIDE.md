"""
HOW TO ADD LOGGING TO MBA CODE ON KAGGLE

Since you can't use debug_runner.py on Kaggle and MBA code is fixed,
add logging directly to MBA source files.

This makes training visible without changing logic or models.
"""

# ==============================================================================
# STEP 1: Add logging to MBA/main.py
# ==============================================================================

# At the top of main.py, add:
"""
import logging
from datetime import datetime

# Setup logging
log_file = f"/kaggle/working/training_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger()

logger.info("="*80)
logger.info("MBA TRAINING STARTED")
logger.info("="*80)
"""

# Then in main() function, after loading parameters:
"""
logger.info("\\nConfiguration:")
logger.info(f"  dataset: {param['dataset']}")
logger.info(f"  train_method: {param['train_method']}")
logger.info(f"  model: {param['model']}")
logger.info(f"  batch_size: {param.get('batch_size', 2048)}")
logger.info(f"  lambda0: {param['lambda0']}")
logger.info(f"  epochs: {param['epochs']}")
logger.info(f"  device: {param['device']}")
logger.info("")
"""

# ==============================================================================
# STEP 2: Add logging to data loading (in main.py after loading data)
# ==============================================================================

"""
logger.info("="*80)
logger.info("STAGE 1: LOADING DATA")
logger.info("="*80)
logger.info(f"Dataset: Users={user_num}, Items={item_num}")
logger.info(f"Train PV interactions: {train_mat_pv.nnz}")
logger.info(f"Train BUY interactions: {train_mat_buy.nnz}")
logger.info(f"PV density: {train_mat_pv.nnz / (user_num * item_num) * 100:.4f}%")
logger.info(f"BUY density: {train_mat_buy.nnz / (user_num * item_num) * 100:.4f}%")
logger.info(f"Data loaded successfully\\n")
"""

# ==============================================================================
# STEP 3: Add logging to training (in MBA/train.py, pretrain method)
# ==============================================================================

# In pretrain() method, after setup, add:
"""
logger.info("="*80)
logger.info(f"STAGE 2: TRAINING {train_mode.upper()} MODEL")
logger.info("="*80)
logger.info(f"Model: {model_name}")
logger.info(f"Early stop rounds: {early_stop_rounds}")
logger.info(f"Learning rate: {self.lr}")
logger.info("")
"""

# In the epoch loop, add:
"""
for epoch in range(epochs):
    model.train()
    # ... training code ...
    
    # Add logging every epoch
    if epoch % 1 == 0:
        logger.info(f"Epoch {epoch+1}/{epochs}: Training...")
    
    # Add checkpoint
    if (epoch + 1) % 10 == 0:
        checkpoint_path = os.path.join(self.param['folder'], 
                                      f"checkpoint_{train_mode}_epoch{epoch+1}.pt")
        torch.save(model.state_dict(), checkpoint_path)
        logger.info(f"Checkpoint saved: {checkpoint_path}")
"""

# In validation section, add:
"""
logger.info(f"Epoch {epoch}: Recall@100={recall[-1]:.4f}, NDCG@20={NDCG[0]:.4f}")

if should_stop:
    logger.info(f"Early stopping at epoch {epoch}")
    logger.info(f"Best performance: Recall@100={cur_best_pre_0:.4f}")
"""

# ==============================================================================
# STEP 4: Add logging to evaluate.py
# ==============================================================================

# At start of test_all_users(), add:
"""
import logging
logger = logging.getLogger()
logger.info(f"Evaluating on {len(test_data_pos)} test users...")
"""

# ==============================================================================
# STEP 5: Add logging to data_utils.py
# ==============================================================================

# In load_pretrain() function, add:
"""
import logging
logger = logging.getLogger()
logger.info("Loading training data...")
logger.info(f"Train PV file: {train_pv}")
logger.info(f"Train BUY file: {train_buy}")
"""

# ==============================================================================
# COMPLETE EXAMPLE - Modified main.py section
# ==============================================================================

MAIN_PY_EXAMPLE = """
import argparse
import os
import logging
from datetime import datetime

# ===== ADD LOGGING SETUP =====
def setup_logging(output_folder):
    os.makedirs(output_folder, exist_ok=True)
    log_file = os.path.join(output_folder, f"training_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger()
    return logger, log_file

def main(param):
    # ===== START LOGGING =====
    logger, log_file = setup_logging(param['folder'])
    logger.info("="*80)
    logger.info("MBA RECOMMENDER SYSTEM - TRAINING START")
    logger.info("="*80)
    
    # ===== LOG CONFIGURATION =====
    logger.info("\\nCONFIGURATION:")
    logger.info(f"  Dataset: {param['dataset']}")
    logger.info(f"  Training method: {param['train_method']}")
    logger.info(f"  Model: {param['model']}")
    logger.info(f"  Pretrain model: {param['pretrain_model']}")
    logger.info(f"  Batch size: {param.get('batch_size', 2048)}")
    logger.info(f"  Learning rate: {param.get('lr', 0.001)}")
    logger.info(f"  Lambda0: {param['lambda0']}")
    logger.info(f"  Epochs: {param['epochs']}")
    logger.info(f"  Device: {param['device']}")
    logger.info(f"  Log file: {log_file}")
    
    # ... rest of code ...
    
    logger.info("\\n" + "="*80)
    logger.info("STAGE 1: LOADING DATA")
    logger.info("="*80)
    
    data_path = f"{param['datadir']}/{param['dataset']}/"
    logger.info(f"Data path: {data_path}")
    
    if param['train_method'] == "pre":
        logger.info("Loading pretrain data...")
        user_num, item_num, \\
        train_mat_pv, train_mat_buy, \\
        user_pos_dict_pv, user_pos_dict_buy, \\
        train_data_dict_pv, train_data_dict_buy, \\
        test_data_dict_pv, test_data_dict_buy = load_pretrain(data_path, param['dataset'])
    else:
        logger.info("Loading full data...")
        user_num, item_num, \\
        train_mat_pv, train_mat_buy, \\
        user_pos_dict_pv, user_pos_dict_buy, \\
        train_data_dict_pv, train_data_dict_buy, \\
        test_data_dict_buy = load_all(data_path, param['dataset'])
    
    logger.info(f"\\nDataset Statistics:")
    logger.info(f"  Users: {user_num}")
    logger.info(f"  Items: {item_num}")
    logger.info(f"  Train PV interactions: {train_mat_pv.nnz}")
    logger.info(f"  Train BUY interactions: {train_mat_buy.nnz}")
    logger.info(f"  PV density: {train_mat_pv.nnz / (user_num * item_num) * 100:.4f}%")
    logger.info(f"  BUY density: {train_mat_buy.nnz / (user_num * item_num) * 100:.4f}%")
    
    # ... continue with rest of code ...

if __name__ == "__main__":
    main(param)
"""

# ==============================================================================
# MODIFIED train.py SECTION - pretrain method
# ==============================================================================

TRAIN_PY_EXAMPLE = """
def pretrain(self, model, train_loader, train_mode,
             test_data_pos, user_pos,
             model_name, early_stop_rounds, model_save_path=None):
    
    import logging
    logger = logging.getLogger()
    
    logger.info("="*80)
    logger.info(f"STAGE: PRETRAIN {train_mode.upper()} MODEL")
    logger.info("="*80)
    logger.info(f"Model: {model_name}")
    logger.info(f"Learning rate: {self.lr}")
    logger.info(f"Early stop rounds: {early_stop_rounds}")
    logger.info(f"Epochs: {self.param['epochs']}")
    logger.info("")
    
    self.print_pretrain_config(train_mode, model_name, early_stop_rounds)

    count, last_loss = 0, 1e9
    cur_best_pre_0 = 0.
    stopping_step = 0
    epochs = self.param['epochs']
    rec_loger, ndcg_loger = [], []

    pretrain_model_optim = optim.Adam(model.parameters(), lr=self.lr)
    model.to(self.device)
    
    for epoch in range(epochs):
        model.train()

        train_loader.dataset.train_mode = train_mode
        for uid, pos_pv, pos_buy in train_loader:
            if train_mode == "pv":
                pos = pos_pv
            else:
                pos = pos_buy
            pretrain_model_optim.zero_grad()
            uid, pos = uid.squeeze(1), pos.squeeze(1)
            uid, pos = uid.to(self.device), pos.to(self.device)
            pos_prediction_logits, neg_prediction_logits, neg_item = \\
                self.forward(model, uid, pos, self.NSR, source=train_mode)

            loss = bpr_loss(pos_prediction_logits, neg_prediction_logits)

            reg_loss = 0
            for param in model.parameters():
                reg_loss += param.norm(2).pow(2)

            reg_loss = 1 / 2 * reg_loss / float(self.user_num)

            loss += reg_loss * self.param['lambda0']
            loss.backward()

            pretrain_model_optim.step()

            if count % 200 == 0 and count != 0:
                logger.info(f"Epoch {epoch+1}/{epochs}: Batch {count}, Loss={loss:.4f}")
            count += 1

        logger.info(f"\\nEpoch {epoch+1}/{epochs}: Validation...")
        print("################### PRETRAIN TEST ######################")
        recall, NDCG = evaluate.test_all_users(model, 4096, test_data_pos, user_pos, self.top_k, device=self.device)
        final_perf = "Iter=[%d]\\t recall=[%s], ndcg=[%s]" % \\
                     (epoch,
                      '\\t'.join(['%.4f' % r for r in recall]),
                      '\\t'.join(['%.4f' % r for r in NDCG]))
        print(final_perf)
        logger.info(f"Results: Recall@100={recall[-1]:.4f}, NDCG@20={NDCG[0]:.4f}")

        rec_loger.append(recall)
        ndcg_loger.append(NDCG)

        cur_best_pre_0, stopping_step, should_stop = early_stopping(recall[-1],
                                                                    cur_best_pre_0,
                                                                    stopping_step, expected_order='acc',
                                                                    early_stop_rounds=early_stop_rounds)
        if should_stop:
            logger.info(f"Early stopping triggered at epoch {epoch+1}")
            logger.info(f"Best Recall@100: {cur_best_pre_0:.4f}")
            break

        if cur_best_pre_0 == recall[-1]:
            if model_save_path is None:
                model_save_path = os.path.join(self.param['folder'], 
                                              f"pretrain_{train_mode}_{model_name}_{self.param['dataset']}_{self.seed}_{str(self.param['lambda0'])}.pt")
            logger.info(f"Saving best model to: {model_save_path}")
            torch.save(model.state_dict(), model_save_path)

    recs = np.array(rec_loger)
    ndcgs = np.array(ndcg_loger)

    best_rec_0 = max(recs[:, -1])
    best_idx = list(recs[:, -1]).index(best_rec_0)

    final_perf = "Best Iter=[%d]\\t recall=[%s], ndcg=[%s]" % \\
                 (best_idx,
                  '\\t'.join(['%.5f' % r for r in recs[best_idx]]),
                  '\\t'.join(['%.5f' % r for r in ndcgs[best_idx]]))
    print(final_perf)
    logger.info(f"\\nTraining Complete: {final_perf}")
"""

# ==============================================================================
# USAGE ON KAGGLE
# ==============================================================================

KAGGLE_USAGE = """
On Kaggle Notebook or Kaggle script:

%%bash
cd /kaggle/input/datasets/hngphongkiu/rs-mba/

# After adding logging to main.py, train.py, etc:
python main.py \\
  --datadir /kaggle/working/data \\
  --folder /kaggle/working/output \\
  --dataset otto \\
  --train_method pre \\
  --model MF \\
  --pretrain_model MF \\
  --lambda0 1e-4 \\
  --pretrain_early_stop_rounds 20 \\
  --idx 0

# Output will show:
# - Progress in console
# - Detailed log in /kaggle/working/output/training_YYYYMMDD_HHMMSS.log

# To view logs:
!tail -100 /kaggle/working/output/training_*.log
"""
