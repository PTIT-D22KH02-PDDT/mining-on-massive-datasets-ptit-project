# GHTID: Global Heterogeneous Graph and Target Interest Denoising for Multi-behavior Sequential Recommendation

## Giới thiệu tổng quan

### Paper này về cái gì?

Paper được công bố tại **WSDM '24** (Hội nghị ACM về Web Search và Data Mining) đề xuất một phương pháp mới gọi là **GHTID** để giải quyết bài toán **Multi-behavior Sequential Recommendation (MBSR)** - tức dự đoán sản phẩm tiếp theo mà người dùng sẽ tương tác, dựa trên lịch sử tương tác với nhiều loại hành vi khác nhau.

---

## Phần 1: CÁC ĐỊNH NGHĨA CƠ BẢN

### 1.1 Recommendation System (Hệ thống Gợi ý)

**Định nghĩa:**
Hệ thống gợi ý là hệ thống dự đoán những gì người dùng có thể quan tâm, dựa trên dữ liệu hành vi quá khứ của họ.

**Ví dụ thực tế:**
- Netflix gợi ý phim tiếp theo bạn nên xem
- Amazon gợi ý sản phẩm bạn nên mua
- TikTok gợi ý video bạn nên xem tiếp

**Vai trò:**
- Giúp người dùng tìm thấy nội dung/phẩm phù hợp nhanh hơn
- Giảm tải thông tin (information overload)
- Tăng trải nghiệm người dùng và doanh thu

---

### 1.2 Sequential Recommendation (SR) - Hệ thống Gợi ý Tuần tự

**Định nghĩa:**
Hệ thống gợi ý tuần tự dự đoán sản phẩm tiếp theo dựa trên **thứ tự** các sản phẩm mà người dùng đã tương tác trước đó.

**Ý tưởng chính:**
- Học từ chuỗi các items (A → B → C → ...)
- Dự đoán item tiếp theo (D)
- Quan tâm đến "ai làm gì trước"

**Ví dụ thực tế:**
```
Sequence của user: [iPhone 15, Case iPhone, Tai nghe AirPods, Sạc dự phòng]
Dự đoán:       [Dock sạc Apple Watch]
```

**Vai trò:**
- Nắm bắt xu hướng hiện tại của user
- Dự đoán nhu cầu ngắn hạn
- Cải thiện độ chính xác so với collaborative filtering truyền thống

---

### 1.3 Multi-behavior Sequential Recommendation (MBSR) - Gợi ý Tuần tự Đa hành vi

**Định nghĩa:**
MBSR là phiên bản nâng cao của SR, xem xét **nhiều loại hành vi** khác nhau mà user có thể thực hiện với sản phẩm.

**Các loại hành vi:**

| Ký hiệu | Tên tiếng Anh | Tên tiếng Việt | Ý nghĩa |
|---------|---------------|---------------|---------|
| PV | Page View | Xem trang | User chỉ xem sản phẩm |
| Cart | Add to Cart | Thêm vào giỏ | User thêm vào giỏ hàng |
| Fav | Favorite | Yêu thích | User đánh dấu thích |
| Pur | Purchase | Mua | User mua sản phẩm |

**Ví dụ thực tế trên Amazon:**
```
1. User xem iPhone 15 Pro Max (PV)
2. User xem Samsung S24 Ultra (PV)
3. User thêm iPhone vào giỏ hàng (Cart)
4. User xem case iPhone (PV)
5. User mua iPhone 15 Pro Max (Pur)
```

**Sequence đầy đủ:**
`[(iP15, PV), (SamS24, PV), (iP15, Cart), (Case, PV), (iP15, Pur)]`

**Sự khác biệt với SR truyền thống:**

| Sequential Recommendation (SR) | Multi-behavior SR |
|-----------------------------|-----------------|
| Chỉ 1 loại hành vi | Nhiều loại hành vi |
| Mua hàng → Mua hàng | Xem → Xem → Mua |
| Ít thông tin | Nhiều thông tin hơn |
| Đơn giản | Phức tạp hơn |

