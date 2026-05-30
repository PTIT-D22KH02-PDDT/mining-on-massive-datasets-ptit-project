# ⚡ Quick Reference Card - MBA Recommender System

## Your Command Explained

```
python -u main.py \
  --datadir /kaggle/working/data              🗂️  Input data location
  --folder /kaggle/working/output             💾 Where to save trained models
  --dataset otto                              📊 Dataset: otto | beibei | taobao
  --train_method pre                          🎯 Training phase: pre | mba
  --model MF                                  🧠 Final model: MF | lgn
  --pretrain_model MF                         🧠 Pretrain model: MF | lgn
  --lambda0 1e-4                              🎚️  Regularization (lower=stronger)
  --pretrain_early_stop_rounds 20             ⏹️  Stop if no progress for 20 checks
  --idx 0                                     🔢 Experiment ID for tracking
```

---

## 🔄 Pipeline Stages

```
┌─────────────────────────────────────────┐
│  STAGE 1: LOAD DATA                      │
│  ├─ Read user × item matrices             │
│  ├─ Split into train/test                 │
│  └─ Count: Users, Items, Interactions    │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│  STAGE 2: CREATE DATASET                │
│  ├─ For each epoch: positive/negative     │
│  ├─ Batch size: 2048 samples              │
│  └─ DataLoader ready for GPU              │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│  STAGE 3: INITIALIZE MODELS             │
│  ├─ User embeddings: 32-dim               │
│  ├─ Item embeddings: 32-dim               │
│  └─ Total params: ~3.2M                  │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│  STAGE 4: TRAIN                         │
│  ├─ 100+ epochs of training               │
│  ├─ Validate every batch                  │
│  ├─ Early stop @ 20 no-progress rounds    │
│  └─ Save best model                       │
└─────────────────────────────────────────┘
```

---

## 📊 Dataset Statistics (Expected for OTTO)

```
Users:        1,000,000
Items:        100,000
Train PV:     40,000,000 interactions  (density: 0.04%)
Train BUY:    10,000,000 interactions  (density: 0.01%)
Test samples: 100,000 users
Sparsity:     99.95%
```

---

## 🎯 Two Models Trained Separately

```
Model 1: PV (Page View Predictor)     Model 2: BUY (Purchase Predictor)
├─ Predicts what user will VIEW       ├─ Predicts what user will BUY
├─ More data (clicks)                 ├─ Less data (actual purchases)
└─ Easier task                        └─ Harder task
```

---

## ✅ Success Metrics

| Metric | Good | Excellent |
|--------|------|-----------|
| **Recall@20** | > 0.70 | > 0.80 |
| **Recall@100** | > 0.85 | > 0.90 |
| **NDCG@20** | > 0.40 | > 0.50 |

💡 These values mean: "Of top-20 items we recommend, ~70-80% will be purchased by the user"

---

## 🔧 Key Hyperparameters Explained

### `lambda0` (Regularization)
```
lambda0 = 1e-4    👎 Strong regularization → Simpler model, less flexible
lambda0 = 1e-5    👍 Weak regularization → Complex model, more flexible
lambda0 = 1e-6    ⚠️  Very weak → May overfit

Default: 1e-4 (balanced for most datasets)
```

### `batch_size` (Training Speed vs Quality)
```
batch_size = 256      👍 Small → Slower but better accuracy
batch_size = 2048     👎 Large → Faster but may be less accurate
batch_size = 4096     ⚠️  Very large → Risk of GPU OOM error

Default: 2048 (good balance)
```

### `pretrain_early_stop_rounds` (Training Duration)
```
Value = 10    ⏱️  Short training (~30-50 mins)
Value = 20    🕐 Medium training (~1-2 hours)  ← Your setting
Value = 50    🕰️  Long training (~4-8 hours)
```

---

## 📁 Output Files

```
.pt file = PyTorch model (can be loaded with torch.load())

File size: ~100-200 MB per model
├─ Contains: User embeddings + Item embeddings + parameters
└─ Use: Load and predict recommendations on new data
```

---

## 🚀 How to Run

```bash
# Original (no visibility)
cd /kaggle/working
python input/datasets/hngphongkiu/rs-mba/main.py \
  --datadir /kaggle/working/data \
  --dataset otto

# With full visibility (NEW)
cd /home/haiphong0132/mining-on-massive-datasets-ptit-project
python debug_runner.py \
  --datadir /kaggle/working/data \
  --dataset otto
```

---

## 📋 What Gets Logged

```
✓ All parameters being used
✓ Dataset statistics (users, items, density)
✓ Model architecture (layer sizes, parameter count)
✓ Training progress (epoch, loss, recall, NDCG)
✓ Validation metrics every checkpoint
✓ Early stopping trigger
✓ Model save location
✓ Any errors with full traceback

Location: /kaggle/working/output/logs/debug_*.log
```

---

## ⚠️ Common Errors & Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `FileNotFoundError: otto` | Data not in correct location | Check `--datadir` path |
| `CUDA out of memory` | Model too large for GPU | Add `--batch_size 512` |
| `No improvement after X rounds` | Dataset too small | Add `--pretrain_early_stop_rounds 50` |
| `ImportError: No module` | Missing library | `pip install` the missing package |

---

## 💡 Performance Tips

**To see what's happening:**
```bash
python debug_runner.py ... 2>&1 | tee training.log
tail -f training.log
```

**To profile speed:**
```bash
time python debug_runner.py ...
```

**To monitor GPU:**
```bash
nvidia-smi -l 1  # Updates every second
```

**To train faster:**
- Increase `--batch_size` to 4096
- Reduce `--pretrain_early_stop_rounds` to 10
- Use LightGCN with `--num_layers 2`

---

## 📚 Understanding the Output Paths

```
Files will be saved to:
  /kaggle/working/output/pretrain_pv_MF_otto_0_0.0001_0.pt
                         ↑      ↑ ↑   ↑ ↑  ↑        ↑ ↑
                    [mode] [task][model][dataset][seed][lambda][idx]
                      pre=pretrain  MF=model_type  otto=dataset
```

---

## 🎓 Next Steps

1. **Run with debug_runner** to see what happens
2. **Check the logs** to understand bottlenecks
3. **Adjust hyperparameters** based on metrics
4. **Save best models** and use for inference

**You're no longer running a black box! 🎉**
