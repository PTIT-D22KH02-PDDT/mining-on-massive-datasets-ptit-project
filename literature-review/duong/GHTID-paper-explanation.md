# GHTID: Global Heterogeneous Graph and Target Interest Denoising for Multi-behavior Sequential Recommendation

## Giới thiệu về Paper

Đây là paper được công bố tại hội nghị **WSDM '24** (17th ACM International Conference on Web Search and Data Mining) bởi các tác giả từ Đại học Tianjin, Trung Quốc. Paper đề xuất một phương pháp mới gọi là **GHTID** để giải quyết bài toán **Multi-behavior Sequential Recommendation (MBSR)** - tức dự đoán sản phẩm tiếp theo mà người dùng sẽ tương tác, dựa trên lịch sử tương tác với nhiều loại hành vi khác nhau.

---

## 1. Các Khái niệm Nền tảng (Definitions)

### 1.1. Sequential Recommendation (SR) - Hệ thống Gợi ý Tuần tự

**Định nghĩa đơn giản:**
Hệ thống gợi ý tuần tự là hệ thống dự đoán sản phẩm tiếp theo mà người dùng có thể quan tâm, dựa trên thứ tự các sản phẩm mà người dùng đã tương tác trước đó.

**Ví dụ thực tế:**
Khi bạn mua sắm trên Amazon, nếu bạn đã xem: Điện thoại → Tai nghe → Ốp lưng, hệ thống sẽ dự đoán bạn có thể muốn mua thêm sạc dự phòng.

**Tác dụng/Vai trò:**
- Giúp người dùng tìm thấy sản phẩm phù hợp nhanh hơn
- Tăng doanh thu cho nền tảng thương mại điện tử
- Cải thiện trải nghiệm người dùng

### 1.2. Multi-behavior Sequential Recommendation (MBSR) - Gợi ý Tuần tự Đa hành vi

**Định nghĩa đơn giản:**
Khác với SR truyền thống chỉ xem xét một loại hành vi (ví dụ: chỉ mua hàng), MBSR xem xét **nhiều loại hành vi** khác nhau mà người dùng có thể thực hiện với sản phẩm.

**Các loại hành vi phổ biến:**
| Loại hành vi | Ký hiệu | Ý nghĩa |
|-------------|---------|---------|
| Page View (PV) | PV | Người dùng chỉ xem sản phẩm |
| Add to Cart | Cart | Thêm vào giỏ hàng |
| Add to Favorite | Fav | Thêm vào danh sách yêu thích |
| Purchase (Pur) | Pur | Mua hàng (đây thường là hành vi mục tiêu) |

**Ví dụ thực tế:**
- Bạn vào trang Amazon, xem (PV) nhiều điện thoại
- Bạn thêm (Cart) 2 cái vào giỏ hàng
- Bạn thêm (Fav) 1 cái vào danh sách yêu thích
- Cuối cùng bạn mua (Pur) 1 cái

**Tác dụng/Vai trò:**
- Cung cấp thông tin phong phú hơn về sở thích người dùng
- PV (xem) cho biết người dùng đang cân nhắc gì
- Cart (thêm giỏ) cho biết người dùng thực sự quan tâm
- Pur (mua) cho biết ý định thực sự

### 1.3. Target Behavior - Hành vi Mục tiêu

**Định nghĩa đơn giản:**
Hành vi mục tiêu là hành vi có giá trị cao nhất đối với doanh nghiệp - thường là hành vi **Purchase (mua hàng)**.

**Tại sao quan trọng:**
- Mua hàng = doanh thu trực tiếp
- Các hành vi khác (xem, thêm giỏ) chỉ là bước trung gian

**Tác dụng/Vai trò:**
- GHTID tập trung vào việc dự đoán hành vi mục tiêu
- Các hành vi khác (PV, Cart, Fav) được coi là "hành vi phụ" để hỗ trợ dự đoán

### 1.4. Auxiliary Behaviors - Hành vi Phụ/Auxiliary

**Định nghĩa đơn giải:**
Là các hành vi không phải mục tiêu - ví dụ Page View (xem), Favorite (yêu thích), Cart (giỏ hàng).

**Vấn đề với Auxiliary Behaviors:**
- Người dùng có thể xem rất nhiều sản phẩm nhưng chỉ muốn vài cái
- Thông tin nhiễu (noise) từ các hành vi phụ có thể làm giảm độ chính xác

**Ví dụ:**
Bạn xem 50 điện thoại nhưng chỉ mua 1 cái. Nếu đưa cả 50 vào model, có thể gây nhiễu.