**Tác dụng/Vai trò:**
- Cung cấp tín hiệu phong phú hơn về sở thích user
- User mua = quan tâm thực sự (target behavior)
- User xem = đang cân nhắc (auxiliary behavior)
- Kết hợp cả 2 cho độ chính xác cao hơn

---

### 1.4 Target Behavior - Hành vi Mục tiêu

**Định nghĩa:**
Target Behavior (hành vi mục tiêu) là hành vi có **giá trị cao nhất** đối với doanh nghiệp - thường là **Purchase (mua hàng)**.

**Tại sao là Purchase?**
- Mua = doanh thu trực tiếp cho nền tảng
- Các hành vi khác chỉ là bước trung gian

**Ví dụ:**
| Nền tảng | Target Behavior |
|----------|----------------|
| Shopee, Amazon | Purchase (mua hàng) |
| TikTok, YouTube | Watch (xem video) |
| Spotify, Apple Music | Listen (nghe nhạc) |
| App Store | Download (tải app) |

**Vai trò:**
- Là mục tiêu dự đoán cuối cùng
- Các hành vi khác hỗ trợ dự đoán này

---

### 1.5 Auxiliary Behavior - Hành vi Phụ

**Định nghĩa:**
Auxiliary Behavior (hành vi phụ) là các hành vi **không phải mục tiêu** - thường là PV (xem), Cart (giỏ), Favorite (yêu thích).

**Vấn đề chính:**
- User có thể xem rất nhiều sản phẩm nhưng chỉ mua vài cái
- Thông tin từ PV có thể không liên quan hoặc **trái ngược** với sở thích thực sự

**Ví dụ về nhiễu (noise):**
```
User xem 50 điện thoại khác nhau:
- iPhone 15, Samsung S24, Xiaomi 14, Oppo Find X7, OnePlus 12...
- Google Pixel 8, Vivo X100, Honor Magic 6, Realme GT5...

Nhưng cuối cùng chỉ mua: iPhone 15 Pro
→ 49 sản phẩm còn lại là NHIỄU
```

**Tác dụng/Vai trò:**
- Cung cấp thông tin bổ sung
- Có thể gây nhiễu nếu xử lý không đúng cách
- GHTID giải quyết bằng cách lọc nhiễu

---

### 1.6 Heterogeneous Item Transitions - Chuyển đổi Item không đồng nhất

**Đây là KHÁI NIỆM CỐT LÕI của paper**

**Định nghĩa:**
Heterogeneous Item Transitions mô tả **mối quan hệ/chuyển đổi giữa các items** dựa trên loại hành vi.

**Có 2 loại chuyển đổi:**

#### A) Intra-type Transition (Chuyển đổi CÙNG LOẠI)

**Định nghĩa:**
Chuyển đổi giữa các items cùng loại hành vi.

**Các trường hợp:**
- PV → PV: Từ xem item này đến xem item khác
- Cart → Cart: Từ thêm giỏ này đến thêm giỏ khác  
- Pur → Pur: Từ mua item này đến mua item khác

**Ví dụ:**
```
User xem: iPhone 15 → Samsung S24 → Xiaomi 14
Đây là PV → PV → PV (Intra-type)
```

**Ý nghĩa:**
- Cho biết sở thích trong cùng loại hành vi
- "User thích xem điện thoại, đang cân nhắc nhiều loại"

---

#### B) Cross-type Transition (Chuyển đổi LIÊN LOẠI)

**Định nghĩa:**
Chuyển đổi giữa các items **khác loại** hành vi.

**Các trường hợp:**
- PV → Pur: Từ xem đến mua (quan tâm → mua)
- PV → Cart: Từ xem đến thêm giỏ (quan tâm → cân nhắc)
- Pur → PV: Từ mua đến xem (mua rồi xem thêm)
- Cart → Pur: Từ giỏ đến mua (chuyển từ cân nhắc sang mua)

