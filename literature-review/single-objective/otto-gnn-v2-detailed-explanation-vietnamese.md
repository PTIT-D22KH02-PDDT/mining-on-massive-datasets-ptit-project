# Otto GNN Optimized v2 - Giải thích chi tiết dành cho người mới bắt đầu

## Mục lục

1. [Tổng quan về bài toán](#1-tổng-quan-về-bài-toán)
2. [Dữ liệu](#2-dữ-liệu)
3. [So sánh v1 và v2](#3-so-sánh-v1-và-v2)
4. [Kiến trúc model chi tiết](#4-kiến-trúc-model-chi-tiết)
5. [Các cải tiến và ý nghĩa](#5-các-cải-tiến-và-ý-nghĩa)
6. [Quá trình huấn luyện](#6-quá-trình-huấn-luyện)
7. [Đánh giá model](#7-đánh-giá-model)
8. [Các tham số và cách điều chỉnh](#8-các-tham-số-và-cách-điều-chỉnh)
9. [Tổng kết](#9-tổng-kết)

---

## 1. Tổng quan về bài toán

### 1.1 Otto Group là gì?

**Otto Group** là một cuộc thi trên Kaggle về hệ thống khuyến nghị (Recommendation System) do công ty thương mại điện tử Otto (Đức) tổ chức.

### 1.2 Mục tiêu

Dự đoán các sản phẩm mà người dùng sẽ **thêm vào giỏ hàng (cart)** hoặc **đặt hàng (order)** trong phiên mua sắm tiếp theo, dựa trên lịch sử hành vi.

### 1.3 Định dạng bài toán

Với mỗi user (session), ta cần đề xuất **top 20 sản phẩm** có khả năng được thêm vào giỏ hoặc mua.

---

## 2. Dữ liệu

### 2.1 Đường dẫn

| Loại | Đường dẫn |
|------|-----------|
| Train | `/kaggle/input/datasets/cdeotte/otto-validation/train_parquet/*.parquet` |
| Test | `/kaggle/input/datasets/cdeotte/otto-validation/test_parquet/*.parquet` |

### 2.2 Schema

Mỗi file parquet có 4 cột:

| Cột | Kiểu | Mô tả |
|-----|------|-------|
| `session` | Int32 | ID của phiên mua sắm |
| `aid` | Int32 | ID của sản phẩm (article ID) |
| `ts` | Int64 | Timestamp (miliseconds) |
| `type` | String | Loại tương tác: `clicks`, `carts`, `orders` |

### 2.3 Ví dụ dữ liệu

```
session  |  aid    |    ts      |  type
---------|--------|------------|--------
1234567  |  89012  |  1650000000  | clicks
1234567  |  45678  |  1650000015  | carts
1234567  |  12345  |  1650000030  | orders
1234568  |  98765  |  1650000100  | clicks
```

### 2.4 Các loại tương tác

- **Clicks** (nhấp chuột): Người dùng chỉ xem sản phẩm, chưa mua
- **Carts** (giỏ hàng): Người dùng thêm vào giỏ - **mục tiêu chính của cuộc thi!**
- **Orders** (đơn hàng): Người dùng mua sản phẩm

---

## 3. So sánh v1 và v2

### 3.1 Bảng so sánh

| Tính năng | v1 | v2 | Thay đổi |
|-----------|-----|-----|----------|
| **Số GCN Layers** | 4 | **3** | Giảm (theo nghiên cứu) |
| **Learning Rate** | 5e-4 | **1e-3** | Tăng gấp đôi |
| **Epochs** | 50 | **30** | Giảm + early stopping |
| **Session Sample** | 100% | **10%** | Giảm để nhanh hơn |
| **Type Embedding** | ✗ | ✓ | **MỚI** |
| **Learnable Aggregation** | ✗ | ✓ | **MỚI** |
| **Target-Aware Attention** | ✗ | ✓ (option) | **MỚI** |

### 3.2 Tại sao thay đổi?

| Thay đổi | Lý do |
|----------|-------|
| Layers 4→3 | SR-GNN research: T>3 gây over-smoothing |
| LR 5e-4→1e-3 | Học nhanh hơn, vẫn ổn định |
| Epochs 50→30 | Early stopping tránh overfitting |
| Session 100%→10% | Xử lý nhanh hơn, vẫn đủ dữ liệu |
| Type Embedding | Model hiểu được các loại tương tác khác nhau |

---

## 4. Kiến trúc model chi tiết

### 4.1 Multi-Behavior LightGCN

Đây là phiên bản nâng cao của LightGCN với các cải tiến:

```
┌────────────────────────────────────────────────────────────────��────────┐
│                    Multi-Behavior LightGCN v2                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  INPUT:                                                                  │
│  - User-Item Graph (sessions ↔ items)                                    │
│  - Interaction types (clicks/carts/orders)                               │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │ Bước 1: Embedding Layer                                            │ │
│  │   ┌──────────────────────┐   ┌──────────────────────┐            │ │
│  │   │ User/Item Embedding  │   │ Type Embedding (NEW)  │            │ │
│  │   │ (num_nodes × dim)     │   │ (3 × dim)            │            │ │
│  │   └──────────────────────┘   └──────────────────────┘            │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                    ↓                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │ Bước 2: GCN Layers (T=3 bước)                                       │ │
│  │                                                                      │ │
│  │   Layer 0: x^(0) = embedding ban đầu                                 │ │
│  │   Layer 1: x^(1) = GCNConv(x^(0), edges) → thông tin từ 1-hop        │ │
│  │   Layer 2: x^(2) = GCNConv(x^(1), edges) → thông tin từ 2-hops       │ │
│  │   Layer 3: x^(3) = GCNConv(x^(2), edges) → thông tin từ 3-hops       │ │
│  │                                                                      │ │
│  │   Tại sao T=3? (theo SR-GNN research)                                   │ │
│  │   - T < 3: Không lan truyền đủ thông tin                              │ │
│  │   - T > 3: Over-smoothing - các nodes giống nhau quá                   │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                    ↓                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │ Bước 3: Learnable Aggregation (NEW)                                │ │
│  │                                                                      │ │
│  │   weights = softmax(agg_weights)  # Học trọng số từng layer           │ │
│  │   final_emb = Σ w_i × x^(i)  cho i = 0,1,2,3                         │ │
│  │                                                                      │ │
│  │   Thay vì trung bình dơn giản, model tự học trọng số tốt nhất       │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                    ↓                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │ Bước 4: Tách User và Item Embeddings                                  │ │
│  │                                                                      │ │
│  │   final_emb = [user_embeddings | item_embeddings]                   │ │
│  │   user_emb = final_emb[0:num_sessions]                                │ │
│  │   item_emb = final_emb[num_sessions:]                                │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  OUTPUT:                                                                 │
│  - User embeddings (num_sessions × 64)                                   │
│  - Item embeddings (num_items × 64)                                      │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Các thành phần chính

#### 4.2.1 Embedding Layer

```python
self.embedding = nn.Embedding(num_users + num_items, embed_dim)
self.type_embedding = nn.Embedding(3, embed_dim)  # NEW: 3 types
```

- **User/Item embedding**: Vector ngẫu nhiên cho mỗi user và item
- **Type embedding**: Vector riêng cho clicks(0), carts(1), orders(2)

#### 4.2.2 GCN Layers

```python
self.convs = nn.ModuleList([
    GCNConv(embed_dim, embed_dim, cached=False)
    for _ in range(num_layers)  # num_layers = 3
])
```

GCN (Graph Convolutional Network) lan truyền thông tin qua đồ thị:
- Mỗi node cập nhật dựa trên các neighbors
- Thông tin "chảy" qua các cạnh

#### 4.2.3 Learnable Aggregation

```python
self.agg_weights = nn.Parameter(torch.ones(num_layers + 1) / (num_layers + 1))
```

Thay vì lấy trung bình đơn giản, model học trọng số cho mỗi layer.

---

## 5. Các cải tiến và ý nghĩa

### 5.1 Type Embedding (MỚI trong v2)

#### 5.1.1 Vấn đề của v1

Trong v1, tất cả tương tác được xử lý như nhau:
- User click sản phẩm → weight = 1.0
- User thêm vào giỏ → weight = 6.0
- User mua → weight = 3.0

Nhưng model không "hiểu" được sự khác biệt này!

#### 5.1.2 Giải pháp của v2

Thêm **type embedding** - vector riêng cho mỗi loại:

```python
# Model definition
self.type_embedding = nn.Embedding(3, embed_dim)  # 3 types

# Training
type_emb = model.type_embedding(types)  # Lấy embedding theo type
pos_emb = items_emb[pos_items] + type_emb  # Cộng vào item embedding
neg_emb = items_emb[neg_items] + type_emb
```

#### 5.1.3 Ý nghĩa

- **Click** = quan tâm thấp, chỉ xem
- **Cart** = quan tâm cao, sẽ mua (mục tiêu!)
- **Order** = quan tâm trung bình, đã mua

→ Model học được "ý nghĩa" khác nhau của các tương tác!

#### 5.1.4 Minh họa

```
Item A embeddings với type:
- Click(A):   [0.1, 0.2] + type_click[0.1, 0.1] = [0.2, 0.3]
- Cart(A):    [0.1, 0.2] + type_cart[0.8, 0.9]  = [0.9, 1.1]  ← Mạnh!
- Order(A):   [0.1, 0.2] + type_order[0.5, 0.6] = [0.6, 0.8]

→ Cart có "lực" mạnh nhất trong việc học user preference!
```

---

### 5.2 T=3 Layers (TỐI ƯU)

#### 5.2.1 Nghiên cứu SR-GNN (AAAI 2019)

SR-GNN test các giá trị của T (số GCN layers):

| T (layers) | Recall@20 (Yoochoose) | Recall@20 (Diginetica) |
|-----------|---------------------|----------------------|
| 1 | 0.6923 | 0.4856 |
| 2 | 0.6989 | 0.4934 |
| **3** | **0.7012** | **0.4989** (best) |
| 4 | 0.7008 | 0.4978 |
| 5 | 0.6998 | 0.4967 |

#### 5.2.2 Over-smoothing

Khi T quá lớn, tất cả nodes trở nên **giống nhau** vì thông tin lan truyền qua quá nhiều bước.

```
T=1: Node A ≠ Node B ≠ Node C  (khác biệt)
T=3: Node A ≈ Node B ≈ Node C   (over-smoothing!)
T=5: Node A ≈ Node B ≈ Node C   (quá giống)
```

→ **T=3 là điểm cân bằng** giữa lan truyền đủ thông tin và tránh over-smoothing!

---

### 5.3 Learnable Aggregation (MỚI trong v2)

#### 5.3.1 Vấn đề của trung bình đơn giản

Trong v1, các layer được tổng hợp bằng trung bình:

```python
final_emb = (emb_0 + emb_1 + emb_2 + emb_3) / 4
```

Tất cả layer có **trọng số bằng nhau** = 0.25

#### 5.3.2 Giải pháp

Học trọng số từ dữ liệu:

```python
self.agg_weights = nn.Parameter(torch.ones(4) / 4)  # [0.25, 0.25, 0.25, 0.25]

# Trong forward:
weights = F.softmax(self.agg_weights)  # [0.2, 0.3, 0.3, 0.2] (ví dụ)
final_emb = weights[0]*emb_0 + weights[1]*emb_1 + weights[2]*emb_2 + weights[3]*emb_3
```

#### 5.3.3 Ý nghĩa

- Layer gần (emb_0) có thể quan trọng hơn
- Model tự học trọng số tốt nhất cho dữ liệu này
- Không cần manually điều chỉnh!

---

### 5.4 Higher Learning Rate (1e-3 vs 5e-4)

#### 5.4.1 Lý do tăng LR

- v1 dùng LR thấp (5e-4) → học chậm
- v2 tăng lên 1e-3 → học nhanh gấp đôi
- Kết hợp với early stopping để tránh overfitting

#### 5.4.2 Warmup + Cosine Annealing

```python
def get_lr(epoch):
    if epoch < warmup_epochs:  # 2 epochs
        # Warmup: tăng dần từ 0
        return (epoch + 1) / warmup_epochs
    else:
        # Cosine annealing: giảm dần
        progress = (epoch - warmup_epochs) / (epochs - warmup_epochs)
        return 0.5 * (1 + math.cos(math.pi * progress))
```

**Tại sao?**
- **Warmup**: Cho model "làm quen" với dữ liệu, tránh lr quá cao ban đầu
- **Cosine**: Giảm từ từ → hội tụ ổn định hơn

---

### 5.5 Session Sampling (10% vs 100%)

#### 5.5.1 Vấn đề

Dữ liệu Otto rất lớn:
- ~1.7 triệu sessions
- ~26 triệu tương tác
- Huấn luyện trên 100% mất rất lâu

#### 5.5.2 Giải pháp

Lấy mẫu 10% sessions ngẫu nhiên:

```python
sampled_sessions = all_sessions.sample(
    fraction=0.10,  # 10%
    shuffle=True,
    seed=config.seed
)
```

#### 5.5.3 Ý nghĩa

- Huấn luyện nhanh hơn 10x
- Vẫn đủ dữ liệu để model học tốt
- Giảm overfitting

---

## 6. Quá trình huấn luyện

### 6.1 BPR Loss (Bayesian Personalized Ranking)

```python
def bpr_loss(u_emb, pos_emb, neg_emb):
    pos_scores = torch.sum(u_emb * pos_emb, dim=-1)
    neg_scores = torch.sum(u_emb * neg_emb, dim=-1)
    loss = -torch.mean(F.logsigmoid(pos_scores - neg_scores))
    return loss
```

#### 6.1.1 Ý nghĩa

- **Mục tiêu**: positive items gần user hơn negative items
- **Positive**: Item user đã tương tác (click/cart/order)
- **Negative**: Item user CHƯA tương tác (ngẫu nhiên)
- **Loss nhỏ = Tốt**: pos_scores cao, neg_scores thấp

#### 6.1.2 Minh họa

```
User embedding:    [1.0, 0.5]
Positive item:     [0.9, 0.4] → similarity = 1.0*0.9 + 0.5*0.4 = 1.1
Negative item:    [0.1, 0.2] → similarity = 1.0*0.1 + 0.5*0.2 = 0.2

pos_scores - neg_scores = 1.1 - 0.2 = 0.9 → Loss thấp = Tốt!
```

---

### 6.2 Negative Sampling

```python
def __getitem__(self, idx):
    user_idx, pos_item_idx = self.pairs[idx]
    
    # Sample negative item
    neg_item_idx = random.choice(self.all_items)
    while neg_item_idx in self.user_pos_items.get(user_idx, set()):
        neg_item_idx = random.choice(self.all_items)
    
    return user_idx, pos_item_idx, neg_item_idx
```

- Chọn item **CHƯA** tương tác làm negative
- Tránh "leak" thông tin vào training

---

### 6.3 Training Loop

```python
for epoch in range(epochs):
    # Training
    model.train()
    for users, pos_items, neg_items, types in train_loader:
        # Forward
        users_emb, items_emb = model(edge_index, edge_weight)
        
        # Get type embeddings (NEW)
        type_emb = model.type_embedding(types)
        
        # Add type info
        pos_emb = items_emb[pos_items - num_sessions] + type_emb
        neg_emb = items_emb[neg_items - num_sessions] + type_emb
        
        # Compute loss
        loss = bpr_loss(users_emb[users], pos_emb, neg_emb)
        
        # Backward
        loss.backward()
        optimizer.step()
    
    # Validation
    recall = recall_at_k(users_emb, items_emb, user_pos_dict)
    
    # Early stopping
    if recall > best_recall:
        save_model()
    else:
        patience += 1
        if patience >= early_stopping_patience:
            break
```

---

## 7. Đánh giá model

### 7.1 Recall@20

```
Recall@20 = |{relevant items in top 20}| / |{all relevant items}|
```

**Ví dụ**:
- User có 10 items trong validation set
- Model đề xuất 5 items đúng trong top 20
- Recall@20 = 5/10 = **0.5 (50%)**

### 7.2 NDCG@20 (Normalized Discounted Cumulative Gain)

```
DCG@20 = Σ (rel_i / log2(i+2)) cho i = 1 đến 20
IDCG@20 = Σ (1 / log2(i+2)) cho i = 1 đến min(20, num_relevant)
NDCG@20 = DCG@20 / IDCG@20
```

**Ví dụ**:
- Items đúng ở vi trí 1, 3, 5
- DCG = 1/log2(2) + 1/log2(4) + 1/log2(6) = 1 + 0.5 + 0.39 = 1.89
- IDCG = 1 + 0.5 + 0.39 = 1.89 (nếu có 3 items đúng)
- NDCG = 1.89/1.89 = **1.0** (perfect!)

### 7.3 Target-Aware Attention (Optional)

Từ paper Attention-Enhanced GNN:

```python
def target_aware_attention(self, user_emb, target_items):
    # User representation thay đổi theo target!
    # Mỗi candidate "kích hoạt" interests khác nhau
    target_emb = self.embedding.weight[target_items]
    q = self.target_query(target_emb)
    k = self.target_key(user_emb)
    v = self.target_value(user_emb)
    
    scores = torch.matmul(q, k.T) / math.sqrt(self.embed_dim)
    attn_weights = F.softmax(scores, dim=-1)
    
    context = torch.matmul(attn_weights, v)
    return context
```

**Ý nghĩa**:
- Session: [Áo thun, Quần jean, Đồng hồ]
- Target "Áo khoác" → nhấn mạnh fashion
- Target "Tai nghe" → nhấn mạnh tech

---

## 8. Các tham số và cách điều chỉnh

### 8.1 Tham số hiện tại

| Tham số | Giá trị | Ý nghĩa |
|---------|---------|---------|
| `embed_dim` | 64 | Kích thước vector embedding |
| `num_layers` | 3 | Số GCN layers (tối ưu) |
| `batch_size` | 4096 | Kích thước batch |
| `epochs` | 30 + early stop | Số epochs tối đa |
| `learning_rate` | 1e-3 | Learning rate |
| `session_sample_rate` | 0.10 | % sessions huấn luyện |
| `warmup_epochs` | 2 | Warmup epochs |
| `early_stopping_patience` | 5 | Early stopping |
| `type_weights` | {click:1, cart:6, order:3} | Trọng số edge |

### 8.2 Nếu model overfits

- Giảm `embed_dim` (32 hoặc 48)
- Tăng `weight_decay` (1e-4)
- Giảm `num_layers` (2)
- Tăng dropout (0.2 hoặc 0.3)

### 8.3 Nếu model underfits

- Tăng `embed_dim` (128 hoặc 256)
- Tăng `num_layers` (4)
- Tăng `learning_rate` (5e-3)
- Giảm `weight_decay` (1e-6)

### 8.4 Nếu training quá chậm

- Giảm `session_sample_rate` (0.05)
- Giảm `batch_size` (2048)
- Giảm `embed_dim` (32)

---

## 9. Tổng kết

### 9.1 Các cải tiến so với v1

| Cải tiến | Ý nghĩa |
|-----------|----------|
| **Type Embedding** | Model hiểu click vs cart vs order khác nhau |
| **T=3 Layers** | Tránh over-smoothing (SR-GNN research) |
| **Learnable Aggregation** | Layer weights tự học |
| **Higher LR (1e-3)** | Học nhanh hơn |
| **Session Sample (10%)** | Huấn luyện nhanh |
| **Early Stopping** | Tránh overfitting |

### 9.2 Research papers tham khảo

| Paper | Năm | Đóng góp |
|-------|-----|----------|
| **SR-GNN** | AAAI 2019 | GNN cho session recommendation, T=3 optimal |
| **Attention-Enhanced GNN** | Mathematics 2020 | Target-aware attention |

### 9.3 Kết quả mong đợi

| Metric | v1 | v2 (dự kiến) |
|--------|-----|--------------|
| Recall@20 | ~0.01 | ~0.02+ |
| NDCG@20 | ~0.005 | ~0.01+ |

---

## Phụ lục: Glossary

| Thuật ngữ | Tiếng Việt | Giải thích |
|-----------|-----------|------------|
| **GNN** | Graph Neural Network | Mạng neural hoạt động trên đồ thị |
| **GCN** | Graph Convolutional Network | Loại GNN phổ biến |
| **BPR Loss** | BPR Loss | Loss cho recommendation |
| **Recall@K** | Độ bao phủ@K | Tỷ lệ items đúng trong top K |
| **NDCG@K** | NDCG@K | Độ chính xác có trọng số vị trí |
| **Embedding** | Embedding | Biểu diễn vector của node |
| **Over-smoothing** | Over-smoothing | Hiện tượng nodes giống nhau |
| **Early Stopping** | Dừng sớm | Dừng khi không cải thiện |

---

*Tài liệu được viết dựa trên nghiên cứu SR-GNN (AAAI 2019), Attention-Enhanced GNN (Mathematics 2020), và LightGCN.*
