# 🎯 Transparency Package - Understanding Your MBA Training

## Problem: "Running this code is like running a black box"

This package **makes the training process transparent** by adding:
- ✅ Detailed logging at every stage
- ✅ Parameter validation
- ✅ Data statistics  
- ✅ Progress tracking
- ✅ Error reporting

---

## 📦 What's Included

### 1. **debug_runner.py** ← USE THIS
Main wrapper script that adds transparency to training.

**Features:**
- Logs all parameters to console AND file
- Validates data directory exists
- Shows dataset statistics (users, items, sparsity)
- Tracks all 4 training stages
- Saves detailed log file: `output/logs/debug_YYYYMMDD_HHMMSS.log`

**Usage:**
```bash
python debug_runner.py \
  --datadir /kaggle/working/data \
  --dataset otto \
  --train_method pre
```

### 2. **TRAINING_GUIDE.md** ← Read this first
Complete explanation of what the code does.

**Contents:**
- 📋 Command breakdown
- 🔄 4-stage pipeline explanation
- 📊 Dataset structure
- 📈 Training metrics explained
- 🔧 Hyperparameters explained
- ❌ Common issues & solutions

### 3. **QUICK_REFERENCE.md** ← Bookmark this
Visual one-page reference card.

**Contents:**
- ⚡ Your command explained line-by-line
- 🔄 Pipeline flow diagram
- 📊 Expected dataset stats
- 📋 Hyperparameter guide
- 🚀 How to run
- ⚠️ Common errors & fixes

### 4. **run_commands.sh** ← Copy & paste commands
Pre-built commands for common scenarios.

**Examples:**
- Your original command (with debug)
- LightGCN model training
- Quick CPU test run
- Different hyperparameters
- Different datasets

### 5. **This file** 
Package overview & how to use everything.

---

## 🚀 Quick Start (3 steps)

### Step 1: Read the overview
```bash
cat QUICK_REFERENCE.md  # 2-minute read
```

### Step 2: Run with debug visibility
```bash
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

### Step 3: Monitor in real-time
```bash
tail -f /kaggle/working/output/logs/debug_*.log
```

---

## 📊 What You'll See

```
INFO - ================================================================================
INFO - MBA RECOMMENDER SYSTEM - DEBUG MODE
INFO - ================================================================================
INFO - 📋 CONFIGURATION PARAMETERS:
INFO -   datadir: /kaggle/working/data
INFO -   dataset: otto
INFO -   batch_size: 2048
INFO -   ...
INFO - 
INFO - 🔍 CHECKING DATA DIRECTORY: /kaggle/working/data
INFO - ✓ Found: /kaggle/working/data/otto
INFO - Files (15):
INFO -   - train_sessions.parquet
INFO -   - valid_labels.parquet
INFO -   ...
INFO - 
INFO - ================================================================================
INFO - STAGE 1: LOADING DATA
INFO - ================================================================================
INFO - Loading dataset: otto from /kaggle/working/data/otto
INFO - Loading pretrain data...
INFO - ✓ Pretrain data loaded
INFO - 
INFO - 📈 Dataset Statistics:
INFO -   Users: 1000000
INFO -   Items: 100000
INFO -   Train PV density: 0.0412%
INFO -   Train BUY density: 0.0098%
...
```

---

## 🎓 Understanding What Each File Does

### Your Command Parameters

```
--datadir /kaggle/working/data
  └─ Where the dataset files are stored
     Usually: OTTO parquet files

--dataset otto
  └─ Which dataset to use (otto | beibei | taobao)
     Determines which parquet files to load

--train_method pre
  └─ "pre" = pretraining (train two separate models)
     "mba" = fine-tuning with MBA co-training

--model MF
  └─ Final model type (not used in pretraining stage)
     "MF" = Matrix Factorization
     "lgn" = LightGCN (graph-based)

--pretrain_model MF
  └─ Model to use during pretraining
     Same options as --model

--lambda0 1e-4
  └─ Regularization strength
     Prevents overfitting to training data
     Smaller = more regularization

--pretrain_early_stop_rounds 20
  └─ Stop training if validation doesn't improve for 20 checks
     Prevents overfitting and saves time

--idx 0
  └─ Experiment index for tracking different runs
```

### Pipeline Overview

```
1. LOAD DATA
   ├─ Read parquet files
   ├─ Create train/test split
   └─ Calculate sparsity