**Ví dụ:**
```
User xem iPhone 15 (PV) → Thêm vào giỏ (Cart) → Mua (Pur)
Đây là PV → Cart → Pur (Cross-type)
```

**Ý nghĩa:**
- Cho biết mối liên hệ giữa các hành vi
- "User xem → thích → mua" (funnel)
- Quan trọng để dự đoán hành vi mục tiêu

---

**Hình minh họa:**

```
Ví dụ sequence:  [iPhone(PV), SamS24(PV), iPhone(Cart), AirPods(PV), iPhone(Pur)]

                                    Intra-type (PV→PV)
                                    iPhone(SamS24)
                                        ↓
Intra-type (Cart→Cart)                PV→Cart
iPhone(Cart) ─────────────────────────→ iPhone(PV)
                                        ↓
                                    Intra-type (PV→PV)
                                        ↓
                                    AirPods(PV)
                                        ↓
                                    Pur→PV
                                        ↓
                                    iPhone(Pur)
```

---

### 1.7 Graph Neural Network (GNN) - Mạng Neural Đồ thị

**Định nghĩa:**
GNN là loại mạng neural hoạt động trên **cấu trúc đồ thị** (graph), thay vì chuỗi hay hình ảnh.

**Tại sao dùng GNN?**
- Items có mối quan hệ với nhau (không phải chuỗi)
- Dễ dàng biểu diễn "A mua với B"
- Truyền tải thông tin giữa các nodes

**Các khái niệm trong GNN:**

| Khái niệm | Tiếng Việt | Ý nghĩa |
|----------|------------|----------|
| Node | Đỉnh | Điểm trong đồ thị (ví dụ: item) |
| Edge | Cạnh | Đường nối giữa 2 nodes |
| Neighbor | Hàng xóm | Các nodes kết nối với node hiện tại |
| Message passing | Truyền tin | Cách nodes trao đổi thông tin |

**Ví dụ simple:**
```
Item Graph:
iPhone ──────Samsung
  │              │
  │              │
AirPods────────Case

iPhone có neighbors: Samsung, AirPods, Case
```

**Vai trò trong GHTID:**
- Xây dựng đồ thị item-item
- Học representations của items
- Truyền tải thông tin từ neighbors

---

### 1.8 Attention Mechanism - Cơ chế Chú ý

**Định nghĩa:**
Attention Mechanism cho phép model **tập trung** vào những phần quan trọng của dữ liệu, giống như con người chú ý vào điều gì đó.

**Ý tưởng:**
- Không phải neighbor nào cũng quan trọng như nhau
- Attention weights = mức độ quan trọng
- Tự động học weights từ dữ liệu

**Ví dụ:**
```
Sequence: [iPhone(PV), SamS24(PV), Xiaomi(PV), Case(PV), iPhone(Pur)]

Attention weights:
- iPhone (PV): 0.4 (quan trọng, liên quan đến mua cuối cùng)
- SamS24 (PV): 0.1 
- Xiaomi (PV): 0.1
- Case (PV): 0.2 
- iPhone (Pur): 0.2 (mua rồi)
```

---

### 1.9 Embedding - Biểu diễn Vector

**Định nghĩa:**
Embedding là cách biểu diễn items/users dưới dạng **vector số** (dãy các con số) để máy tính có thể xử lý.

**Ví dụ:**
```
Item "iPhone 15" → [0.12, -0.34, 0.56, 0.89, -0.23, ...] (64 chiều)
Item "Samsung S24" → [0.45, 0.12, -0.67, 0.34, 0.78, ...] (64 chiều)
```

**Tại sao cần embedding?**
- Máy tính chỉ hiểu số
- Items có embedding gần nhau = similar items
- Dùng trong mọi tính toán

---

## Phần 2: HAI THÁCH THỨC CHÍNH

### 2.1 Thách thức 1: Heterogeneous Item Transitions