### 1.5. Heterogeneous Item Transitions - Chuyển đổi Mục Item Không đồng nhất

**Định nghĩa đơn giản:**
Đây là **khái niệm cốt lõi** của paper. Nó mô tả mối quan hệ/chuyển đổi giữa các sản phẩm dựa trên loại hành vi.

**Có 2 loại chuyển đổi:**

#### a) Intra-type Transition (Chuyển đổi Cùng loại)
- PV → PV: Từ sản phẩm xem này sang sản phẩm xem khác
- Pur → Pur: Từ sản phẩm mua này sang sản phẩm mua khác

**Ví dụ thực tế:**
Bạn xem iPhone 15 → Xem Samsung S24 (cùng loại PV)

#### b) Cross-type Transition (Chuyển đổi Liên loại)
- PV → Pur: Từ sản phẩm xem sang sản phẩm mua
- Pur → PV: Từ sản phẩm mua sang sản phẩm xem (mua xong lại xem thêm)
- PV → Cart: Từ xem sang thêm giỏ

**Tại sao quan trọng:**
- Intra-type: Cho biết sở thích trong cùng loại hành vi
- Cross-type: Cho biết mối liên hệ giữa các hành vi (xem nhiều → mua cái nào?)

**Vai trò trong GHTID:**
GHTID xây dựng đồ thị để học cả 2 loại chuyển đổi này.

---

## 2. Hai Thách thức Chính (Challenges)

### 2.1. Thách thức 1: Heterogeneous Item Transitions (Chuyển đổi Item không đồng nhất)

**Mô tả vấn đề:**
Các nghiên cứu trước đây:
- Không mô hình hóa rõ ràng các chuyển đổi giữa các loại hành vi
- Bỏ qua thông tin từ người dùng khác (global perspective)

**Tác dụng/Vai trò của việc giải quyết:**
- Học được mối quan hệ phức tạp giữa các sản phẩm
- Nắm bắt được pattern hành vi của từng người dùng

### 2.2. Thách thức 2: Interference of Auxiliary Behaviors (Nhiễu từ hành vi phụ)

**Mô tả vấn đề:**
- Trước khi thực hiện hành vi mục tiêu (mua), người dùng có thể xem rất nhiều sản phẩm (PV)
- Các hành vi phụ có thể chứa thông tin không liên quan hoặc thậm chí **trái ngược** với sở thích cuối cùng

**Ví dụ:**
Bạn xem: Áo sơ mi → Quần jean → Giày → Nón → Túi xách → Áo phông (50 items)
Nhưng bạn chỉ mua: Áo phông

→ Nếu đưa cả 50 items vào model, thông tin về 49 items kia là **nhiễu**

**Tác dụng/Vai trò của việc giải quyết:**
- Lọc bỏ thông tin nhiễu
- Tập trung vào tín hiệu liên quan đến hành vi mục tiêu

---

## 3. Kiến trúc Model GHTID

### 3.1. Tổng quan Kiến trúc

```
┌─────────────────────────────────────────────────────────────┐
│                        GHTID                                 │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │ Global Graph │    │  Local Graph │    │    IAM       │   │
│  │ Convolution  │    │  Convolution │    │(Interest     │   │
│  │   Module     │ +  │   Module     │ +  │ Aggregation) │   │
│  └──────────────┘    └──────────────┘    └──────────────┘   │
├─────────────────────────────────────────────────────────────┤
│                      Final Output                           │
│                   (User Interest)                           │
└─────────────────────────────────────────────────────────────┘
```

GHTID gồm **3 module chính**:
1. **Global Graph Convolution Module (GG)**: Học đại diện item ở mức toàn cục
2. **Local Graph Convolution Module (LG)**: Học đại diện item ở mức cục bộ (theo từng user)
3. **Interest Aggregation Module (IAM)**: Tổng hợp sở thích từ hành vi mục tiêu

---

## 4. Chi tiết từng Module

### 4.1. Global Graph Convolution Module (GG)

**Mục đích:** Học mối quan hệ đồng xuất hiện (co-occurrence) giữa các sản phẩm từ **góc nhìn toàn cục** (tất cả người dùng).

#### 4.1.1. Global Item-Item Co-occurrence Graph (Đồ thị đồng xuất hiện Item-Item toàn cục)

**Định nghĩa:**
- **Đồ thị G_g = {V_g, E_g}**
- V_g = tất cả các item
- E_g = cạnh giữa các item với trọng số là hệ số đồng xuất hiện