2. CREATE DATASET
   ├─ Sample positive items (user interacted)
   ├─ Sample negative items (user didn't interact)
   └─ Create batches for training

3. INITIALIZE MODELS
   ├─ Create embeddings (user & item)
   ├─ Set up loss functions
   └─ Move to GPU if available

4. TRAIN
   ├─ Forward pass: predict interaction scores
   ├─ Compute loss
   ├─ Backward pass: update embeddings
   ├─ Validate on test set
   └─ Save best model
```

---

## 🔍 How to Debug Issues

### Issue: "What parameters was it using?"
**Solution:** Look at the logs
```bash
grep "CONFIGURATION PARAMETERS" /kaggle/working/output/logs/debug_*.log
```

### Issue: "Did the data load correctly?"
**Solution:** Check dataset statistics in logs
```bash
grep "Dataset Statistics" -A 5 /kaggle/working/output/logs/debug_*.log
```

### Issue: "How many epochs ran?"
**Solution:** Count training updates in logs
```bash
grep "Epoch" /kaggle/working/output/logs/debug_*.log | tail -20
```

### Issue: "What was the final accuracy?"
**Solution:** Look for final metrics
```bash
grep "recall\|NDCG" /kaggle/working/output/logs/debug_*.log | tail -10
```

### Issue: "Where were models saved?"
**Solution:** Check model save paths
```bash
grep ".pt" /kaggle/working/output/logs/debug_*.log
```

---

## ✅ What "Success" Looks Like

```
✅ All modules imported successfully!
✓ Pretrain data loaded
✓ Dataset created
✓ Models initialized  
✓ Training start: PV model
  [Epoch 1/100] Loss: 0.525, Recall@20: 0.745, NDCG@20: 0.412
  [Epoch 2/100] Loss: 0.412, Recall@20: 0.812, NDCG@20: 0.498
  ...
  [Epoch 15/100] Loss: 0.204, Recall@20: 0.854, NDCG@20: 0.541
✓ Early stopping triggered (no improvement for 20 rounds)
✓ Best model saved to: pretrain_pv_MF_otto_0_0.0001_0.pt

✓ Training start: BUY model
  ...
✓ Early stopping triggered
✓ Best model saved to: pretrain_buy_MF_otto_0_0.0001_0.pt

✅ PRETRAINING COMPLETE
```

---

## 📚 Related Files to Check

### Configuration
- [config/config.yml](../config/config.yml) - If using config file

### Original Implementation
- [MBA/main.py](../MBA/main.py) - Original trainer (reference only)
- [MBA/train.py](../MBA/train.py) - Training loop details
- [MBA/model.py](../MBA/model.py) - Model architecture

### Data Processing
- [MBA/data_utils.py](../MBA/data_utils.py) - Data loading functions
- [MBA/datasets.py](../MBA/datasets.py) - Dataset classes

---

## 🎯 Next Steps

1. **Run the debug script** to see full training process
2. **Read QUICK_REFERENCE.md** to understand each parameter
3. **Check the logs** to identify any issues
4. **Adjust hyperparameters** based on metrics
5. **Save best model** paths for later use

---

## 💡 Pro Tips

**Tip 1: Save logs with timestamp**
```bash
python debug_runner.py ... | tee "training_$(date +%Y%m%d_%H%M%S).log"
```

**Tip 2: Watch training in real-time**
```bash
tail -f /kaggle/working/output/logs/debug_*.log | grep -E "Epoch|Loss|Recall"
```

**Tip 3: Compare multiple runs**
```bash
diff debug_run1.log debug_run2.log
```

**Tip 4: Extract metrics for analysis**
```bash
grep "Recall\|NDCG" /kaggle/working/output/logs/debug_*.log > metrics.csv
```

---

## 🆘 Need Help?

| Question | Answer |
|----------|--------|
| **What does this command do?** | See QUICK_REFERENCE.md |
| **How do I run it?** | See run_commands.sh |
| **What are hyperparameters?** | See TRAINING_GUIDE.md |
| **Why is training slow?** | Check QUICK_REFERENCE.md "Performance Tips" |
| **How do I debug errors?** | Check "How to Debug Issues" above |

---

**🎉 You're no longer running a black box!**

The training process is now **transparent, trackable, and debuggable**. Good luck! 🚀