**Mô tả vấn đề:**
- Các nghiên cứu trước không mô hình hóa rõ ràng các chuyển đổi Intra-type và Cross-type
- Bỏ qua thông tin từ users khác (global perspective)

**Tại sao quan trọng:**
- Mỗi user có pattern chuyển đổi khác nhau
- Cần học cả 2 loại transitions
- Cần cả global (tất cả users) và local (user cụ thể)

---

### 2.2 Thách thức 2: Interference from Auxiliary Behaviors

**Mô tả vấn đề:**
- Trước khi mua (target), user xem rất nhiều items (auxiliary)
- Các auxiliary behaviors chứa thông tin không liên quan hoặc ngược ý

**Ví dụ:**
```
User mua iPhone 15 Pro (Pur)
Nhưng trước đó đã xem:
- 20 điện thoại Android (không liên quan)
- 15 tablet (không liên quan)  
- 10 laptop (không liên quan)
→ 45 items = NHIỄU!
```

**Cách GHTID giải quyết:**
- Target Behavior Mask: chỉ lấy thông tin liên quan đến Pur
- Interest Aggregation: tổng hợp sở thích từ target behavior

---

## Phần 3: KIẾN TRÚC GHTID

### 3.1 Tổng quan

```
┌───────────────────────────────────��─��───────────────────────────┐
│                          GHTID                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │            INPUT: Multi-behavior Sequence                 │    │
│  │  [(iP, PV), (Sam, PV), (iP, Cart), (Air, PV), (iP, Pur)]│    │
│  └──────────────────────────────────────────────────────────┘    │
│                              ↓                                    │
│  ┌────────────────┐    ┌────────────────┐    ┌────────────┐    │
│  │ Global Graph   │    │ Local Graph   │    │   IAM     │    │
│  │ Convolution  │ +  │ Convolution  │ +  │(Interest  │    │
│  │  Module     │    │  Module     │    │ Aggregation)│   │
│  └────────────────┘    └────────────────┘    └────────────┘    │
│         ↓                      ↓                    ↓                │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │           Fuse Global + Local + Interest                  │    │
│  └──────────────────────────────────────────────────────────┘    │
│                              ↓                                    │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │              Predict: Score for Next Item                   │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**3 Module chính:**
1. **Global Graph Convolution Module (GG)**: Đồ thị toàn cục
2. **Local Graph Convolution Module (LG)**: Đồ thị cục bộ
3. **Interest Aggregation Module (IAM)**: Tổng hợp sở thích

---

### 3.2 Global Graph Convolution Module (GG)

**Mục đích:** Học mối quan hệ **đồng xuất hiện** (co-occurrence) giữa các items từ **tất cả users**.

**Tại sao gọi là "Global"?**
- Từ tất cả users trong dataset
- Không phải của một user cụ thể
- Đại diện cho kiến thức chung

---

#### 3.2.1 Global Item-Item Co-occurrence Graph

**Định nghĩa:**
Đồ thị G_g = {V_g, E_g}:
- V_g = tất cả items trong dataset
- E_g = cạnh với trọng số PMI (co-occurrence)

**Ý tưởng:**
Nếu nhiều users cùng mua/xem 2 items A và B với nhau, thì A và B có liên quan.

**Ví dụ:**
```
Global Graph (một phần):
iPhone ─── Samsung (PMI cao, nhiều người mua c��� 2)
  │
  │
AirPods (PMI trung bình)