**Ý tưởng:**
Nếu nhiều người dùng cùng xem (hoặc mua) 2 sản phẩm A và B với nhau, thì A và B có liên quan.

**Công thức đo độ đồng xuất hiện (PMI - Pointwise Mutual Information):**

```
PMI(A, B, x→y) = log[ P(A,B | x→y) / (P(A|x) × P(B|y)) ]
```

**Giải thích đơn giản:**
- P(A,B | x→y): Xác suất A và B xuất hiện cùng nhau với hành vi x→y
- P(A|x): Xác suất A xuất hiện với hành vi x
- P(B|y): Xác suất B xuất hiện với hành vi y

**Tại sao dùng PMI?**
- PMI cao → 2 items thực sự liên quan
- PMI âm → 2 items không liên quan hoặc trùng lặp ngẫu nhiên
- GHTID chỉ giữ lại cạnh có PMI > 0

#### 4.1.2. Item-to-Relationship (Từ Item đến Relationship)

**Mục đích:** Tạo messages (tin nhắn) cho từng loại edge (quan hệ) khác nhau.

**Công thức:**
```
m^(l)(v_i, r) = Σ [ (w_ij × q^(l-1)(v_j)) / w_i ] / |N_r(v_i)|
```

**Giải thích:**
- w_ij = trọng số đồng xuất hiện
- q^(l-1)(v_j) = đại diện của item v_j ở layer trước
- N_r(v_i) = các neighbor của v_i theo relation r
- m^(l)(v_i, r) = message tổng hợp cho v_i với relation r

**Tác dụng:**
- Mỗi loại quan hệ (PV→Pur, PV→PV, etc.) tạo ra một message riêng
- Giữ được thông tin về loại chuyển đổi

#### 4.1.3. Relationship-to-Item (Từ Relationship đến Item)

**Mục đích:** Tổng hợp các messages từ các loại quan hệ khác nhau.

**Công thức:**
```
π(v_i, r) = a^T × LeakyReLU( W_r × [p^(l-1)(v_i) || m^(l)(v_i, r)] )
α(v_i, r) = exp(π(v_i, r)) / Σ exp(π(v_i, k))

p^(l)(v_i) = Σ [ α(v_i, k) × m^(l)(v_i, k) ]
```

**Giải thích:**
- Sử dụng **Attention Mechanism** (cơ chế chú ý)
- α(v_i, r) = trọng số attention cho relation r
- p^(l)(v_i) = đại diện cuối cùng của item v_i

**Tác dụng/Vai trò:**
- Tự động học tầm quan trọng của từng loại quan hệ
- Trọng số cao = quan hệ đó quan trọng hơn cho item này

---

### 4.2. Local Graph Convolution Module (LG)

**Mục đích:** Học mối chuyển đổi giữa các items từ **góc nhìn cục bộ** (theo từng user riêng biệt).

#### 4.2.1. Local Item-Item Transition Graph (Đồ thị chuyển đổi cục bộ)

**Định nghĩa:**
- Đồ thị G_s = {V_s, E_s}
- V_s = items xuất hiện trong sequence của một user cụ thể
- E_s = cạnh giữa các items với thứ tự

**Đặc điểm:**
- Khác với Global Graph (tất cả users), Local Graph chỉ cho **một user**
- Có thứ tự: x → y có nghĩa là user xem A trước, sau đó xem B

**Các loại quan hệ:**
- x → y (+): User tương tác với x trước, rồi tương tác với y
- x → y (-): Ngược lại (trong một số trường hợp)

#### 4.2.2. Behavior-aware Attention (Cơ chế Chú ý nhận biết hành vi)

**Đây là điểm khác biệt quan trọng của Local Graph**

**Công thức:**
```
π(v_i, v_j) = a^T_rij × LeakyReLU( [W1 × q^(l-1)(v_i) || W2 × q^(l-1)(v_j)] )
attn(v_i, v_j) = exp(π(v_i, v_j)) / Σ exp(π(v_i, v_k))
```

**Giải thích:**
- W1, W2 = ma trận projection cho source và target
- a^T_rij = vector trọng số phụ thuộc vào loại quan hệ rij
- attn(v_i, v_j) = mức độ quan trọng của neighbor v_j đối với v_i

**Tại sao gọi là "Behavior-aware"?**
- Cặp (PV → Pur) có cách tính attention riêng
- Cặp (Pur → PV) có cách tính khác
- Mỗi cặp hành vi khác nhau → attention weights khác nhau

