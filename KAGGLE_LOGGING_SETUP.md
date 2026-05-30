# Kaggle - Make MBA Not a Black Box

## Vấn đề
Chạy trên Kaggle, code MBA cố định → không thấy gì, không biết chạy đến đâu.

## Giải Pháp
Thêm logging trực tiếp vào code MBA, rồi upload lên Kaggle.

---

## 📋 Step-by-Step

### Step 1: Thêm Logging Vào Code MBA

**Option A: Auto (dễ nhất)**
```bash
cd /home/haiphong0132/mining-on-massive-datasets-ptit-project
python add_logging_to_mba.py
```

Xong! Tự động thêm logging vào:
- `MBA/main.py` - Dataset stats
- `MBA/train.py` - Training progress

**Option B: Manual (nếu auto không được)**

Xem file: [KAGGLE_LOGGING_GUIDE.md](KAGGLE_LOGGING_GUIDE.md) - Copy & paste code

### Step 2: Update Your Kaggle Dataset

**Option A: Update existing `rs-mba` dataset (Recommended)**
```bash
# Upload modified MBA files to your existing rs-mba dataset
# Go to https://kaggle.com/datasets/hngphongkiu/rs-mba/edit
# Delete old MBA files
# Upload new modified MBA files
# Or use Kaggle API to update version
```

**Option B: Create new dataset**
```bash
# If you want to keep original
zip -r mba_with_logging.zip MBA/
# Upload to https://kaggle.com/settings/datasets
# Create new dataset name: mba-with-logging
```

### Step 3: Use in Kaggle Notebook

**Option A: Using existing `rs-mba` dataset (Recommended - Same command!)**
```python
import os

# Cell 1: Run training (same command as before, but MBA has logging now)
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

**Option B: Using new dataset**
```python
import os

# Cell 1: Run training with new dataset path
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

### Step 4: Monitor Training

**In Kaggle Notebook:**

```python
# View live logs
!tail -f /kaggle/working/output/training_*.log

# View just metrics
!grep "Recall\|NDCG\|Epoch" /kaggle/working/output/training_*.log

# Check training progress
import os
logs = os.listdir('/kaggle/working/output/')
print(f"Files created: {logs}")
```

---

## 🎯 What Logging Shows

### Before (Black Box):
```
(Nothing happens for hours...)
```

### After (With Logging):
```
2024-04-16 10:30:45,123 - INFO - ================================================================================
2024-04-16 10:30:45,124 - INFO - MBA RECOMMENDER SYSTEM - KAGGLE TRAINING
2024-04-16 10:30:45,125 - INFO - ================================================================================

2024-04-16 10:31:02,456 - INFO - Dataset Statistics:
2024-04-16 10:31:02,457 - INFO -   Users: 1000000
2024-04-16 10:31:02,458 - INFO -   Items: 100000
2024-04-16 10:31:02,459 - INFO -   PV interactions: 40000000
2024-04-16 10:31:02,460 - INFO -   BUY interactions: 10000000

2024-04-16 10:35:12,789 - INFO - ================================================================================
2024-04-16 10:35:12,790 - INFO - TRAINING PV MODEL
2024-04-16 10:35:12,791 - INFO - ================================================================================

2024-04-16 10:38:45,123 - INFO - Epoch 1: Recall@100=0.7250, NDCG@20=0.4125
2024-04-16 10:42:10,456 - INFO - Epoch 2: Recall@100=0.7845, NDCG@20=0.4512
2024-04-16 10:45:35,789 - INFO - Epoch 3: Recall@100=0.8120, NDCG@20=0.4820
...
2024-04-16 11:30:00,123 - INFO - Epoch 15: Recall@100=0.8954, NDCG@20=0.5450
2024-04-16 11:30:00,124 - INFO - Early stopping at epoch 15
2024-04-16 11:30:00,125 - INFO - Best Recall@100: 0.8954

2024-04-16 11:30:15,456 - INFO - Saving best model: /kaggle/working/output/pretrain_pv_MF_otto_...

2024-04-16 11:30:30,789 - INFO - TRAINING BUY MODEL
...
```

**Bây giờ bạn biết chắc:**
- ✓ Training đã start
- ✓ Dataset load xong
- ✓ Mỗi epoch tiến độ
- ✓ Early stop khi nào
- ✓ Model save ở đâu

---

## 📊 Expected Output Files

Sau khi chạy trên Kaggle:
```
/kaggle/working/output/
├── training_20240416_103045.log     <- Detailed log file
├── pretrain_pv_MF_otto_0_0.0001_0.pt
├── pretrain_buy_MF_otto_0_0.0001_0.pt
└── ...
```

---

## ⚠️ Notes

1. **Logging không làm thay đổi model**
   - Chỉ thêm print statements
   - Training logic không đổi
   - Results sẽ giống hệt

2. **Có thể revert bất kỳ lúc nào**
   ```bash
   cp MBA/main.py.backup_logging MBA/main.py
   cp MBA/train.py.backup_logging MBA/train.py
   ```

3. **Log file được lưu** ở `/kaggle/working/output/training_*.log`
   - Tự động tạo tên theo timestamp
   - Chi tiết đầy đủ

4. **Validation frequency** có thể optimize (optional)
   ```python
   # Để nhanh hơn, validate mỗi 5 epochs thay vì mỗi epoch
   if epoch % 5 == 0 or epoch == epochs - 1:
       # Do validation
   ```

---

## 🔄 Workflow

```
1. Chạy add_logging_to_mba.py (locally)
   ↓
2. Upload modified MBA lên Kaggle dataset
   ↓
3. Chạy training trên Kaggle notebook
   ↓
4. Monitor logs in Kaggle (real-time visibility)
   ↓
5. Training không còn black box!
```

---

## ✅ Quick Checklist

- [ ] Run `python add_logging_to_mba.py`
- [ ] Check logs created (grep OPTIMIZATION MBA/main.py)
- [ ] Zip modified MBA folder
- [ ] Upload to Kaggle dataset
- [ ] Use modified code in Kaggle notebook
- [ ] Run training
- [ ] Monitor with `tail -f /kaggle/working/output/training_*.log`
- [ ] ✓ Training visible, not a black box!

---

## 🎯 Summary

| Cái gì | Kết quả |
|-------|---------|
| **Before** | Training chạy im lặng, không biết gì |
| **After** | Console output + Detailed log file |
| **Effort** | 5 phút (auto patch) |
| **Change** | Không đổi model, chỉ thêm logging |
| **Benefit** | **FULL VISIBILITY!** ✅ |

**Ready to make training visible? 🚀**