iPhone ─── Nokia (PMI thấp, ít người mua cả 2)
```

---

#### 3.2.2 PMI (Pointwise Mutual Information)

**Định nghĩa:**
PMI đo độ **liên quan** giữa 2 items dựa trên xác suất đồng xuất hiện.

**Công thức:**
```
PMI(A, B, x→y) = log[ P(A,B | x→y) / (P(A|x) × P(B|y)) ]
```

**Giải thích:**
- P(A,B | x→y): Xác suất A và B xuất hiện với hành vi x→y
- P(A|x): Xác suất A xuất hiện với hành vi x
- P(B|y): Xác suất B xuất hiện với hành vi y

**Ý nghĩa:**
- PMI > 0: Items thực sự liên quan (nhiều người mua cùng)
- PMI < 0: Items không liên quan (ngẫu nhiên)
- Chỉ giữ cạnh có PMI > 0

---

#### 3.2.3 Item-to-Relationship Message Passing

**Mục đích:** Tạo messages riêng cho từng loại **edge type** (quan hệ).

**Các loại quan hệ:**
- PV → PV
- PV → Cart
- PV → Pur
- Cart → Cart
- Cart → Pur
- Pur → Pur
- etc.

**Công thức:**
```
m^(l)(v_i, r) = Σ [ (w_ij × q^(l-1)(v_j)) / w_i ] / |N_r(v_i)|
```

**Giải thích:**
- w_ij = trọng số PMI
- q^(l-1)(v_j) = embedding của item v_j
- N_r(v_i) = tất cả neighbors có quan hệ r
- m^(l)(v_i, r) = message tổng hợp

**Tác dụng:**
- Mỗi loại quan hệ tạo ra message riêng
- Giữ thông tin về loại chuyển đổi

---

#### 3.2.4 Relationship-to-Item Aggregation

**Mục đích:** Tổng hợp các messages từ tất cả các loại quan hệ.

**Công thức:**
```
π(v_i, r) = a^T × LeakyReLU( W_r × [p^(l-1)(v_i) || m^(l)(v_i, r)] )
α(v_i, r) = exp(π(v_i, r)) / Σ exp(π(v_i, k))
p^(l)(v_i) = Σ [ α(v_i, k) × m^(l)(v_i, k) ]
```

**Giải thích:**
- Attention mechanism để học trọng số
- α(v_i, r) = trọng số cho quan hệ r
- p^(l)(v_i) = representation cuối cùng

**Tác dụng:**
- Tự động học tầm quan trọng của từng loại quan hệ
- Kết hợp tất cả thông tin

---

### 3.3 Local Graph Convolution Module (LG)

**Mục đích:** Học mối **chuyển đổi** giữa các items từ **góc nhìn của một user cụ thể**.

**Tại sao gọi là "Local"?**
- Chỉ của một user cụ thể
- Cá nhân hóa (personalized)
- Phản ánh preference riêng

---

#### 3.3.1 Local Item-Item Transition Graph

**Định nghĩa:**
Đồ thị G_s = {V_s, E_s} cho một user:
- V_s = items xuất hiện trong sequence của user đó
- E_s = cạnh với thứ tự

**Đặc biệt:**
- Có thứ tự: A → B nghĩa là user xem A trước, B sau
- Xem xét cả hướng (+/-)

**Ví dụ cho 1 user:**
```
Sequence: [iPhone(PV), Sam(PV), iPhone(Cart), AirPods(PV), iPhone(Pur)]

Local Graph:
iPhone(PV) ───Sam(PV) ───iPhone(Cart)───AirPods(PV)───iPhone(Pur)
    A            B            C              D              E