**Tác dụng/Vai trò:**
- Phân biệt tầm quan trọng của các items dựa trên loại hành vi
- Học được pattern riêng của từng user

---

### 4.3. Interest Aggregation Module (IAM)

**Mục đích:** Giải quyết vấn đề **nhiễu từ auxiliary behaviors** bằng cách tập trung vào tín hiệu từ **target behavior**.

#### 4.3.1. Target Behavior Mask (Mặt nạ hành vi mục tiêu)

**Định nghĩa:**
M = (m_1, m_2, ..., m_n) where:
- m_i = 1 nếu behavior của item thứ i là target behavior (Pur)
- m_i = 0 nếu là auxiliary behavior (PV, Cart, Fav)

**Ví dụ:**
```
Sequence: [(ItemA, PV), (ItemB, Pur), (ItemC, PV), (ItemD, Pur)]
Mask M:    [0,          1,          0,          1]
```

#### 4.3.2. Target Short-Term Interest Aggregation (Tổng hợp sở thích ngắn hạn)

**Ý tưởng:**
- **Short-term interest** = sở thích gần đây (item cuối cùng)
- Dùng item cuối cùng làm "query" để tìm các items liên quan có target behavior

**Công thức:**
```
q_short = h_(v_n)  // Item cuối cùng làm query

α_i = a^T_short × σ( W4 × q_short + W5 × h_(v_i) + b1 )
h_short^s = Σ ( m_i × α_i × h_(v_i) )
```

**Giải thích:**
- q_short = vector của item cuối cùng
- α_i = trọng số attention cho item thứ i
- m_i = mask (chỉ lấy items có target behavior)
- h_short^s = representation cuối cùng của short-term interest

**Tác dụng/Vai trò:**
- Tìm các items có target behavior liên quan đến item gần nhất
- Giảm nhiễu từ auxiliary behaviors

#### 4.3.3. Target Long-Term Interest Aggregation (Tổng hợp sở thích dài hạn)

**Ý tưởng:**
- **Long-term interest** = sở thích tổng quát (tất cả items với target behavior)
- Dùng trung bình của tất cả target behavior items làm query

**Công thức:**
```
q_long = (1/n) × Σ ( m_i × h_(v_i) )  // Trung bình các items target

β_i = a^T_long × σ( W6 × q_long + W7 × h_(v_i) + b2 )
h_long^s = Σ ( β_i × h_(v_i) )
```

**Giải thích:**
- q_long = trung bình các items có target behavior
- β_i = trọng số attention cho item thứ i
- h_long^s = representation cuối cùng của long-term interest

**Tác dụng/Vai trò:**
- Nắm bắt sở thích tổng quát của user về target behavior
- Ví dụ: User này thường mua điện thoại giá rẻ

#### 4.3.4. Interest Fusion (Hợp nhất sở thích)

**Ý tưởng:**
- Kết hợp short-term và long-term interest
- MLP (Multi-Layer Perceptron) học cách kết hợp

**Công thức:**
```
h^s = LeakyReLU( W8 × [h_short^s || h_long^s] )
```

**Giải thích:**
- [h_short^s || h_long^s] = concatenation của 2 vectors
- W8 = ma trận weights của MLP
- h^s = representation cuối cùng của user interest

**Tác dụng/Vai trò:**
- Long-term: "User này thích thương hiệu Apple"
- Short-term: "User đang tìm điện thoại dưới 10 triệu"
- Fusion: Kết hợp cả 2 để gợi ý iPhone giá rẻ!

---

## 5. Prediction Layer (Tầng Dự đoán)

**Mục đích:** Dự đoán xác suất user sẽ tương tác với một item dưới target behavior.

**Công thức:**
```
y_(s,i,b) = h^s^T × (h^s ⊙ h^b)
Score của item v_i dưới behavior b
```

**Training với Cross-Entropy Loss:**
```
Loss = - (1/|O|) × Σ log[ exp(y_(s,i,b)) / Σ exp(y_(s,j,b)) ]
```

**Tác dụng/Vai trò:**
- Học để score của item đúng (positive) cao hơn items khác
- Tối ưu hóa để ranking đúng thứ tự

---

## 6. Fusion của Global và Local Representations

**Công thức:**
```
h^v_i = ReLU( W3 × [Dropout(h^v_g_i) || h^v_s_i] )
```

