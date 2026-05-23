# Nghiên cứu chi tiết: Graph and Sequential Neural Networks in Session-based Recommendation: A Survey

## Thông tin bài báo

- **Tiêu đề:** Graph and Sequential Neural Networks in Session-based Recommendation: A Survey
- **Tác giả:** Zihao Li, Chao Yang, Yakun Chen, Xianzhi Wang, Hongxu Chen, Guandong Xu, Lina Yao, Michael Sheng
- **Tạp chí:** ACM Computing Surveys, Volume 57, Issue 2, Article 40
- **Năm xuất bản:** November 2024 (Online: September 2024)
- **DOI:** https://doi.org/10.1145/3696413
- **Đơn vị:** University of Technology Sydney, Ocean University of China, UNSW Sydney, Macquarie University, The Education University of Hong Kong
- **Loại bài báo:** SURVEY (Tổng quan/Bài khảo sát)
- **Số trích dẫn:** 17 | **Số lượt tải:** 4,726

---

## Mục lục

1. [Bài Survey là gì? Tại sao quan trọng?](#1-bài-survey-là-gì-tại-sao-quan-trọng)
2. [Ôn lại kiến thức nền tảng](#2-ôn-lại-kiến-thức-nền-tảng)
3. [Các định nghĩa và khái niệm cơ bản](#3-các-định-nghĩa-và-khái-niệm-cơ-bản)
4. [Đặc điểm của Session-Based Recommendation](#4-đặc-điểm-của-session-based-recommendation)
5. [Phân loại các phương pháp SR](#5-phân-loại-các-phương-pháp-sr)
6. [Framework tổng quan cho Sequential Neural Networks](#6-framework-tổng-quan-cho-sequential-neural-networks)
7. [Framework tổng quan cho GNNs](#7-framework-tổng-quan-cho-gnns)
8. [Chi tiết các thành phần kỹ thuật](#8-chi-tiết-các-thành-phần-kỹ-thuật)
9. [Datasets và Evaluation Metrics](#9-datasets-và-evaluation-metrics)
10. [Thách thức và hướng nghiên cứu tương lai](#10-thách-thức-và-hướng-nghiên-cứu-tương-lai)
11. [Kết luận](#11-kết-luận)
12. [Bảng thuật ngữ Anh-Việt](#12-bảng-thuật-ngữ-anh-việt)

---

## 1. Bài Survey là gì? Tại sao quan trọng?

### 1.1 Survey (Bài khảo sát/tổng quan) là gì?

**Survey** là một bài báo khoa học **KHÔNG đề xuất phương pháp mới**, mà thay vào đó:
- **Tổng hợp** tất cả các nghiên cứu trước đó trong một lĩnh vực
- **Phân loại** các phương pháp theo các nhóm/tiêu chí
- **So sánh** ưu/nhược điểm của từng phương pháp
- **Chỉ ra** các khoảng trống nghiên cứu và hướng phát triển tương lai

**Ví dụ:** Nếu bạn muốn tìm hiểu về "Session-Based Recommendation" và có 150+ bài báo, thay vì đọc từng bài một, bạn đọc 1 bài Survey → nó sẽ tóm tắt, phân loại và so sánh tất cả cho bạn.

### 1.2 Tại sao bài Survey này quan trọng?

1. **Mới nhất (2024):** Tổng hợp các nghiên cứu đến tháng 6/2024
2. **Toàn diện:** Review 150+ bài báo về SR
3. **Hệ thống:** Đề xuất framework thống nhất để phân loại
4. **So sánh chi tiết:** Sequential Neural Networks vs GNNs
5. **Định hướng tương lai:** Chỉ ra 8 hướng nghiên cứu mở

### 1.3 Lịch sử phát triển của SR

```
2002: Modani et al. lần đầu đề xuất khái niệm "session" cho dynamic recommendation
2005: Modani et al. đề xuất framework dựa trên bipartite graph (tiên phong)
2016: GRU4REC - áp dụng RNN đầu tiên cho SR
2019: SR-GNN - áp dụng GNN đầu tiên cho SR → Bùng nổ nghiên cứu
2019: 46 bài báo
2020: 85 bài báo (gấp đôi 2019)
2021: 87 bài báo
2022: 126 bài báo
2023: 142 bài báo
2024 (tháng 6): Tổng cộng 593 bài báo trên DBLP
```

**Hội nghị hàng đầu:** RecSys, SIGIR, CIKM, WWW, WSDM, TOIS, TKDE

---

## 2. Ôn lại kiến thức nền tảng

> **Lưu ý quan trọng:** Đây là bài Survey nên nó tổng hợp TẤT CẢ các khái niệm từ các bài trước. Nếu bạn đã đọc 2 file nghiên cứu trước (SR-GNN và Attention-Enhanced GNN), bạn đã có nền tảng tốt. Dưới đây là tóm tắt nhanh:

| Khái niệm | Giải thích ngắn |
|-----------|----------------|
| **Recommendation System** | Hệ thống gợi ý sản phẩm/nội dung cho người dùng |
| **Session** | Một phiên làm việc - chuỗi hành động liên tục của người dùng |
| **Session-Based Recommendation** | Dự đoán hành động tiếp theo CHỈ dựa trên session hiện tại (không cần biết user là ai) |
| **Graph Neural Network (GNN)** | Mạng nơ-ron xử lý dữ liệu dạng đồ thị |
| **Sequential Neural Network** | Mạng nơ-ron xử lý dữ liệu dạng chuỗi (RNN, LSTM, GRU, Transformer) |
| **Attention Mechanism** | Cơ chế tự động tập trung vào phần quan trọng |
| **Embedding** | Biểu diễn đối tượng bằng vector số |

---

## 3. Các định nghĩa và khái niệm cơ bản

### 3.1 Các định nghĩa cốt lõi

#### Item (Sản phẩm)
Là đối tượng mà người dùng tương tác. Thường được biểu diễn bằng một ID.
- **Ví dụ:** iPhone 15, Áo sơ mi, Bài hát "Shape of You"...

#### Attribute (Thuộc tính)
Thông tin bổ sung (side information) của items hoặc interactions.

**Item-oriented attributes (thuộc tính hướng sản phẩm):**
- Brand (thương hiệu): Apple, Samsung...
- Category (danh mục): Điện thoại, Quần áo...
- Text description (mô tả văn bản)
- Images (hình ảnh)

**Interaction-oriented attributes (thuộc tính hướng tương tác):**
- Geographic information (vị trí địa lý)
- Interaction time and order (thời gian và thứ tự tương tác)
- Behavior types (loại hành vi): search (tìm kiếm), click (nhấp chuột), add cart (thêm vào giỏ), buy (mua), share (chia sẻ), comment (bình luận)...

#### Session (Phiên)
Danh sách các items/services mà người dùng đã tương tác, thường sắp xếp theo thời gian.

### 3.2 Ba loại Session-Based Recommendation

#### Loại 1: Session-based Recommendation (SR) - Cơ bản

**Định nghĩa:**
- Cho I = {i₁, i₂, ..., iₙ} là tập tất cả items
- Mỗi session s = [i₁, i₂, ..., iₘ] là chuỗi các items tương tác
- **Nhiệm vụ:** Cho session s, tính xác suất ŷ cho tất cả items → recommend top-K

**Đặc điểm:**
- User ẩn danh (anonymous)
- Chỉ dùng session hiện tại
- Không có lịch sử người dùng

**Ví dụ:**
```
Session: [iPhone → Ốp lưng → AirPods]
→ Dự đoán: Sản phẩm tiếp theo là gì?
```

#### Loại 2: Personalized Session-based Recommendation (PSR)

**Định nghĩa:**
- Cho user u, tập tất cả sessions lịch sử Sᵤ = {Sᵤ₁, Sᵤ₂, ..., Sᵤₙᵤ}
- Session hiện tại: Scᵤ
- Sessions lịch sử: Shᵤ
- **Nhiệm vụ:** Dựa trên Shᵤ, dự đoán item tiếp theo trong Scᵤ

**Khác biệt với SR:**
- Biết user là ai (onymous)
- Có lịch sử sessions của user đó
- Còn gọi là "streaming session-based recommendation"

**Ví dụ:**
```
User "NguyenVanA" có lịch sử:
- Session 1 (tuần trước): [Áo → Quần → Giày]
- Session 2 (hôm qua): [Mũ → Cà vạt]
- Session hiện tại: [Áo sơ mi]
→ Dự đoán: Sản phẩm tiếp theo trong session hiện tại
```

#### Loại 3: Session-based Social Recommendation (SSR)

**Định nghĩa:**
- Dựa trên PSR, thêm thông tin bạn bè/người quen
- Cho user u, tập bạn bè {uₖ} với k từ 1 đến N(u)
- **Nhiệm vụ:** Dựa trên session hiện tại của u VÀ sessions của bạn bè → dự đoán item tiếp theo

**Ví dụ:**
```
User A đang xem: [iPhone]
Bạn bè của A cũng đang xem: [Ốp lưng, AirPods, Sạc dự phòng]
→ Kết hợp cả hai để gợi ý cho A
```

### 3.3 Các loại Graph (Đồ thị) trong SR

#### 3.3.1 Digraph (Đồ thị có hướng) và Undigraph (Đồ thị vô hướng)

**Digraph:**
- Nếu user click item j SAU item i → thêm cạnh có hướng i → j
- Thể hiện thứ tự thời gian

**Undigraph:**
- Thêm cạnh vô hướng giữa i và j
- Không phân biệt thứ tự

#### 3.3.2 Intra-session Graph (Đồ thị nội session)

**Định nghĩa:** Xây dựng đồ thị CHO MỖI session riêng biệt.

**Ví dụ:**
```
Session 1: [A → B → C]  → Graph 1: A → B → C
Session 2: [B → D → E]  → Graph 2: B → D → E
Session 3: [A → C → E]  → Graph 3: A → C → E
```

Mỗi session có đồ thị riêng, không liên kết với nhau.

#### 3.3.3 Inter-session Graph (Đồ thị liên session)

**Định nghĩa:** Xây dựng MỘT đồ thị THỐNG NHẤT cho TẤT CẢ sessions.

**Ví dụ:**
```
Session 1: [A → B → C]
Session 2: [B → D → E]
Session 3: [A → C → E]

Inter-session Graph:
  A → B → C
  ↓   ↓   ↓
  C   D → E
```

Tất cả sessions được gộp vào một đồ thị lớn.

#### 3.3.4 Hypergraph (Siêu đồ thị)

**Khác biệt với đồ thị thường:**
- Đồ thị thường: 1 cạnh nối 2 nodes
- Hypergraph: 1 hyperedge (siêu cạnh) có thể nối NHIỀU nodes cùng lúc

**Ví dụ:**
```
Đồ thị thường: A—B, B—C, C—D (mỗi cạnh nối 2 nodes)
Hypergraph: {A, B, C, D} cùng thuộc 1 hyperedge (1 siêu cạnh nối tất cả)
```

**Các cách định nghĩa hyperedge trong SR:**

| Loại | Cách định nghĩa | Ví dụ |
|------|----------------|-------|
| Hypergraph with attributes | Các items có cùng thuộc tính | Tất cả điện thoại Apple |
| Hypergraph with session | Các items trong cùng session | [iPhone, Ốp lưng, AirPods] |
| Hypergraph with incoming items | Item + các items đến trước nó | iPhone + [Ốp lưng, AirPods] |
| Hypergraph with slide windows | Các items trong cửa sổ ngữ cảnh | 3 items liên tiếp |
| Hypergraph with intent unit | Các items thuộc cùng intent | [Áo, Quần, Giày] = "mặc" |

#### 3.3.5 Heterogeneous Graph (Đồ thị dị thể)

**Định nghĩa:** Đồ thị có NHIỀU LOẠI nodes và NHIỀU LOẠI edges.

**Điều kiện:** |M_node| + |M_edge| > 2

**Các loại Heterogeneous Graph trong SR:**

**(a) User-Item Social Graph:**
- Nodes: User nodes + Item nodes
- Edges: item-to-item + user-to-item + user-to-user (social)

```
User A —follows→ User B
   ↓                  ↓
clicks            clicks
   ↓                  ↓
iPhone ←—similar— Samsung
```

**(b) Item-Attributes Knowledge Graph:**
- Nodes: Item nodes + Attribute nodes
- Edges: item-to-item + item-to-attribute

```
Harry Potter —written_by→ J.K. Rowling
     ↓
 published_in
     ↓
   UK
     ↓
  Genre: Fantasy
```

**(c) User-Behavior Session Graph:**
- Thêm loại edges dựa trên loại hành vi: buy, click, view...

```
User A —click→ iPhone —view→ AirPods —buy→ Ốp lưng
```

**(d) Spatialtemporal Session Graph:**
- Nodes: Item + Session + Location + Time
- Dùng cho các dịch vụ có vị trí: Meituan, Yelp...

```
User tại Q.Hoàn Kiếm (location)
  lúc 14:00 (time)
    click vào Nhà hàng Phở (item)
      trong Session 5
```

---

## 4. Đặc điểm của Session-Based Recommendation

### 4.1 Bốn đặc điểm chính

#### Đặc điểm 1: Session Length (Độ dài session ngắn)

- So với Sequential Recommendation (dùng TẤT CẢ lịch sử), SR chỉ dùng session hiện tại
- Độ dài session rất giới hạn: **median < 6 items** cho hầu hết datasets
- **Ví dụ:** Diginetica: avg 5.12, median 4.0; Yoochoose: avg 3.95, median 3.0

**Hệ quả:** Dữ liệu ít → mô hình phải hoạt động tốt với ít thông tin.

#### Đặc điểm 2: Dynamic and Timely Recommendation (Gợi ý động và kịp thời)

- SR tập trung vào sở thích NGẮN HẠN (short-term interest)
- Không quan tâm sự tiến hóa sở thích dài hạn như Sequential Recommendation
- Mục tiêu: Gợi ý ĐỘNG và KỊP THỜI cho session đang diễn ra

**Ví dụ:**
- Sequential Rec: "User này thích công nghệ → gợi ý iPhone"
- SR: "User ĐANG xem iPhone, Ốp lưng → gợi ý AirPods NGAY BÂY GIỜ"

#### Đặc điểm 3: Adjacent Dependency (Phụ thuộc kề nhau không rõ ràng)

- Items trong session sắp xếp theo thời gian, nhưng KHÔNG có mẫu thứ tự rõ ràng
- Không phải lúc nào item trước cũng "gây ra" item sau

**Ví dụ:**
```
Session: [iPhone → Ốp lưng → Tai nghe → iPhone → Sạc]
→ iPhone xuất hiện 2 lần, không theo thứ tự tuyến tính
→ GNN phù hợp hơn RNN vì nắm bắt được mối quan hệ phi tuyến tính
```

#### Đặc điểm 4: Anonymous (Ẩn danh)

- SR không biết user là ai
- Không có lịch sử tương tác dài hạn
- PSR và SSR có thêm thông tin nhưng CHƯA phải mainstream (chưa phổ biến)

### 4.2 So sánh SR với Sequential Recommendation

| Đặc điểm | Session-Based Rec | Sequential Rec |
|----------|-------------------|----------------|
| Dữ liệu đầu vào | Session hiện tại | Tất cả lịch sử user |
| Độ dài | Ngắn (< 6 items) | Dài (có thể hàng trăm) |
| User | Ẩn danh | Biết danh tính |
| Focus | Short-term interest | Long-term interest evolution |
| Thời gian | Real-time, dynamic | Có thể offline |
| Tính chất | Dynamic, timely | Historical, statistical |

---

## 5. Phân loại các phương pháp SR

### 5.1 Sơ đồ phân loại tổng quan

```
Session-Based Recommendation Methods
├── Conventional Methods (Phương pháp cổ điển)
│   ├── Popularity-based (Dựa trên độ phổ biến)
│   │   ├── POP: Recommend items phổ biến nhất trong training set
│   │   └── S-POP: Recommend items phổ biến nhất trong session hiện tại
│   ├── Frequent Pattern Mining (Khai phá mẫu thường xuyên)
│   │   └── FP-tree: Khai phá items và patterns thường xuyên
│   ├── KNN-based
│   │   ├── Item-oriented KNN: Đo similarity giữa target item và candidates
│   │   └── Session-oriented KNN: Chọn sessions similar nhất, collect items
│   └── Matrix Factorization: Học latent features từ user-item matrix
│
├── Sequential Neural Network-based Methods
│   ├── RNN-based (GRU4REC, HRNN...)
│   ├── Attention-based (NARM, STAMP...)
│   ├── Transformer-based (BERT4Rec, Transformer4Rec...)
│   ├── CNN-based
│   ├── Memory Neural Networks
│   └── Variational Autoencoder (VAE)
│
└── Graph-based Methods
    ├── Random Walk-based (DeepWalk, Node2vec, S-Walk)
    └── GNN-based
        ├── Intra-session Graph (SR-GNN, GC-SAN...)
        ├── Inter-session Graph
        ├── Hypergraph
        ├── Heterogeneous Graph
        └── Hybrid Graphs
```

### 5.2 Chi tiết từng nhóm

#### 5.2.1 Conventional Methods

**Popularity-based:**
- **POP:** Luôn recommend những items phổ biến nhất
  - Ưu điểm: Đơn giản, dễ implement
  - Nhược điểm: Không cá nhân hóa, bỏ qua items mới (cold start)
- **S-POP:** Recommend items phổ biến trong session hiện tại
  - Tốt hơn POP vì xét ngữ cảnh session

**KNN-based:**
- **Item-oriented KNN:** Tìm items similar nhất với item cuối cùng
  - Similarity = cosine similarity
- **Session-oriented KNN:** Tìm sessions similar nhất → collect items từ đó

**Matrix Factorization:**
- Phân tích user-item interaction matrix thành 2 ma trận nhỏ
- Học latent features của users và items

**Markov Chain:**
- **FMC:** Dự đoán next item dựa trên Markov model
- **FPMC:** Kết hợp Matrix Factorization + Markov Chain
- **Hạn chế:** Giả định mạnh - next item chỉ phụ thuộc vào previous item

#### 5.2.2 Sequential Neural Network-based Methods

**RNN-based:**
- **GRU4REC (2016):** Đầu tiên áp dụng RNN cho SR
  - Input: chuỗi clicks → Embedding → n-layer GRU → Full connection → probabilities
- **HRNN:** Hierarchical RNN với inter-session information
- **Tan et al. (2016):** Enhanced RNN bằng data augmentation

**Attention-based:**
- **NARM:** Hybrid encoder với attention mechanism
  - Nắm bắt sequential behavior + main intentions
- **STAMP:** MLP + attention
  - Tăng cường ảnh hưởng của latest interests

**Transformer-based:**
- **BERT4Rec:** Áp dụng BERT (bidirectional) cho SR
- **Transformer4Rec:** Transformer cho session-based

**CNN-based:**
- CNN với dilated convolution để capture n-gram features
- Causal CNN cho long-term dependency

**Khác:**
- **Memory Neural Networks (MNN):** Dùng memory để lưu và truy xuất thông tin
- **VAE (Variational Autoencoder):** Giới thiệu latent variable module

#### 5.2.3 Graph-based Methods

**Random Walk-based:**
- **DeepWalk:** Random walk + word2vec để học node representations
- **Node2vec:** Cải tiến DeepWalk với biased random walk
- **S-Walk:** Random walk with restart, capture inter-session và intra-session relations

**GNN-based:**
- **SR-GNN:** Tiên phong áp dụng GNN cho SR
- **GC-SAN:** GNN + self-attention
- **TAGNN:** GNN + target attention
- Và nhiều biến thể khác...

---

## 6. Framework tổng quan cho Sequential Neural Networks

### 6.1 Pipeline tổng quát

```
Input: s = [i₁, i₂, ..., iₘ] (chuỗi items)
    ↓
[1] Embedding Layer: X = [x₁, x₂, ..., xₘ]
    ↓
[2] Sequence Modeling Layer: H = SM(X)
    ↓
[3] Session Representation Layer: S = SR(H)
    ↓
[4] Prediction Layer: ŷ = P(S, X)
```

**Công thức tổng quát:**
```
H = SM(X)          # Sequence modeling
S = SR(H)          # Session representation
ŷ = P(S, X)        # Prediction
```

### 6.2 Chi tiết từng layer

#### Layer 1: Embedding Layer

Biến mỗi item ID thành vector liên tục:
```
xᵢ = Embedding(i) ∈ Rᵈ
```

**Ví dụ:**
- Item "iPhone" (ID = 123) → x = [0.2, -0.5, 0.8, 0.1, ...] (100 chiều)

#### Layer 2: Sequence Modeling Layer

**Các phương pháp:**

| Phương pháp | Mô tả | Ví dụ |
|---|---|---|
| **GRU/LSTM** | Phổ biến nhất, nắm bắt thông tin tuần tự | GRU4REC, NARM |
| **Self-attention/MLP** | Transformer-style, capture correlation giữa items | BERT4Rec |
| **CNN/Causal CNN** | Capture n-gram features, dilated cho long-term | Multi-interest CNN |
| **Leap Recurrent Unit** | Extended GRU với leap gate | HLN |
| **α-entmax** | Thay thế softmax (softmax đưa vào noise) | [99, 186] |
| **FFT + Transformer** | Fast Fourier Transform + Transformer | [173] |

#### Layer 3: Session Representation Layer

**Các phương pháp tạo vector session:**

| Phương pháp | Công thức | Mô tả |
|---|---|---|
| **Last Item** | s = Whₘ | Dùng vector của item cuối cùng |
| **Mean Pooling** | s = (1/m)Σhᵢ | Trung bình tất cả vectors |
| **Max Pooling** | s = max(h₁, ..., hₘ) | Lấy giá trị lớn nhất mỗi chiều |
| **Soft-attention** | s = Σαᵢhᵢ | Tổng có trọng số |
| **GRU** | s = hidden state cuối | Dùng hidden state cuối của GRU |
| **Self-attention + MLP** | s = E[-1,:] | Transformer-style |

#### Layer 4: Prediction Layer

**Inner Product (phổ biến nhất):**
```
ŷᵢ = softmax(sᵀ · xᵢ)
```

**MLP:**
```
ŷᵢ = σ(MLP(s))
```

---

## 7. Framework tổng quan cho GNNs

### 7.1 Pipeline tổng quát

```
Input: Session set S hoặc session s
    ↓
[1] Session Selection: Chọn session hiện tại + neighbor sessions
    ↓
[2] Graph Construction: Xây dựng đồ thị G
    ↓
[3] Item & Side Information Embedding: Tạo embeddings
    ↓
[4] Information Propagation & Aggregation: H = GNN(X)
    ↓
[5] Session Representation: S = SR(H)
    ↓
[6] Prediction: ŷ = P(S, X)
```

**Công thức tổng quát:**
```
H = GNN(X)         # Information propagation
S = SR(H)          # Session representation
ŷ = P(S, X)        # Prediction
```

### 7.2 Chi tiết từng module

#### Module 1: Session Selection (Chọn sessions lân cận)

Vì session hiện tại thường thiếu thông tin, nhiều nghiên cứu thu thập neighbor sessions.

**4 chiến lược:**

**(a) Adjacent-based (Dựa trên kề nhau):**
- **Item Sharing:** Sessions có chung ít nhất 1 item
- **Share Last Item:** Sessions có chung item cuối cùng
- **Time Closest:** m sessions gần nhất trên timeline

**(b) Similarity-based (Dựa trên độ tương đồng):**
- **Number of Duplicates:** Đếm số items giống nhau
- **Binary Cosine Similarity:** sim(sᵢ, sⱼ) = |sᵢ ∩ sⱼ| / √(|sᵢ| · |sⱼ|)
- **Cosine Similarity:** sim(sᵢ, sⱼ) = (sᵢ · sⱼ) / (||sᵢ|| · ||sⱼ||)
- **Inner Product with Projection:** sim = ReLU(tanh(sᵢ · sⱼᵀ))
- **Euclidean Distance with Gaussian Kernel:** sim = 1 - exp(-dᵢⱼ² / 2d*²)

**(c) User-based (Dựa trên user):**
- **Self-based:** Tất cả sessions lịch sử của user
- **Self + Social:** Sessions của user + bạn bè

**(d) All (Tất cả):**
- Tất cả training sessions
- Sessions trong cùng batch (để cân bằng hiệu suất)

#### Module 2: Graph Construction (Xây dựng đồ thị)

**Các loại đồ thị:**

| Loại | Mô tả | Ví dụ |
|------|-------|-------|
| **Intra-session** | Đồ thị cho mỗi session riêng | SR-GNN |
| **Inter-session** | Đồ thị thống nhất cho tất cả sessions | Global graph |
| **Intra + ε-Neighbor** | Intra-session + thêm ε-neighbor items | [156, 198] |
| **Intra + Relations** | Thêm các loại quan hệ (PRE, NET, SELF, NPL) | [68, 204] |
| **Intra + Virtual Node** | Thêm virtual satellite node | [100, 123] |
| **Teleportation** | Fully connected trong session | [25] |
| **S2SG** | Thêm self-loop + shortcut edges | [18] |
| **Hypergraph** | Siêu cạnh nối nhiều nodes | [47, 140, 166] |
| **Heterogeneous** | Nhiều loại nodes và edges | [13, 19, 94, 102] |

#### Module 3: Item & Side Information Embedding

**3 nhóm embeddings:**

**(a) Item-oriented:**
- **Item Embedding:** xᵢ = Embedding(item_ID)
- **Attribute Embedding:** category, brand, keywords...
- **Item Description Embedding:** Dùng BERT cho text description

**(b) Interaction-oriented:**
- **Interacted Behavior Embedding:** click, add cart, buy...
- **User Embedding:** Thông tin user (nếu có)
- **Time Interval Embedding:** Thời gian giữa 2 hành vi liên tiếp

**(c) Position-oriented:**
- **Positional Embedding:** Vị trí của item trong session
- **Session Segment Embedding:** Chia session thành segments

#### Module 4: Information Propagation & Aggregation

**Các phương pháp:**

**(a) Average Pooling:**
```
hᵢ⁽ˡ⁺¹⁾ = (1/|Nᵢ|) Σⱼ∈Nᵢ Whⱼ⁽ˡ⁾
```
- Trung bình vectors của hàng xóm

**(b) GCN (Graph Convolutional Network):**
```
hᵢ⁽ˡ⁺¹⁾ = σ((1/√(dᵢ+1))Whᵢ⁽ˡ⁾ + Σⱼ∈Nᵢ (1/√((dᵢ+1)(dⱼ+1)))Whⱼ⁽ˡ⁾)
```
- Dạng ma trận: H⁽ˡ⁺¹⁾ = σ(D̃⁻¹/²ÃD̃⁻¹/²H⁽ˡ⁾W⁽ˡ⁾)

**(c) GAT (Graph Attention Network):**
```
hᵢ⁽ˡ⁺¹⁾ = Σⱼ∈Nᵢ αᵢⱼWhⱼ⁽ˡ⁾
αᵢⱼ = exp(LeakyReLU(aᵀ[Whᵢ || Whⱼ])) / Σₖ exp(LeakyReLU(aᵀ[Whᵢ || Whₖ]))
```
- Attention-based: hàng xóm quan trọng hơn có trọng số cao hơn

**(d) Soft-attention:**
- Inner production: αᵢⱼ = exp(WhᵢᵀWhⱼ) / Σₖ exp(WhᵢᵀWhₖ)
- Concat: αᵢⱼ = exp(σ(aᵀ[Whᵢ || Whⱼ])) / Σₖ exp(σ(aᵀ[Whᵢ || Whₖ]))

**(e) Routing (không có trainable parameters):**
```
hᵢ⁽ˡ⁺¹⁾ = Squash(hᵢ + Σⱼ∈Nᵢ wᵢⱼhⱼ)
wᵢⱼ = exp(hᵢᵀhⱼ) / Σₖ exp(hᵢᵀhₖ)
Squash(x) = (||x||²/(1+||x||²)) · (x/||x||)
```

**(f) Hybrid (GCN/GAT/Soft-attention + GRU):**
```
aₛ,ᵢ = GCN/GAT/Attention([h₁, ..., hₘ])
zₛ,ᵢ = σ(Wz·aₛ,ᵢ + Uz·hᵢ)
rₛ,ᵢ = σ(Wr·aₛ,ᵢ + Ur·hᵢ)
h̃ᵢ = tanh(Wo·aₛ,ᵢ + Uo·(rₛ,ᵢ ⊙ hᵢ))
hᵢ = (1 - zₛ,ᵢ) ⊙ hᵢ + zₛ,ᵢ ⊙ h̃ᵢ
```
- Đây chính là Gated GNN (GGNN) dùng trong SR-GNN

#### Module 5: Session Representation

**Các phương pháp:**

| Phương pháp | Mô tả |
|---|---|
| **Last Item** | s = Whₘ (item cuối cùng) |
| **Mean/Max Pooling** | Trung bình hoặc max pooling |
| **Concatenation** | s = Concat(mean pooling, max pooling) |
| **Concat + MLP** | Concat tất cả → MLP |
| **GRU** | Last hidden state của GRU |
| **Soft-attention** | s = Σαᵢhᵢ |
| **Self-attention + MLP** | Transformer-style |
| **MNN (Memory Neural Network)** | Truy xuất từ memory block |

**Kết hợp Global + Local:**
```
Addition:  s = s_g + s_l
Weight:    s = w·s_g + (1-w)·s_l
```
- s_l = hₗ (last item)
- w = σ(w[s_g || sₗ]) hoặc hyperparameter

#### Module 6: Prediction Layer

**Inner Product:**
```
ŷᵢ = softmax(sᵀ · xᵢ)
```

**MLP:**
```
ŷᵢ = σ(MLP(s))
```

---

## 8. Chi tiết các thành phần kỹ thuật

### 8.1 Loss Functions (Hàm mất mát)

#### 8.1.1 Standard Loss Functions

**(a) Cross-Entropy Loss (phổ biến nhất):**
```
L_CE = -Σᵢ log(ŷᵢ)
```
- ŷᵢ là xác suất dự đoán cho item đúng

**(b) BPR Loss (Bayesian Personalized Ranking):**
```
L_bpr = -(1/N_S) Σⱼ log σ(ŷᵢ - ŷⱼ)
```
- ŷᵢ = score của item đúng, ŷⱼ = score của item sai
- Tối ưu pairwise ranking

**(c) TOP1 Loss:**
```
L_top1 = (1/N_S) Σⱼ [σ(ŷⱼ - ŷᵢ) + σ(ŷⱼ²)]
```

**(d) BPR-max:**
```
L_bpr-max = -log Σⱼ sⱼσ(ŷᵢ - ŷⱼ) + λ Σⱼ sⱼŷⱼ²
```
- Dùng softmax weights cho negative examples
- Thêm L2 regularization

**(e) List-wise Ranking Loss:**
```
L_rank = -Σⱼ ŷᵢ log ŷⱼ
```
- Chỉ xét top-K scores

**(f) Robust Distance Measuring (RDM):**
```
L_RDM = -log exp(cos(s, x⁺)/τ) / Σᵢ exp(cos(s, xᵢ)/τ)
```
- Inspired by contrastive learning

**(g) Adaptive Weight Loss (inspired by Focal Loss):**
```
pᵢ = ŷᵢ nếu y=1, else 1-ŷᵢ
L_AW = -Σᵢ (2 - 2pᵢ)^γ log(pᵢ)
```
- γ controls modulating factor
- Tăng đóng góp của hard samples, giảm easy samples

#### 8.1.2 Auxiliary Loss Functions

**InfoNCE (Contrastive Learning):**
```
L_InfoNCE = -log Σᵢ∈Θ⁺ exp(φ(θ, θᵢ)/τ) / Σⱼ∈Θ exp(φ(θ, θⱼ)/τ)
```
- φ = discriminator function (inner product hoặc khác)
- Tối ưu uniformity và alignment của representations

**Khác:**
- Distillation loss [182]
- Interest-independent loss với distance correlation [123]
- Link prediction loss cho knowledge graphs [94, 191]

### 8.2 External Information Fusion (Kết hợp thông tin bên ngoài)

**3 giai đoạn fusion:**

| Giai đoạn | Mô tả | Ưu điểm | Nhược điểm |
|---|---|---|---|
| **Fusion-First** | Fuse ở embedding stage | Đơn giản, hiệu quả | Không khai thác sâu |
| **Fusion-in-Process** | Inject trong propagation | Mô tả được implicit correlation | Phức tạp |
| **Fusion-Last** | Construct separate graphs → fuse | Khai thác đầy đủ features | Tốn computation |

**Phương pháp fusion:**
- Addition (cộng)
- Concatenation (nối)
- Gate mechanism (cổng)
- Convolution (tích chập)
- Self-attention

### 8.3 Multi-Interest Representation (Biểu diễn đa sở thích)

**Vấn đề:** Một vector session duy nhất KHÔNG đủ để biểu diễn đa dạng sở thích.

**Các giải pháp:**

| Phương pháp | Mô tả |
|---|---|
| **Capsule Networks** | GCN + capsule network cho multi-level, multi-interests |
| **Hierarchical Leaping Network** | Extract subsequences → học multi-interest |
| **Chunk-based** | Chia item embedding thành chunks → GGNN cho mỗi chunk |
| **Clustering** | Cluster similar products → cải thiện diversity |
| **Interest split** | Tách thành interest trend + interest diversity |

### 8.4 Distribution Representation (Biểu diễn phân phối)

**Ý tưởng:** Thay vì biểu diễn item bằng 1 vector cố định → biểu diễn bằng PHÂN PHỐI.

**Ví dụ:**
- Item embedding ~ Multi-Gaussian Distribution
- Mean vector = basic preferences
- Covariance matrix = uncertainty (độ không chắc chắn)

**Ưu điểm:** Inject uncertainties và flexibility vào mô hình.

---

## 9. Datasets và Evaluation Metrics

### 9.1 Public Datasets

| Dataset | Domain | # Sessions | # Interactions | # Items | Avg Length |
|---------|--------|-----------|----------------|---------|------------|
| **Yoochoose** | E-commerce | 1,375,128 | 5,426,961 | 28,582 | 3.95 |
| **Tmall** | E-commerce | 1,774,729 | 13,418,695 | 425,348 | 7.56 |
| **Diginetica** | E-commerce | 780,328 | 982,961 | 43,097 | 5.12 |
| **RetailRocket** | E-commerce | 59,962 | 212,182 | 31,968 | 3.54 |
| **Last.FM** | Music | 169,576 | 2,887,349 | 449,037 | 17.03 |
| **NowPlaying** | Music | 27,005 | 271,177 | 75,169 | 10.04 |
| **Xing** | Job | 91,683 | 546,862 | 59,121 | 5.78 |
| **Gowalla** | Check-in | 830,893 | 245,157 | 6,871 | 4.32 |

**Chi tiết từng dataset:**

**Yoochoose:**
- RecSys Challenge 2015
- User clicks/buy events trong 6 tháng
- Thường dùng subsamples: 1/64 và 1/4

**Tmall:**
- IJCAI-15 competition
- Shopping logs trên Tmall platform

**Diginetica:**
- CIKM CUP 2016
- Transition histories

**RetailRocket:**
- Real-world e-commerce
- User behavior + item properties

**Last.FM:**
- Music artist recommendation

**NowPlaying:**
- Từ music-related tweets

**Xing:**
- Recsys Challenge 2016
- 770k users over 80 days
- Interactions: click, bookmark, reply, delete

**Gowalla:**
- Check-in data + social network
- Location-based social networking

**Tiền xử lý chung:**
- Filter sessions có length = 1
- Filter items xuất hiện < 5 lần

### 9.2 Evaluation Metrics

#### 9.2.1 Accuracy Metrics (Độ chính xác)

**(a) HR@K (Hit Rate):**
```
HR@K = n_hit / N
```
- N = số test sessions
- n_hit = số lần target item nằm trong top-K
- **Ý nghĩa:** Tỷ lệ sessions mà model dự đoán ĐÚNG (target item ∈ top-K)

**Ví dụ:** 100 test sessions, model dự đoán đúng 50 lần → HR@20 = 50%

**(b) MRR@K (Mean Reciprocal Rank):**
```
MRR@K = (1/N) Σ 1/Rank(î)
```
- Rank(î) = hạng của target item (0 nếu không trong top-K)
- **Ý nghĩa:** Trung bình nghịch đảo hạng → hạng càng cao (số càng nhỏ) càng tốt

**Ví dụ:**
- Target item ở hạng 1 → reciprocal rank = 1/1 = 1.0
- Target item ở hạng 3 → reciprocal rank = 1/3 ≈ 0.33
- Target item ở hạng > 20 → reciprocal rank = 0

**(c) NDCG@K (Normalized Discounted Cumulative Gain):**
```
NDCG@K = (1/N) Σ 1/log₂(Rank(î) + 1)
```
- Tương tự MRR nhưng discount chậm hơn
- Estimates ranking order

**K thường dùng:** 5, 10, 20

#### 9.2.2 Diversity Metrics (Đa dạng)

**(a) ILD (Intra-List Distance):**
```
ILD = Σ dᵢⱼ / (|RL| × (|RL| - 1))
```
- dᵢⱼ = Euclidean distance của category embeddings
- Đo average pairwise dissimilarity
- ILD cao → gợi ý đa dạng hơn

**(b) Coverage@K:**
```
Coverage@K = |∩ Cᵢ| / K
```
- Cᵢ = category của item i
- Đo số lượng categories khác nhau trong top-K

---

## 10. Thách thức và hướng nghiên cứu tương lai

### 10.1 More External Information (Thêm thông tin bên ngoài)

**3 vấn đề mở:**

**Vấn đề 1: Thông tin nào cần thiết?**
- 3 nhóm: item-based, interaction-based, position-based
- Một số tốn kém (item descriptions, user comments)
- Một số không phù hợp (user personal info - sessions phải ẩn danh)
- Một số không cần thiết (position/order info - sessions ngắn)
- Phụ thuộc vào scenario: news/book/music → categories quan trọng; products → brand/price quan trọng

**Vấn đề 2: Cân bằng effectiveness vs. efficiency**

| Phương pháp | Ưu điểm | Nhược điểm |
|---|---|---|
| Addition | Không thay đổi cấu trúc, không thêm params | Không khai thác sâu |
| Concatenation | Tăng cường representation | Tăng complexity dramatically |
| Self-attention | Hiệu quả | Tốn extra params và computation |

**Vấn đề 3: Couple vs. Decouple - cái nào tốt hơn?**
- **Couple (Fusion-First):** Unified framework → efficient nhưng giới hạn capacity
- **Decouple (Fusion-Last):** Khai thác đầy đủ features → computation cost cao

### 10.2 Session Selection và Graph Construction

**3 vấn đề:**

**(1) Scalable Graphs:**
- Graphs lớn với billions nodes/edges trong thực tế
- Sampling (GraphSage, PinSage) có randomness cao → unstable training
- Cần scalable graph structure design

**(2) Dynamic Graphs:**
- Items và relations thay đổi theo thời gian
- Hầu hết studies dùng static graphs
- Dynamic graphs chưa được khám phá nhiều

**(3) Self-learning Graph Structure:**
- Obtaining proper graph structure cần nhiều effort
- Heuristic và problem-specific
- Self-learning strategy hứa hẹn [35, 70, 164]

### 10.3 Diverse and Uncertain Representation of User Interests

**(1) Diverse Representation:**
- Single fixed representation → insufficient
- Methods: capsule networks, attention, multi-interest, short/long-term
- **Vấn đề mở:** Làm sao xác định số interests adaptively? Làm sao fuse interest representations?

**(2) Uncertain Representation:**
- Distribution representation injects uncertainties
- Item embedding = multi-Gaussian distribution
- Mean = basic preferences, Covariance = uncertainty
- Rất ít studies cho SR → hướng hứa hẹn

### 10.4 Explainability và Privacy Protection

**Explainability (Khả năng giải thích):**
- Trả lời "TẠI SAO" item được recommend
- Cải thiện transparency, persuasiveness, user satisfaction
- Deep learning = black boxes → challenging
- **Rất ít studies** tập trung vào SR explainability

**Privacy Protection (Bảo vệ quyền riêng tư):**
- Historical interactions chứa private info (gender, age, political orientation)
- Unlearning strategies để xóa sensitive data
- Chủ đề nghiên cứu tương lai hứa hẹn

### 10.5 Streaming hoặc Online SR

**Vấn đề:**
- Sessions được tạo dynamically như stream
- Static models không hợp lý cho sessions mới
- Preferences thay đổi theo thời gian

**Giải pháp hiện tại:**
- Maintain reservoir để update model
- Sampling bằng Wasserstein distance hoặc ranking-based distance
- Problem: Phụ thuộc vào sampling strategy + expensive

**Lightweight approaches:**
- Model compression: low-rank decomposition, hash coding, quantization
- Problem: Fixed compression ratio → sub-optimal

### 10.6 Causal Debias và Denoise

**Vấn đề:**
- Bias và noise từ exposure mechanism, popularity effects, feedback loop
- Làm giảm effectiveness

**Giải pháp:**
- Causal-inference, causal graph
- Giới hạn studies cho SR → sẽ đưa research lên tầm cao mới

### 10.7 Reinforcement Learning cho SR

**Tiềm năng:**
- RL focuses on goal-directed learning maximizing total reward
- Modeling user-agent interactions
- Capturing rapid preference changes
- Dynamic recommendations

**4 ứng dụng:**
1. Simulating user interactions cho dynamic/timely recommendations
2. Capturing interest shift
3. Filtering noise trong sessions
4. Selecting valuable items cho SR

**Thách thức:**
- Model-free deep RL cần nhiều samples
- SR có sessions ngắn + action space cực lớn
- Cần high-quality samples để cover exploration space

### 10.8 SR với Language Model và Diffusion Model

**Large Language Models (LLMs):**
- Prompting/in-context learning và PEFT
- GPT-3, LLaMA (TALLRec với LoRA), M6-Rec
- **RAG (Retrieval-Augmented Generation):** External knowledge → guide LLM
- Ít efforts explore LLM + RAG trong SR

**Diffusion Models:**
- 2 stages: diffusion (corrupt → Gaussian) + reverse (recover từ noise)
- DiffuRec: đầu tiên áp dụng diffusion cho sequential recommendation
- **CHƯA CÓ WORK nào** áp dụng diffusion cho SR
- **Drawbacks:** Discrete embedding space, time cost trong reverse stage
- Promising uphill research area

---

## 11. Kết luận

### 11.1 Tóm tắt nội dung Survey

Bài survey này đã:

1. **Chuẩn hóa khái niệm:** Định nghĩa rõ ràng về SR, các loại session, các loại graph
2. **Phân loại hệ thống:** 3 nhóm chính - Conventional, Sequential NN, Graph-based
3. **Framework thống nhất:** Pipeline cho cả Sequential NN và GNN
4. **Chi tiết kỹ thuật:** Embedding, propagation, session representation, prediction, loss functions
5. **Datasets & Metrics:** 8 datasets phổ biến, các metrics accuracy và diversity
6. **Thách thức & Hướng tương lai:** 8 hướng nghiên cứu mở

### 11.2 So sánh Sequential NN vs GNN

| Đặc điểm | Sequential NN | GNN |
|----------|--------------|-----|
| Biểu diễn session | Chuỗi tuần tự | Đồ thị |
| Nắm bắt quan hệ | Tuần tự (trước→sau) | Đa chiều (mọi node với nhau) |
| Phù hợp khi | Session dài, có thứ tự rõ ràng | Session ngắn, quan hệ phức tạp |
| Phổ biến | GRU, LSTM, Transformer | GCN, GAT, GGNN |
| Ưu điểm | Đơn giản, hiệu quả với chuỗi dài | Nắm bắt implicit dependencies |
| Nhược điểm | Bỏ qua quan hệ không liên tiếp | Cần xây dựng graph trước |

### 11.3 Xu hướng nghiên cứu

1. **Kết hợp nhiều loại thông tin:** External info, knowledge graphs, social networks
2. **Multi-interest representation:** Không dùng 1 vector cố định
3. **Dynamic/Online SR:** Real-time recommendation
4. **Causal reasoning:** Debias và denoise
5. **LLM + RAG:** Tận dụng sức mạnh của language models
6. **Diffusion Models:** Hướng nghiên cứu mới mẻ

---

## 12. Bảng thuật ngữ Anh-Việt

| Tiếng Anh | Tiếng Việt | Giải thích |
|-----------|-----------|-----------|
| Survey | Bài khảo sát/tổng quan | Tổng hợp và phân loại các nghiên cứu |
| Session-based Recommendation | Gợi ý dựa trên phiên | Dự đoán từ session hiện tại |
| Sequential Recommendation | Gợi ý tuần tự | Dự đoán từ toàn bộ lịch sử |
| Intra-session Graph | Đồ thị nội session | Đồ thị cho mỗi session riêng |
| Inter-session Graph | Đồ thị liên session | Đồ thị thống nhất cho tất cả |
| Hypergraph | Siêu đồ thị | 1 cạnh nối nhiều nodes |
| Heterogeneous Graph | Đồ thị dị thể | Nhiều loại nodes và edges |
| Knowledge Graph | Đồ thị tri thức | Graph với entities và relations |
| Information Propagation | Lan truyền thông tin | Thông tin lan truyền giữa các nodes |
| Aggregation | Tổng hợp | Gom thông tin từ hàng xóm |
| Neighbor Session | Session lân cận | Sessions có liên quan |
| Item Sharing | Chia sẻ item | Sessions có chung items |
| Similarity-based | Dựa trên tương đồng | Chọn sessions similar nhất |
| Positional Embedding | Embedding vị trí | Biểu diễn vị trí trong chuỗi |
| Side Information | Thông tin phụ/bổ sung | External info của items/users |
| Cross-Entropy Loss | Hàm mất mát chéo | Loss function phổ biến nhất |
| BPR Loss | Hàm mất mát BPR | Pairwise ranking loss |
| Contrastive Learning | Học tương phản | Học bằng cách so sánh positive/negative |
| InfoNCE | InfoNCE | Contrastive loss function |
| Multi-Interest | Đa sở thích | Nhiều sở thích khác nhau |
| Distribution Representation | Biểu diễn phân phối | Biểu diễn bằng phân phối xác suất |
| Explainability | Khả năng giải thích | Giải thích tại sao recommend |
| Privacy Protection | Bảo vệ quyền riêng tư | Bảo vệ thông tin cá nhân |
| Streaming SR | SR luồng | SR online, real-time |
| Causal Debias | Khử thiên kiến nhân quả | Loại bỏ bias bằng causal reasoning |
| Reinforcement Learning | Học tăng cường | Học bằng thưởng/phạt |
| Large Language Model | Mô hình ngôn ngữ lớn | GPT, LLaMA... |
| Diffusion Model | Mô hình khuếch tán | Generative model 2 giai đoạn |
| RAG | RAG | Retrieval-Augmented Generation |
| Hit Rate | Tỷ lệ trúng | HR@K |
| MRR | Trung bình nghịch đảo hạng | MRR@K |
| NDCG | NDCG | Normalized DCG |
| ILD | Khoảng cách nội danh sách | Intra-List Distance |
| Coverage | Độ phủ | Coverage@K |
| Cold Start | Khởi đầu lạnh | Vấn đề với items/users mới |
| Overfitting | Học thuộc lòng | Model quá khớp với training data |
| Regularization | Điều chuẩn | Kỹ thuật tránh overfitting |
| Dropout | Dropout | Tắt ngẫu nhiên nodes khi train |
| Residual Connection | Kết nối dư | Nhảy qua các layers |