```

---

#### 3.3.2 Behavior-aware Attention

**Đây là điểm khác biệt quan trọng của LG**

**Ý tưởng:**
- Quan hệ (PV → Cart) khác với (Cart → Pur)
- Attention weights khác nhau cho từng cặp behavior

**Công thức:**
```
π(v_i, v_j) = a^T_rij × LeakyReLU( [W1 × q^(l-1)(v_i) || W2 × q^(l-1)(v_j)] )
attn(v_i, v_j) = exp(π(v_i, v_j)) / Σ exp(π(v_i, v_k))
```

**Giải thích:**
- a^T_rij = vector trọng số cho cặp (ri, j)
- W1, W2 = ma trận projection
- attn = attention weight

**Tại sao "Behavior-aware"?**
- Cặp (PV → Pur): "đang chuyển từ xem sang mua" → quan trọng!
- Cặp (PV → PV): "chỉ đang xem" → ít quan trọng hơn

---

### 3.4 Interest Aggregation Module (IAM)

**Mục đích:** Giải quyết vấn đề **nhiễu từ auxiliary behaviors**.

**Đây là module quan trọng nhất để giảm nhiễu!**

---

#### 3.4.1 Target Behavior Mask (Mặt nạ Hành vi Mục tiêu)

**Định nghĩa:**
M = (m_1, m_2, ..., m_n)

- m_i = 1 nếu behavior = target (Pur)
- m_i = 0 nếu behavior = auxiliary (PV, Cart, Fav)

**Ví dụ:**
```
Sequence: [(A, PV), (B, Pur), (C, PV), (D, Pur)]
Mask M:    [ 0,     1,     0,     1]
```

**Tác dụng:**
- Chỉ lấy items có target behavior
- Lọc bỏ nhiễu

---

#### 3.4.2 Target Short-Term Interest Aggregation

**Định nghĩa:**
Short-term interest = sở thích **gần đây** (item cuối cùng)

**Ý tưởng:**
- Dùng item cuối cùng làm query
- Tìm các items có target behavior **liên quan**

**Công thức:**
```
q_short = h_(v_n)  // Item cuối cùng
α_i = a^T_short × σ( W4 × q_short + W5 × h_(v_i) + b1 )
h_short^s = Σ ( m_i × α_i × h_(v_i) )
```

**Giải thích:**
- q_short = query vector
- α_i = attention weights
- m_i = mask (chỉ lấy target)
- h_short^s = short-term representation

**Ví dụ:**
```
Sequence: [iPhone(xem), Sam(xem), Xiaomi(xem), iPhone(mua)]
Query: iPhone(mua) → attention vào các items có mua
Output: h_skip có thông tin "user đang mua iPhone"
```

**Vai trò:**
- Nắm bắt sở thích hiện tại
- Giảm nhiễu từ PV

---

#### 3.4.3 Target Long-Term Interest Aggregation

**Định nghĩa:**
Long-term interest = sở thích **tổng quát** (tất cả target items trong quá khứ)

**Ý tưởng:**
- Dùng trung bình của tất cả target items
- Phản ánh sở thích chung

**Công thức:**
```
q_long = (1/n) × Σ ( m_i × h_(v_i) )
β_i = a^T_long × σ( W6 × q_long + W7 × h_(v_i) + b2 )
h_long^s = Σ ( β_i × h_(v_i) )
```

**Ví dụ:**
```
3 tháng qua:
- User mua: iPhone, iPad, MacBook, AirPods
→ Long-term: "User thích Apple ecosystem"
```

**Vai trò:**
- Sở thích tổng quát (brand, price range, category)
- Ổn định theo thời gian

---

#### 3.4.4 Interest Fusion

**Định nghĩa:**
Kết hợp short-term và long-term interests thành **một representation cuối cùng**.

**Công thức:**
```
h^s = LeakyReLU( W8 × [h_short^s || h_long^s] )
```

**Giải thích:**
- [h_short || h_long] = nối 2 vectors
- W8 = weights của MLP

**Sự kết hợp:**
- Short-term: "User đang tìm iPhone Pro Max"
- Long-term: "User thích Apple, giá trên 20 triệu"
- **Fusion**: "Gợi iPhone 15 Pro Max 256GB"

---

### 3.5 Fusion: Global + Local + Interest

**Công thức:**
```
h^v_i = ReLU( W3 × [Dropout(h^v_g_i) || h^v_s_i] )
```

**Giải thích:**
- h^v_g_i = representation từ Global Graph (kiến thức chung)
- h^v_s_i = representation từ Local Graph (preference riêng)
- Dropout = tránh overfitting

---

### 3.6 Prediction Layer

**Mục đích:** Dự đoán xác suất user sẽ tương tác với một item.

**Công thức:**
```
y_(s,i,b) = h^s^T × (h^s ⊙ h^b)
```

**Giải thích:**
- ⊙ = element-wise product
- h^b = behavior vector
- Score càng cao = khả năng mua càng lớn

---

## Phần 4: DATASETS VÀ KẾT QUẢ

### 4.1 Các Datasets

| Dataset | Mô tả | #Users | #Items | Behaviors |
|--------|-------|--------|--------|-----------|
| ML1M | MovieLens 1M (phim) | 5,645 | 2,357 | Exam, Like |
| UB | UserBehaviors (Alibaba) | 20,858 | 30,793 | PV, Cart, Fav, Pur |
| Rec15 | RecSys Challenge 2015 | 36,917 | 9,621 | Click, Purchase |
| Tmall | Tmall (e-commerce) | 17,209 | 16,177 | PV, Fav, Pur |

### 4.2 Các Baseline Methods

**Single-behavior Methods:**
- FPMC, TransRec, SASRec, TiSASRec, GCEGNN

**Multi-behavior Methods:**
- TransRec++, DMT, MGNN-Spred, M-SR, MBSTR, GPG4HSR

### 4.3 Kết quả

| Dataset | GHTID HR@10 | Best Baseline | Improvement |
|---------|-------------|---------------|-------------|
| ML1M | **0.1663** | 0.1460 (GPG4HSR) | +13.90% |
| UB | **0.1124** | 0.0904 (MBSTR) | +23.34% |
| Rec15 | **0.5081** | 0.4315 (M-SR) | +19.86% |
| Tmall | **0.1115** | 0.0944 (GPG4HSR) | +18.11% |

**Kết luận:** GHTID luôn đạt kết quả tốt nhất!

---

## Phần 5: BẢNG THUẬT NGỮ ANH-VIỆT

| Thuật ngữ | Tiếng Anh | Tiếng Việt |
|----------|-----------|------------|
| SRS | Sequential Recommendation System | Hệ thống gợi ý tuần tự |
| MBSR | Multi-behavior Sequential Recommendation | Gợi ý tuần tự đa hành vi |
| TB | Target Behavior | Hành vi mục tiêu |
| AB | Auxiliary Behavior | Hành vi phụ |
| HIT | Heterogeneous Item Transitions | Chuyển đổi item không đồng nhất |
| ITT | Intra-type Transition | Chuyển đổi cùng loại |
| CTT | Cross-type Transition | Chuyển đổi liên loại |
| GNN | Graph Neural Network | Mạng neural đồ thị |
| GG | Global Graph | Đồ thị toàn cục |
| LG | Local Graph | Đồ thị cục bộ |
| IAM | Interest Aggregation Module | Module tổng hợp sở thích |
| STI | Short-term Interest | Sở thích ngắn hạn |
| LTI | Long-term Interest | Sở thích dài hạn |
| PMI | Pointwise Mutual Information | Thông tin tương hỗ điểm |
| Attention | Attention Mechanism | Cơ chế chú ý |
| Embedding | Embedding | Biểu diễn vector |
| Mask | Target Behavior Mask | Mặt nạ hành vi mục tiêu |
| Fusion | Interest Fusion | Hợp nhất sở thích |
| HR@N | Hit Ratio at N | Tỷ lệ truy cập |
| NDCG@N | Normalized DCG at N | DCG chuẩn hóa |

---

## Phần 6: TÓM TẮT CÁC ĐÓNG GÓP

### Đóng góp 1: Global + Local Graphs
- Đồ thị đồng xuất hiện toàn cục (tất cả users)
- Đồ thị chuyển đổi cục bộ (user cụ thể)

### Đóng góp 2: Interest Aggregation
- Tổng hợp sở thích từ target behavior
- Short-term + Long-term interest
- Giảm nhiễu từ auxiliary

### Đóng góp 3: Hiệu quả
- Vượt trội trên 4 datasets
- Robust với nhiễu

---

## TÀI LIỆU THAM KHẢO

Paper gốc: [WSDM '24](https://doi.org/10.1145/3616855.3635857)