**Giải thích:**
- h^v_g_i = representation từ Global Graph
- h^v_s_i = representation từ Local Graph  
- Dropout = kỹ thuật regularization để tránh overfitting

**Tác dụng/Vai trò:**
- Global: "Users khác thường mua iPhone với AirPods"
- Local: "User này đang xem iPhone 15"
- Fusion: "User này có thể thích AirPods vì nhiều người mua chung"

---

## 7. Datasets trong Experiments

### 7.1. Các Dataset được sử dụng

| Dataset | #Users | #Items | Behavior Types | #Interactions |
|---------|--------|--------|---------------|--------------|
| ML1M | 5,645 | 2,357 | Exam, Like | 628,892 |
| UB | 20,858 | 30,793 | Page View, Cart, Favorite, Purchase | 85,910 |
| Rec15 | 36,917 | 9,621 | Click, Purchase | 446,442 |
| Tmall | 17,209 | 16,177 | Page View, Favorite, Purchase | 831,117 |

### 7.2. Mô tả Dataset

**ML1M (MovieLens 1M):**
- Dataset phim ảnh
- Exam = xem phim, Like = thích phim
- Target behavior: Like

**UB (UserBehaviors):**
- Dataset hành vi người dùng từ Alibaba
- 4 loại hành vi: PV, Cart, Fav, Pur
- Target behavior: Purchase

**Rec15:**
- Dataset từ ACM RecSys Challenge 2015
- 2 loại hành vi: Click, Purchase
- Target behavior: Purchase

**Tmall:**
- Dataset từ nền tảng Tmall
- 3 loại hành vi: PV, Fav, Pur
- Target behavior: Purchase

---

## 8. Kết quả Experiments

### 8.1. Các Phương pháp so sánh (Baselines)

#### Single-behavior Methods (chỉ dùng 1 loại hành vi):
- **FPMC**: Factorized Personalized Markov Chain
- **TransRec**: Translation-based Recommendation
- **SASRec**: Self-Attentive Sequential Recommendation
- **TiSASRec**: Time Interval Aware Sequential Recommendation
- **GCEGNN**: Global Context Enhanced Graph Neural Network

#### Multi-behavior Methods (dùng nhiều loại hành vi):
- **TransRec++**: Mở rộng TransRec cho multi-behavior
- **DMT**: Deep Multi-behavior Transformer
- **MGNN-Spred**: Multi-relational Graph Neural Network
- **M-SR**: Multi-behavior Sequential Recommendation
- **MBSTR**: Multi-behavior Sequential Transformer
- **GPG4HSR**: Global Personalized Graph for Heterogeneous Sequential Recommendation

### 8.2. Kết quả chính

| Dataset | GHTID HR@10 | Best Baseline HR@10 | Improvement |
|---------|-------------|---------------------|-------------|
| ML1M | 0.1663 | 0.1460 (GPG4HSR) | +13.90% |
| UB | 0.1124 | 0.0904 (MBSTR) | +23.34% |
| Rec15 | 0.5081 | 0.4315 (M-SR) | +19.86% |
| Tmall | 0.1115 | 0.0944 (GPG4HSR) | +18.11% |

**Nhận xét:**
- GHTID luôn đạt kết quả tốt nhất trên tất cả 4 datasets
- Cải thiện đáng kể trên tất cả các metrics

### 8.3. Ablation Study (Nghiên cứu loại bỏ)

**Thí nghiệm loại bỏ từng module:**

| Variant | Mô tả | Kết quả |
|---------|-------|---------|
| GHTID w/o GG | Không có Global Graph | Performance giảm đáng kể |
| GHTID w/o LG | Không có Local Graph | Performance giảm |
| GHTID w/o IAM | Không có Interest Aggregation | Performance giảm nhiều nhất |
| GHTID (đầy đủ) | Tất cả modules | Kết quả tốt nhất |

**Kết luận:**
- Mỗi module đều đóng góp vào hiệu suất cuối cùng
- IAM có tác động lớn nhất (giải quyết vấn đề nhiễu)

### 8.4. Robustness Test (Độ bền với nhiễu)

**Thí nghiệm:**
- Thêm noise vào auxiliary behaviors (PV) trong test data
- Tỷ lệ noise: 0% → 50%
- Các loại noise: Mask, Crop, Reorder, Substitute, Insert

**Kết quả:**
- GHTID có độ suy giảm performance **chậm hơn** MBSTR khi noise tăng
- Điều này chứng minh IAM thực sự giảm được nhiễu từ auxiliary behaviors

### 8.5. Ảnh hưởng của các loại Behavior

