# Kaggle - Make MBA Visible (Quick Summary)

## Problem
Running on Kaggle with MBA code → Black box, can't see what's happening

## Solution
Add logging to MBA code → Full visibility

---

## ⚡ 3 Steps

### Step 1: Thêm Logging (5 phút)
```bash
cd /home/haiphong0132/mining-on-massive-datasets-ptit-project
python add_logging_to_mba.py
```

Output:
```
[OK] main.py logging
[OK] train.py logging

✓ Logging added to MBA code!
```

### Step 2: Upload to Kaggle
```bash
# Option A: Using Kaggle CLI
kaggle datasets create -p ./MBA -u --dir-mode zip

# Option B: Manual upload
# - Zip MBA folder
# - Upload to https://kaggle.com/settings/datasets
# - Name it: hngphongkiu/mba-with-logging (example)
```

### Step 3: Use in Kaggle Notebook

**Option A: Update existing `rs-mba` dataset (Recommended)**
```python
import os

# Cell 1: Run training (same command as before, but MBA code now has logging)
os.system('''python -u /kaggle/input/datasets/hngphongkiu/rs-mba/main.py \\
  --datadir /kaggle/working/data \\
  --folder /kaggle/working/output \\
  --dataset otto \\
  --train_method pre \\
  --model MF \\
  --pretrain_model MF \\
  --lambda0 1e-4 \\
  --pretrain_early_stop_rounds 20 \\
  --idx 0''')

# Cell 2: View logs
os.system('tail -50 /kaggle/working/output/training_*.log')
```

**Option B: Create new dataset (if you want to keep original)**
```python
import os

# Cell 1: Run training with new dataset
os.system('''python -u /kaggle/input/datasets/hngphongkiu/mba-with-logging/main.py \\
  --datadir /kaggle/working/data \\
  --folder /kaggle/working/output \\
  --dataset otto \\
  --train_method pre \\
  --model MF \\
  --pretrain_model MF \\
  --lambda0 1e-4 \\
  --pretrain_early_stop_rounds 20 \\
  --idx 0''')

# Cell 2: View logs
os.system('tail -50 /kaggle/working/output/training_*.log')
```

---

## 📊 What You'll See

**Before:**
```
(Silent for hours)
```

**After:**
```
2024-04-16 10:30:45 - INFO - MBA RECOMMENDER SYSTEM - KAGGLE TRAINING
2024-04-16 10:31:02 - INFO - Dataset Statistics:
2024-04-16 10:31:02 - INFO -   Users: 1000000
2024-04-16 10:31:02 - INFO -   Items: 100000
2024-04-16 10:31:02 - INFO -   PV interactions: 40000000

2024-04-16 10:35:12 - INFO - TRAINING PV MODEL
2024-04-16 10:38:45 - INFO - Epoch 1: Recall@100=0.7250, NDCG@20=0.4125
2024-04-16 10:42:10 - INFO - Epoch 2: Recall@100=0.7845, NDCG@20=0.4512
2024-04-16 10:45:35 - INFO - Epoch 3: Recall@100=0.8120, NDCG@20=0.4820
...
2024-04-16 11:30:00 - INFO - Early stopping at epoch 15
2024-04-16 11:30:00 - INFO - Best Recall@100: 0.8954
2024-04-16 11:30:15 - INFO - Saving best model...
```

**Bạn biết chắc:**
- ✓ Training chạy hay không
- ✓ Bao lâu hết 1 epoch
- ✓ Accuracy là bao nhiêu
- ✓ Early stop khi nào
- ✓ Model save ở đâu

---

## 📁 Files Created

```
/home/haiphong0132/mining-on-massive-datasets-ptit-project/
├── add_logging_to_mba.py           <- Run this
├── KAGGLE_LOGGING_GUIDE.md         <- Full guide
├── KAGGLE_LOGGING_SETUP.md         <- Step-by-step
└── MBA/ (modified)
    ├── main.py                     <- With logging
    ├── main.py.backup_logging      <- Original
    ├── train.py                    <- With logging
    └── train.py.backup_logging     <- Original
```

---

## ✅ Revert if Needed

```bash
cp MBA/main.py.backup_logging MBA/main.py
cp MBA/train.py.backup_logging MBA/train.py
```

---

## 🎯 TL;DR

1. `python add_logging_to_mba.py` (auto patch)
2. Upload modified `MBA/` to Kaggle
3. Run training as usual
4. See full logs in Kaggle → **NO MORE BLACK BOX!** 🎉

**That's it!**
