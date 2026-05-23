# Giải thích Notebook Otto GNN Optimized cho người mới bắt đầu

## Mục lục
1. [Otto là gì?](#1-otto-là-gì)
2. [LightGCN là gì?](#2-lightgcn-là-gì)
3. [Tổng quan Notebook](#3-tổng-quan-notebook)
4. [Các bước chi tiết](#4-các-bước-chi-tiết)

---

## 1. Otto là gì?

**Otto Group** là một cuộc thi trên Kaggle về hệ thống khuyến nghị (Recommendation System). Cuộc thi này yêu cầu dự đoán các sản phẩm mà người dùng sẽ **thêm vào giỏ hàng (cart)** hoặc **đặt hàng (order)** dựa trên lịch sử hành vi của họ.

### Dữ liệu bao gồm 3 loại tương tác:
- **Clicks** (Nhấp chuột): Người dùng xem sản phẩm
- **Carts** (Giỏ hàng): Người dùng thêm vào giỏ
- **Orders** (Đơn hàng): Người dùng mua sản phẩm

### Mục tiêu:
- Dự đoán top 20 sản phẩm mà người dùng có khả năng thêm vào giỏ hoặc mua

---

## 2. LightGCN là gì?

### 2.1. Đồ thị (Graph) trong Recommendation

Trong hệ thống khuyến nghị, chúng ta có thể biểu diễn dữ liệu dưới dạng **đồ thị**:
- **Node (Đỉnh)**: Người dùng (users) và Sản phẩm (items)
- **Edge (Cạnh)**: Tương tác giữa người dùng và sản phẩm (click, cart, order)

```
    User A ----click----> Item 1
    User A ----order----> Item 2
    User B ----click----> Item 1
    User B ----cart-----> Item 3
```

### 2.2. Graph Neural Network (GNN)

**GNN** là một loại mạng neural hoạt động trên dữ liệu dạng đồ thị. Thay vì xử lý từng điểm dữ liệu độc lập, GNN "truyền" thông tin giữa các node theo các cạnh.

**Ý tưởng**: Nếu User A và User B đều thích Item 1, thì họ có thể có sở thích tương tự. Item 1 và Item 2 được nhiều người dùng giống nhau mua có thể tương tự nhau.

### 2.3. LightGCN

**LightGCN** là phiên bản đơn giản hóa của GCN (Graph Convolutional Network):
- Loại bỏ các phép biến đổi feature (không dùng transformation matrix)
- Chỉ giữ lại phép lan truyền (propagation) và tổng hợp (aggregation)
- Đơn giản, huấn luyện nhanh hơn, thường cho kết quả tốt hơn

```
Input: User-Item Graph
    ↓
    Embedding Layer (tạo vector ngẫu nhiên cho mỗi user và item)
    ↓
    Nhiều lớp GNN (lan truyền thông tin qua đồ thị)
    ↓
    Tổng hợp các layer (combine all layers)
    ↓
    Output: Vector embedding cho users và items
```

---

## 3. Tổng quan Notebook

Notebook này triển khai **LightGCN Optimized** với các cải tiến:

| Tối ưu | Giải thích |
|--------|------------|
| **Type-weighted edges** | Các tương tác khác nhau có trọng số khác nhau (Orders > Carts > Clicks) |
| **Neighbor sampling** | Lấy mẫu láng giềng để huấn luyện hiệu quả hơn |
| **Learning rate scheduling** | Warmup + Cosine annealing để học ổn định |
| **WandB logging** | Theo dõi quá trình huấn luyện |
| **Validation metrics** | Recall@20, NDCG@20 đánh giá mô hình |
| **Session sampling** | Lấy 15% sessions để huấn luyện |
| **Early stopping** | Dừng sớm khi không cải thiện |

---

## 4. Các bước chi tiết

### Bước 1: Cài đặt thư viện

```python
!pip install torch_geometric wandb -q
```

- **torch_geometric**: Thư viện cho Graph Neural Networks
- **wandb**: Công cụ theo dõi quá trình huấn luyện

### Bước 2: Cấu hình (Configuration)

```python
SEED = 1023
TYPE_WEIGHTS = {'clicks': 1.0, 'carts': 6.0, 'orders': 3.0}

class Config:
    embed_dim = 64       # Kích thước vector embedding
    num_layers = 4       # Số lớp GNN
    batch_size = 4096    # Kích thước batch
    epochs = 50          # Số epoch
    learning_rate = 5e-4 # Tốc độ học
    session_sample_rate = 0.15  # Lấy 15% sessions
```

**Giải thích các tham số:**
- `embed_dim = 64`: Mỗi user và item được biểu diễn bằng vector 64 chiều
- `TYPE_WEIGHTS`: Orders có trọng số cao nhất (3.0), Carts (6.0), Clicks (1.0). **Lưu ý**: Carts có trọng số cao nhất vì đây là mục tiêu chính của cuộc thi!
- `session_sample_rate = 0.15`: Không huấn luyện trên toàn bộ dữ liệu mà chỉ 15% để tiết kiệm thời gian

### Bước 3: Tải dữ liệu

```python
type_map = {'clicks': 0, 'carts': 1, 'orders': 2}
```

Chuyển đổi tên loại tương tác thành số để máy tính hiểu.

### Bước 4: Lấy mẫu Sessions

```python
sampled_sessions = all_train_sessions.sample(fraction=0.15)
train_data = full_train_df.filter(pl.col('session').is_in(sampled_sessions))
```

- Lấy ngẫu nhiên 15% sessions từ dữ liệu gốc
- Lý do: Dữ liệu Otto rất lớn (hàng triệu interactions), không thể huấn luyện trên toàn bộ

### Bước 5: Tạo ánh xạ (Mapping)

```python
session2idx = {s: i for i, s in enumerate(unique_sessions)}
aid2idx = {a: i + num_sessions for i, a in enumerate(unique_aids)}
```

- Gán ID số cho mỗi session và item
- **Quan trọng**: Session được đánh số từ 0, items được đánh số từ `num_sessions` để tránh trùng lặp

### Bước 6: Xây dựng đồ thị (Edge Construction)

```python
# Tạo edges hai chiều (bidirectional)
edge_index = np.array([
    np.concatenate([source_nodes, target_nodes]),
    np.concatenate([target_nodes, source_nodes])
])
```

**Ví dụ:**
- User 0 click Item 5 → Tạo edge 0→5 và 5→0
- Điều này cho phép thông tin "chảy" giữa users và items

### Bước 7: Chuẩn bị dữ liệu huấn luyện

```python
class BPRDataset(Dataset):
    def __getitem__(self, idx):
        user_idx, pos_item_idx = self.interaction_pairs[idx]
        
        # Negative sampling: chọn item ngẫu nhiên không tương tác
        neg_item_idx = random.choice(self.all_items)
        while neg_item_idx in self.user_pos_items.get(user_idx, set()):
            neg_item_idx = random.choice(self.all_items)
        
        return (user_idx, pos_item_idx, neg_item_idx)
```

**BPR (Bayesian Personalized Ranking) Loss:**
- So sánh embedding của user với:
  - Item tích cực (positive): item user đã tương tác
  - Item tiêu cực (negative): item user KHÔNG tương tác
- Mục tiêu: Đưa positive items gần user hơn, đẩy negative items ra xa

### Bước 8: Định nghĩa Model LightGCN

```python
class LightGCN(nn.Module):
    def __init__(self, num_users, num_items, embed_dim=64, num_layers=4):
        self.embedding = nn.Embedding(num_users + num_items, embed_dim)
        self.convs = nn.ModuleList([GCNConv(embed_dim, embed_dim) for _ in range(num_layers)])
        self.agg_weights = nn.Parameter(torch.ones(num_layers + 1) / (num_layers + 1))
```

**Cấu trúc:**
1. **Embedding Layer**: Tạo vector ngẫu nhiên cho mỗi node
2. **GCNConv**: Các lớp tích chập đồ thị, lan truyền thông tin
3. **Aggregation**: Tổng hợp tất cả các lớp với trọng số học được

```python
def forward(self, edge_index, edge_weight=None):
    x0 = self.embedding.weight
    all_embeddings = [x0]
    
    # Lan truyền qua các lớp
    for conv in self.convs:
        x = conv(x, edge_index, edge_weight)
        all_embeddings.append(x)
    
    # Tổng hợp có trọng số
    weights = F.softmax(self.agg_weights, dim=0)
    final_emb = sum(w * emb for w, emb in zip(weights, all_embeddings))
    
    # Tách user và item embeddings
    users_emb, items_emb = torch.split(final_emb, [num_users, num_items])
    return users_emb, items_emb
```

### Bước 9: Optimizer và Scheduler

```python
optimizer = optim.AdamW(model.parameters(), lr=5e-4, weight_decay=1e-5)

def get_lr(epoch):
    if epoch < warmup_epochs:
        return (epoch + 1) / warmup_epochs  # Warmup
    else:
        progress = (epoch - warmup_epochs) / (epochs - warmup_epochs)
        return 0.5 * (1 + math.cos(math.pi * progress))  # Cosine annealing
```

**Learning Rate Schedule:**
- **Warmup (3 epochs đầu)**: Tăng dần từ 0 lên lr ban đầu
- **Cosine Annealing**: Giảm dần theo hình cos, giúp hội tụ ổn định

### Bước 10: Hàm Loss và Đánh giá

```python
def bpr_loss(users_emb, pos_emb, neg_emb):
    pos_scores = torch.sum(users_emb * pos_emb, dim=-1)
    neg_scores = torch.sum(users_emb * neg_emb, dim=-1)
    loss = -torch.mean(F.logsigmoid(pos_scores - neg_scores))
    return loss
```

**Recall@20:**
- Đo lường khả năng đề xuất đúng sản phẩm
- Công thức: Số items đúng trong top 20 / Tổng số items thực tế

### Bước 11: Vòng lặp huấn luyện

```python
for epoch in range(epochs):
    # Training
    model.train()
    for users, pos_items, neg_items in train_loader:
        optimizer.zero_grad()
        users_emb, items_emb = model(edge_index, edge_weight)
        loss = bpr_loss(users_emb[users], items_emb[pos_items], items_emb[neg_items])
        loss.backward()
        optimizer.step()
    
    # Validation
    model.eval()
    with torch.no_grad():
        recall = get_recall_at_k(val_users_emb, val_items_emb, user_pos_dict, k=20)
    
    # Early stopping
    if recall > best_recall:
        save_model()
    else:
        patience_counter += 1
```

### Bước 12: Lưu Embeddings

Sau khi huấn luyện xong, lưu lại embeddings để sử dụng cho việc đề xuất sản phẩm trong cuộc thi.

---

## Tóm tắt luồng dữ liệu

```
Raw Data (parquet files)
    ↓
Sampling 15% sessions
    ↓
Create User-Item Graph with weighted edges
    ↓
BPR Dataset (positive + negative pairs)
    ↓
LightGCN Model
    ↓
Embeddings (users + items)
    ↓
Top-K Recommendation (Recall@20)
```

---

## Các tham số quan trọng có thể điều chỉnh

| Tham số | Giá trị hiện tại | Ảnh hưởng |
|---------|------------------|-----------|
| embed_dim | 64 | Lớn hơn → model mạnh hơn nhưng chậm hơn |
| num_layers | 4 | Nhiều hơn → lan truyền xa hơn nhưng có thể overfit |
| batch_size | 4096 | Lớn hơn → ổn định hơn nhưng cần nhiều RAM |
| learning_rate | 5e-4 | Lớn hơn → học nhanh nhưng có thể không hội tụ |
| session_sample_rate | 0.15 | Lớn hơn → dữ liệu nhiều hơn, model tốt hơn |

---

## Kết luận

Notebook này triển khai một hệ thống khuyến nghị sử dụng **LightGCN** - một thuật toán Graph Neural Network nhẹ và hiệu quả. Các tối ưu được áp dụng giúp model học tốt hơn và nhanh hơn:

1. **Trọng số loại tương tác**: Ưu tiên Orders và Carts hơn Clicks
2. **Tổng hợp đa tầng**: Kết hợp thông tin từ nhiều lớp GNN
3. **Learning rate schedule**: Warmup + Cosine giúp học ổn định
4. **Early stopping**: Tránh overfitting

Đây là một phương pháp tiên tiến trong lĩnh vực Recommendation System và đã được sử dụng thành công trong nhiều cuộc thi Kaggle.