**Thí nghiệm:**
- So sánh hiệu suất khi thêm từng loại auxiliary behavior

**Kết quả:**
- "All behaviors" cho kết quả tốt nhất
- Page View (PV) là auxiliary behavior quan trọng nhất
- Thêm bất kỳ auxiliary behavior nào cũng cải thiện so với không dùng

---

## 9. Tóm tắt Đóng góp chính

### 9.1. Đóng góp 1: Global Item-Item Co-occurrence Graph

**Ý tưởng:** Xây dựng đồ thị toàn cục với các cạnh có trọng số PMI

**Tác dụng:**
- Học được mối quan hệ đồng xuất hiện từ tất cả users
- Giàu thông tin vì tổng hợp từ nhiều users

### 9.2. Đóng góp 2: Local Item-Item Transition Graph

**Ý tưởng:** Xây dựng đồ thị cục bộ riêng cho mỗi user

**Tác dụng:**
- Học được pattern riêng của từng user
- Behavior-aware attention phân biệt tầm quan trọng

### 9.3. Đóng góp 3: Interest Aggregation Module

**Ý tưởng:** Tổng hợp sở thích từ target behavior thông qua short-term và long-term interest

**Tác dụng:**
- Giảm nhiễu từ auxiliary behaviors
- Nắm bắt được cả sở thích ngắn hạn và dài hạn

---

## 10. So sánh với các Phương pháp khác

| Phương pháp | Ưu điểm | Nhược điểm |
|-------------|---------|------------|
| **FPMC, TransRec** | Đơn giản, nhanh | Không xử lý được multi-behavior |
| **SASRec, TiSASRec** | Mạnh mẽ với sequences | Chỉ single-behavior |
| **DMT, MGNN-Spred** | Xử lý multi-behavior | Sequence-level, bỏ qua item-level |
| **GPG4HSR** | Graph-based, multi-behavior | Không tường minh heterogeneous transitions |
| **GHTID** | Heterogeneous + Global + Local + Denoising | Phức tạp hơn |

---

## 11. Hạn chế và Hướng nghiên cứu tương lai

### 11.1. Hạn chế hiện tại:
- Chưa xem xét user profile (tuổi, giới tính, etc.)
- Chưa xem xét item attributes (mô tả, hình ảnh, etc.)

### 11.2. Hướng tương lai:
- Mở rộng framework với user profiling
- Tích hợp item attributes
- Áp dụng cho các domain khác (music, news, etc.)

---

## 12. Kết luận

**GHTID là một phương pháp hoàn chỉnh giải quyết 2 thách thức lớn trong Multi-behavior Sequential Recommendation:**

1. **Heterogeneous Item Transitions**: 
   - Global Graph học đồng xuất hiện từ tất cả users
   - Local Graph học chuyển đổi cá nhân cho mỗi user
   - Behavior-aware attention phân biệt tầm quan trọng

2. **Interference from Auxiliary Behaviors**:
   - Interest Aggregation Module lọc nhiễu
   - Tập trung vào target behavior
   - Short-term + Long-term interest

**Hiệu quả được chứng minh qua:**
- Experiments trên 4 real-world datasets
- Ablation studies cho thấy mỗi module đều quan trọng
- Robustness test cho thấy khả năng chống nhiễu tốt

---

## Bảng thuật ngữ

| Thuật ngữ | Tiếng Anh | Tiếng Việt |
|-----------|-----------|-------------|
| Sequential Recommendation | SRS | Hệ thống gợi ý tuần tự |
| Multi-behavior | MB | Đa hành vi |
| Target Behavior | TB | Hành vi mục tiêu |
| Auxiliary Behavior | AB | Hành vi phụ |
| Heterogeneous Item Transitions | HIT | Chuyển đổi item không đồng nhất |
| Intra-type Transition | ITT | Chuyển đổi cùng loại |
| Cross-type Transition | CTT | Chuyển đổi liên loại |
| Global Graph | GG | Đồ thị toàn cục |
| Local Graph | LG | Đồ thị cục bộ |
| Interest Aggregation | IA | Tổng hợp sở thích |
| Short-term Interest | STI | Sở thích ngắn hạn |
| Long-term Interest | LTI | Sở thích dài hạn |
| Attention Mechanism | AM | Cơ chế chú ý |
| PMI | PMI | Pointwise Mutual Information |

---

## Tài liệu tham khảo

Paper gốc: [WSDM '24](https://doi.org/10.1145/3616855.3635857)
