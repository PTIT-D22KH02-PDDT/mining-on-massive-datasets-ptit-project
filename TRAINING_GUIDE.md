# MBA Recommender System - What This Code Does

## 🎯 Overview

This is a **recommendation system** for the **OTTO dataset** using **MBA (Multi-task Bidirectional co-training)** approach. It predicts what products users will:
1. **View (PV)** - page view interactions
2. **Buy** - purchase transactions

## 📋 Your Command Breakdown

```bash
python main.py \
  --datadir /kaggle/working/data              # Where dataset files are stored
  --folder /kaggle/working/output             # Where to save trained models
  --dataset otto                              # Which dataset (otto/beibei/taobao)
  --train_method pre                          # Pre-training phase (not fine-tuning)
  --model MF                                  # Final model type
  --pretrain_model MF                         # Pretrain model: Matrix Factorization
  --lambda0 1e-4                              # Regularization strength
  --pretrain_early_stop_rounds 20             # Stop if no improvement for 20 rounds
  --idx 0                                     # Experiment index
```

## 🔄 What Happens (4 Stages)

### Stage 1: 📥 Load Data
```
Dataset Structure:
├── train_mat_pv    : User × Item matrix for page views
├── train_mat_buy   : User × Item matrix for purchases  
├── user_pos_dict_pv: Positive items per user (viewed)
├── user_pos_dict_buy: Positive items per user (bought)
└── test_data       : Evaluation data

Example:
  Users: 1,000,000
  Items: 100,000
  Train density: 0.05% (very sparse, like real e-commerce)
```

### Stage 2: 📊 Create Training Dataset
```
MultiDataset:
  ├── For each epoch, sample:
  │   ├── Positive items (user viewed/bought)
  │   └── Negative items (random items user didn't interact)
  └── Batch size: 2048 samples per batch
  
Total batches = ~488 batches per epoch
```

### Stage 3: 🧠 Initialize Models

**Matrix Factorization (MF):**
```
User embedding (32-dim) × Item embedding (32-dim)ᵀ = Prediction score
```

Alternative models:
- **LightGCN**: Graph-based, uses adjacency matrices to model relationships

### Stage 4: 🚀 Training

**What happens during pretraining:**
```
For each epoch:
  1. For each batch of user-item pairs:
     - Forward pass: predict interaction scores
     - Compute loss: how wrong is prediction vs real data
     - Backward pass: update embeddings
  
  2. Validate on test set every few batches
     - Compute Recall@20, Recall@100, NDCG metrics
     - If no improvement for 20 rounds → STOP (early stopping)
  
  3. Save best model to disk
```

**Two separate models trained:**
1. **PV Model**: Predicts page views (users browse items)
2. **BUY Model**: Predicts purchases (users buy items)

## 📊 Output Files Created

```
/kaggle/working/output/
├── pretrain_pv_MF_otto_0_0.0001_0.pt   # Trained PV model
├── pretrain_buy_MF_otto_0_0.0001_0.pt  # Trained BUY model
└── logs/
    └── debug_*.log                       # Detailed training logs
```

## ⚙️ Key Hyperparameters

| Parameter | Value | Meaning |
|-----------|-------|---------|
| `lambda0` | 1e-4 | Regularization - prevents overfitting |
| `pretrain_early_stop_rounds` | 20 | Stop if validation doesn't improve for 20 checks |
| `batch_size` | 2048 | Process 2048 samples at a time |
| `seed` | 0 | Random seed for reproducibility |
| `emb_dim` | 64 | Embedding dimension (for LightGCN) |
| `factor_num` | 32 | Embedding dimension (for MF) |

## 📈 Training Metrics

**Recall@K**: Of top-K predictions, how many are actually purchased/viewed?
```
Recall@20 = 0.8500  →  85% accuracy in top-20 recommendations
Recall@100 = 0.9200 →  92% accuracy in top-100 recommendations
```

**NDCG** (Normalized Discounted Cumulative Gain): Ranks matters!
```
Correct item at rank 1 = better than correct item at rank 10
```

## 🔧 How to Debug / See Details

Use the new **debug runner**:
```bash
cd /home/haiphong0132/mining-on-massive-datasets-ptit-project
python debug_runner.py \
  --datadir /kaggle/working/data \
  --folder /kaggle/working/output \
  --dataset otto \
  --train_method pre \
  --model MF \
  --pretrain_model MF \
  --lambda0 1e-4 \
  --pretrain_early_stop_rounds 20 \
  --idx 0
```

This will:
✅ Show all parameters being used
✅ Check if data files exist
✅ Display dataset statistics
✅ Log each training stage with progress
✅ Save detailed log file: `output/logs/debug_YYYYMMDD_HHMMSS.log`

## 📁 Data Format Expected

```
/kaggle/working/data/otto/
├── train_sessions.parquet       # Columns: session_id, product_id, event_type, timestamp
├── valid_inputs.parquet
├── valid_labels.parquet
├── test.parquet
└── (and other format files)
```

## 🎓 What "Pre" vs "MBA" Mean

- **`--train_method pre`**: Train two separate models (PV and BUY) independently
- **`--train_method mba`**: Fine-tune models using MBA co-training (needs pre-trained models first)

## ✅ Success Indicators

Look for in logs:
```
✅ All modules imported successfully!
✓ Pretrain data loaded
✓ Dataset created
✓ Models initialized
✓ Training complete
✅ PRETRAINING COMPLETE
```

## ❌ Common Issues

| Problem | Solution |
|---------|----------|
| `FileNotFoundError: dataset not found` | Check `--datadir` path |
| `CUDA out of memory` | Reduce `--batch_size` (default 2048 → try 512) |
| `Early stopping triggers immediately` | Dataset might be too small, increase `--pretrain_early_stop_rounds` |
| `GPU not detected` | Add `--device cpu` to run on CPU instead |

---

**💡 TL;DR**: This trains ML models to predict what products users will view and buy, using real e-commerce data. The debug runner helps you see exactly what's happening at each step.
