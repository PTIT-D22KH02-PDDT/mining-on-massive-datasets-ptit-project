# Nghiên cứu chi tiết: Attention-Enhanced Graph Neural Networks for Session-Based Recommendation

## Thông tin bài báo

- **Tiêu đề:** Attention-Enhanced Graph Neural Networks for Session-Based Recommendation
- **Tác giả:** Baocheng Wang và Wentao Cai
- **Tạp chí:** Mathematics 2020, 8(9), 1607
- **Năm:** 2020
- **DOI:** 10.3390/math8091607
- **Đơn vị:** College of Information, North China University of Technology, Beijing, China

---

## Mục lục

1. [Ôn lại kiến thức nền tảng](#1-ôn-lại-kiến-thức-nền-tảng)
2. [Vấn đề nghiên cứu](#2-vấn-đề-nghiên-cứu)
3. [Hạn chế của các phương pháp trước](#3-hạn-chế-của-các-phương-pháp-trước)
4. [Phương pháp đề xuất](#4-phương-pháp-đề-xuất)
5. [Chi tiết kỹ thuật từng thành phần](#5-chi-tiết-kỹ-thuật-từng-thành-phần)
6. [Thực nghiệm và kết quả](#6-thực-nghiệm-và-kết-quả)
7. [Phân tích chuyên sâu](#7-phân-tích-chuyên-sâu)
8. [Kết luận và hướng phát triển](#8-kết-luận-và-hướng-phát-triển)
9. [So sánh với SR-GNN](#9-so-sánh-với-sr-gnn)

---

## 1. Ôn lại kiến thức nền tảng

> **Lưu ý:** Bài báo này là một nghiên cứu **TIẾP THEO** của bài báo SR-GNN (2019). Nếu bạn chưa đọc phần giải thích nền tảng trong file nghiên cứu của SR-GNN, hãy đọc trước file đó. Dưới đây sẽ tóm tắt lại các khái niệm quan trọng nhất.

### 1.1 Session-Based Recommendation (Gợi ý dựa trên phiên)

**Định nghĩa:** Dự đoán sản phẩm tiếp theo người dùng sẽ click, CHỈ dựa vào chuỗi hành động trong session hiện tại (không cần biết người dùng là ai).

**Ví dụ thực tế:** Bạn vào Shopee (không đăng nhập), xem:
1. iPhone 15
2. Ốp lưng iPhone
3. Tai nghe AirPods

→ Hệ thống phải dự đoán: Sản phẩm tiếp theo bạn sẽ xem là gì?

### 1.2 Graph Neural Network (GNN - Mạng nơ-ron đồ thị)

**Graph (đồ thị):** Cấu trúc gồm các **nodes** (nút) và **edges** (cạnh nối giữa các nút).

**GNN:** Mạng nơ-ron xử lý dữ liệu dạng đồ thị, cho phép các node "giao tiếp" với nhau thông qua các cạnh.

**Ví dụ trong session:**
```
Session: [iPhone → Ốp lưng → AirPods → iPhone → Sạc dự phòng]

Đồ thị:
  Ốp lưng
     ↑
iPhone → AirPods
     ↑
Sạc dự phòng

GNN giúp iPhone "biết" rằng nó liên quan đến Ốp lưng, AirPods, và Sạc dự phòng
```

### 1.3 Attention Mechanism (Cơ chế chú ý)

**Attention:** Cơ chế giúp mô hình tự động "tập trung" vào những phần quan trọng nhất.

**Ví dụ:** Trong session [Áo → Quần → Giày → Áo → Cà vạt], attention giúp mô hình nhận ra "Áo" có thể là sản phẩm quan tâm chính (vì xuất hiện 2 lần).

### 1.4 Các khái niệm MỚI trong bài báo này

| Thuật ngữ | Giải thích |
|-----------|-----------|
| **Target Item** | Sản phẩm mục tiêu - sản phẩm mà chúng ta đang thử dự đoán xem người dùng có click không |
| **Target-Aware Attention** | Cơ chế chú ý có ý thức về mục tiêu - điều chỉnh sự chú ý dựa trên sản phẩm mục tiêu cụ thể |
| **Self-Attention** | Tự chú ý - mỗi phần tử trong chuỗi "chú ý" đến tất cả các phần tử khác (kể cả chính nó) |
| **Long-term Interest** | Sở thích dài hạn - sở thích tổng thể của người dùng trong toàn bộ session |
| **Short-term Interest** | Sở thích ngắn hạn - sở thích/sự quan tâm ngay lập tức (thường thể hiện qua sản phẩm cuối cùng click) |
| **Residual Connection** | Kết nối dư - cho phép thông tin từ lớp trước "nhảy qua" các lớp giữa để đến lớp sau |
| **Point-Wise Feed-Forward** | Mạng truyền thẳng xử lý từng điểm riêng biệt |
| **Multi-layer Self-Attention** | Nhiều lớp self-attention chồng lên nhau |
| **Ablation Study** | Nghiên cứu ablation - thử nghiệm loại bỏ từng thành phần để xem thành phần nào quan trọng |

---

## 2. Vấn đề nghiên cứu

### 2.1 Bài toán

Bài báo này giải quyết cùng bài toán với SR-GNN: **Session-Based Recommendation**

**Phát biểu chính thức:**
- Cho V = {v₁, v₂, ..., vₘ} là tập tất cả sản phẩm duy nhất
- Cho session s = [vₛ,₁, vₛ,₂, ..., vₛ,ₙ] là chuỗi các sản phẩm đã click theo thứ tự thời gian
- **Mục tiêu:** Dự đoán vₛ,ₙ₊₁ (sản phẩm tiếp theo)

### 2.2 Hai vấn đề chính mà bài báo chỉ ra

Bài báo chỉ ra 2 hạn chế của các phương pháp trước (bao gồm cả SR-GNN):

#### Vấn đề 1: Session embedding cố định, không thay đổi theo target item

**Giải thích chi tiết:**

Các phương pháp trước (như SR-GNN) tạo ra **MỘT** vector đại diện cho session, và vector này giống nhau bất kể đang dự đoán sản phẩm nào.

**Ví dụ minh họa:**

Session: [Áo sơ mi → Quần tây → Giày → Cà vạt]

- **Cách cũ (SR-GNN):** Tạo 1 vector session duy nhất, dùng vector này để đánh giá TẤT CẢ sản phẩm ứng viên
  - Vector session này giống nhau khi dự đoán xem người dùng sẽ click "Thắt lưng" hay "Tất/vớ"

- **Vấn đề:** 
  - Khi dự đoán "Thắt lưng" → nên tập trung vào "Quần tây" hơn
  - Khi dự đoán "Tất/vớ" → nên tập trung vào "Giày" hơn
  - Nhưng vector session cố định không thể hiện được sự khác biệt này!

**Nói cách khác:** Sở thích của người dùng THAY ĐỔI tùy thuộc vào sản phẩm mục tiêu đang xét. Một vector cố định không thể hiện được sự đa dạng này.

#### Vấn đề 2: Khó nắm bắt chính xác mức độ ưu tiên khác nhau của các sản phẩm

**Giải thích chi tiết:**

Trong session, không phải sản phẩm nào cũng quan trọng như nhau đối với sở thích dài hạn của người dùng.

**Ví dụ:**

Session: [Áo → Quần → Giày → Mũ → Áo → Cà vạt]

- "Áo" xuất hiện 2 lần → có thể là mối quan tâm CHÍNH
- "Mũ" chỉ xuất hiện 1 lần, có thể là click ngẫu nhiên
- Nhưng các phương pháp trước khó phân biệt chính xác mức độ quan trọng khác nhau này

### 2.3 Tại sao 2 vấn đề này quan trọng?

1. **Vấn đề 1** → Nếu không xét đến target item, mô hình không thể "điều chỉnh" sự chú ý phù hợp → dự đoán kém chính xác
2. **Vấn đề 2** → Nếu không phân biệt được mức độ ưu tiên, mô hình có thể bị "nhiễu" bởi các click không quan trọng

---

## 3. Hạn chế của các phương pháp trước

### 3.1 Phương pháp cổ điển

#### 3.1.1 Markov Chain (Chuỗi Markov)

**Cách hoạt động:** Dự đoán sản phẩm tiếp theo dựa trên xác suất chuyển đổi từ sản phẩm hiện tại.

**Ví dụ:** Sau khi xem iPhone, 60% người dùng xem ốp lưng, 25% xem tai nghe, 15% xem sạc.

**Hạn chế:**
- Chỉ nhìn 1 bước trước đó
- Giả định độc lập quá mạnh: kết hợp các thành phần quá khứ một cách độc lập
- Bỏ qua ngữ cảnh rộng hơn

#### 3.1.2 FPMC (Factorizing Personalized Markov Chains)

**Cách hoạt động:** Kết hợp Matrix Factorization và Markov Chain.

**Hạn chế:** Vẫn dựa trên giả định độc lập của Markov Chain.

### 3.2 Phương pháp dựa trên Deep Learning

#### 3.2.1 GRU4REC

**Cách hoạt động:** Dùng GRU (một loại RNN) để mô hình hóa chuỗi click.

**Hạn chế:**
- Chỉ nắm bắt được quan hệ tuần tự đơn giản
- Không nắm bắt được các chuyển đổi phức tạp giữa các sản phẩm

#### 3.2.2 NARM

**Cách hoạt động:** RNN + Attention mechanism.

**Hạn chế:** Vẫn dựa trên RNN nên không nắm bắt được mối quan hệ phức tạp giữa các sản phẩm không liên tiếp.

#### 3.2.3 STAMP

**Cách hoạt động:** MLP + Attention, nắm bắt sở thích dài hạn và ngắn hạn.

**Hạn chế:** Chỉ xem xét chuyển đổi giữa sản phẩm cuối và các sản phẩm trước đó.

### 3.3 Phương pháp dựa trên GNN

#### 3.3.1 SR-GNN (2019)

**Cách hoạt động:** Xây dựng session graph + Gated GNN + Attention để kết hợp global và local embedding.

**Thành công:** Đạt state-of-the-art tại thời điểm đó.

**Hạn chế (theo bài báo này):**
- Bỏ qua sở thích cụ thể của người dùng liên quan đến từng target item
- Không nắm bắt chính xác sở thích dài hạn của người dùng

#### 3.3.2 SR-GNN + Self-Attention (Xu et al., 2019)

**Cách hoạt động:** Kết hợp GNN với self-attention network.

**Hạn chế:** Bỏ qua sở thích cụ thể liên quan đến target item.

#### 3.3.3 TAGNN (Target Attentive GNN, Yu et al., 2020)

**Cách hoạt động:** Kết hợp GNN với target-attentive network.

**Hạn chế:** Khó nắm bắt chính xác mức độ ưu tiên khác nhau của các sản phẩm.

### 3.4 Tóm tắt khoảng trống nghiên cứu

| Phương pháp | Nắm bắt chuyển đổi phức tạp | Xét target item | Nắm bắt priority chính xác |
|---|---|---|---|
| Markov Chain | ❌ | ❌ | ❌ |
| GRU4REC | ❌ | ❌ | ❌ |
| NARM | ❌ | ❌ | ⚠️ |
| STAMP | ❌ | ❌ | ⚠️ |
| SR-GNN | ✅ | ❌ | ❌ |
| SR-GNN + Self-Attention | ✅ | ❌ | ✅ |
| TAGNN | ✅ | ✅ | ❌ |
| **Phương pháp đề xuất** | ✅ | ✅ | ✅ |

---

## 4. Phương pháp đề xuất

### 4.1 Ý tưởng cốt lõi

Bài báo đề xuất mô hình kết hợp **3 thành phần chính**:

```
1. Graph Neural Network (GNN)
   → Nắm bắt chuyển đổi phức tạp giữa các sản phẩm
   
2. Target-Aware Attentive Network
   → Kích hoạt sở thích cụ thể tương ứng với từng target item
   
3. Self-Attention Network
   → Nắm bắt chính xác mức độ ưu tiên khác nhau của các sản phẩm
```

### 4.2 Kiến trúc tổng quan

```
Input: Session sequences
    ↓
[1] Dynamic Graph Structure (Xây dựng đồ thị session)
    ↓
[2] Graph Neural Network (Học vector cho mỗi node)
    ↓
    ├──→ [3a] Target-Aware Attentive Network → Sở thích ngắn hạn (target-specific)
    │
    └──→ [3b] Self-Attention Layers → Sở thích dài hạn (global)
    ↓
[4] Hybrid Session Embedding (Kết hợp dài hạn + ngắn hạn)
    ↓
[5] Prediction Layer (Dự đoán sản phẩm tiếp theo)
```

### 4.3 Đóng góp chính

1. **Đề xuất mô hình mới** kết hợp self-attention network và target-attentive network để:
   - Nắm bắt sở thích cụ thể liên quan đến target item
   - Nắm bắt chính xác mức độ ưu tiên khác nhau của các sản phẩm

2. **Kết hợp sở thích ngắn hạn và dài hạn** dựa trên GNN đã được tăng cường attention

---

## 5. Chi tiết kỹ thuật từng thành phần

### 5.1 Thành phần 1: Dynamic Graph Structure (Cấu trúc đồ thị động)

#### 5.1.1 Xây dựng Session Graph

Mỗi session s = [vₛ,₁, vₛ,₂, ..., vₛ,ₙ] được chuyển thành đồ thị có hướng Gₛ = (Vₛ, Eₛ):

- **Nodes:** Mỗi sản phẩm duy nhất trong session
- **Edges:** Cạnh có hướng (vₛ,ᵢ₋₁, vₛ,ᵢ) nghĩa là người dùng click vₛ,ᵢ sau vₛ,ᵢ₋₁
- **Trọng số cạnh:** = Số lần cạnh xuất hiện / Bậc ra (outdegree) của node nguồn

#### 5.1.2 Ví dụ minh họa

Session: s = [v₁, v₂, v₃, v₁, v₄]

Đồ thị:
```
v₂ → v₃
↑    ↓
v₁   (không có cạnh đi ra từ v₃ trong ví dụ này)
↓
v₄
```

Ma trận kết nối:
- **Ma trận cạnh đi ra (A(out)):**

| | v₁ | v₂ | v₃ | v₄ |
|---|---|---|---|---|
| v₁ | 0 | 1/2 | 0 | 1/2 |
| v₂ | 0 | 0 | 1 | 0 |
| v₃ | 1 | 0 | 0 | 0 |
| v₄ | 0 | 0 | 0 | 0 |

Giải thích: v₁ có 2 cạnh đi ra (v₁→v₂ và v₁→v₄), mỗi cạnh có trọng số 1/2.

- **Ma trận cạnh đi vào (A(in)):**

| | v₁ | v₂ | v₃ | v₄ |
|---|---|---|---|---|
| v₁ | 0 | 0 | 0 | 0 |
| v₂ | 1 | 0 | 0 | 0 |
| v₃ | 0 | 1 | 0 | 0 |
| v₄ | 0 | 0 | 0 | 0 |

#### 5.1.3 Ma trận kết nối tổng hợp

Aₛ = [A(out)ₛ | A(in)ₛ] ∈ Rⁿˣ²ⁿ

Ma trận này ghép nối 2 ma trận trên theo chiều ngang.

### 5.2 Thành phần 2: Graph Neural Network (Học vector node)

#### 5.2.1 Quy trình học

GNN tự động trích xuất các mối quan hệ chuyển đổi phức tạp trong session graph. Quá trình học vector node diễn ra qua các công thức:

**Bước 1 - Tổng hợp thông tin từ hàng xóm:**
```
aₛ,ᵢᵗ = Aₛ,ᵢ: [v₁ᵗ⁻¹, ..., vₙᵗ⁻¹] H + b           (1)
```
- Aₛ,ᵢ: là hàng thứ i của ma trận kết nối
- H ∈ Rᵈˣ²ᵈ là ma trận trọng số
- b là bias
- aₛ,ᵢᵗ là thông tin tổng hợp từ các node lân cận

**Bước 2 - Update Gate (Cổng cập nhật):**
```
zₛ,ᵢᵗ = σ(Wz·aₛ,ᵢᵗ + Uz·vᵢᵗ⁻¹)                    (2)
```
- σ là hàm sigmoid (cho giá trị 0→1)
- zₛ,ᵢᵗ quyết định bao nhiêu % thông tin mới được giữ lại

**Bước 3 - Reset Gate (Cổng đặt lại):**
```
rₛ,ᵢᵗ = σ(Wr·aₛ,ᵢᵗ + Ur·vᵢᵗ⁻¹)                    (3)
```
- rₛ,ᵢᵗ quyết định bao nhiêu % thông tin cũ bị "quên"

**Bước 4 - Trạng thái ứng viên:**
```
ṽᵢᵗ = tanh(Wo·aₛ,ᵢᵗ + Uo·(rₛ,ᵢᵗ ⊙ vᵢᵗ⁻¹))        (4)
```
- ⊙ là phép nhân từng phần tử (element-wise multiplication)
- ṽᵢᵗ là trạng thái ứng viên mới

**Bước 5 - Trạng thái cuối cùng:**
```
vᵢᵗ = (1 - zₛ,ᵢᵗ) ⊙ vᵢᵗ⁻¹ + zₛ,ᵢᵗ ⊙ ṽᵢᵗ          (5)
```

#### 5.2.2 Giải thích bằng ngôn ngữ đơn giản

Hãy tưởng tượng mỗi node là một người:

1. **Bước 1:** Mỗi người nghe tin từ bạn bè (các node lân cận)
2. **Bước 2 (Update Gate):** Quyết định có nên cập nhật kiến thức của mình không (z ≈ 1 → cập nhật nhiều, z ≈ 0 → giữ nguyên)
3. **Bước 3 (Reset Gate):** Quyết định có nên quên kiến thức cũ không (r ≈ 0 → quên, r ≈ 1 → giữ)
4. **Bước 4:** Tạo kiến thức mới dựa trên tin từ bạn bè + kiến thức cũ (đã được reset gate điều chỉnh)
5. **Bước 5:** Kết hợp kiến thức cũ và kiến thức mới

Lặp lại quá trình này nhiều lần → mỗi node có được thông tin từ TOÀN BỘ đồ thị.

### 5.3 Thành phần 3: Target-Aware Attentive Network

> **Đây là thành phần QUAN TRỌNG NHẤT và MỚI NHẤT so với SR-GNN**

#### 5.3.1 Ý tưởng

Thay vì tạo MỘT vector session cố định, mô hình tạo ra các vector session KHÁC NHAU tùy thuộc vào target item đang xét.

**Ví dụ minh họa:**

Session: [Áo sơ mi → Quần tây → Giày → Cà vạt]

- Khi dự đoán **"Thắt lưng"** → mô hình tập trung nhiều hơn vào "Quần tây"
- Khi dự đoán **"Tất/vớ"** → mô hình tập trung nhiều hơn vào "Giày"
- Khi dự đoán **"Kẹp cà vạt"** → mô hình tập trung nhiều hơn vào "Cà vạt" và "Áo sơ mi"

→ Mỗi target item "kích hoạt" (activate) một sở thích KHÁC NHAU của người dùng.

#### 5.3.2 Công thức tính attention score

**Bước 1 - Tính điểm attention giữa mỗi node và target item:**
```
βᵢ,ₜ = softmax(eᵢ,ₜ) = exp(vₜᵀ · W · vᵢ) / Σⱼ exp(vₜᵀ · W · vⱼ)    (6)
```

Trong đó:
- vᵢ là vector của node thứ i trong session
- vₜ là vector của target item (sản phẩm mục tiêu đang xét)
- W ∈ Rᵈˣᵈ là ma trận trọng số (học được)
- βᵢ,ₜ là trọng số attention của node i đối với target item t

**Giải thích:**
- exp(vₜᵀ · W · vᵢ) đo lường mức độ "liên quan" giữa node i và target item t
- Softmax chuẩn hóa các điểm này thành xác suất (tổng bằng 1)
- Node nào liên quan nhiều hơn đến target item → có trọng số cao hơn

**Bước 2 - Tạo vector sở thích hướng đến target item:**
```
s_target = Σ(βᵢ,ₜ · vᵢ) với i từ 1 đến n              (7)
```

Vector này là tổng có trọng số của tất cả node, với trọng số phụ thuộc vào target item.

#### 5.3.3 Ví dụ cụ thể

Session: [Áo (v₁) → Quần (v₂) → Giày (v₃) → Cà vạt (v₄)]

**Khi target item = "Thắt lưng" (vₜ):**

Giả sử mô hình tính được:
- β₁,ₜ (Áo → Thắt lưng) = 0.15
- β₂,ₜ (Quần → Thắt lưng) = 0.50 ← cao nhất!
- β₃,ₜ (Giày → Thắt lưng) = 0.20
- β₄,ₜ (Cà vạt → Thắt lưng) = 0.15

→ s_target = 0.15·v₁ + 0.50·v₂ + 0.20·v₃ + 0.15·v₄
→ Vector này thiên về "Quần" nhất vì thắt lưng liên quan đến quần.

**Khi target item = "Tất/vớ" (vₜ'):**

Giả sử:
- β₁,ₜ' (Áo → Tất) = 0.10
- β₂,ₜ' (Quần → Tất) = 0.15
- β₃,ₜ' (Giày → Tất) = 0.60 ← cao nhất!
- β₄,ₜ' (Cà vạt → Tất) = 0.15

→ s_target' = 0.10·v₁ + 0.15·v₂ + 0.60·v₃ + 0.15·v₄
→ Vector này thiên về "Giày" nhất vì tất liên quan đến giày.

**Kết luận:** s_target ≠ s_target' → Mỗi target item tạo ra một vector session KHÁC NHAU!

### 5.4 Thành phần 4: Self-Attention Layers

> **Thành phần này giải quyết Vấn đề 2: Nắm bắt chính xác mức độ ưu tiên khác nhau**

#### 5.4.1 Self-Attention là gì?

**Self-Attention** (tự chú ý) là cơ chế mà mỗi phần tử trong chuỗi "chú ý" đến TẤT CẢ các phần tử khác (kể cả chính nó), bất kể khoảng cách.

**So sánh với RNN:**
- **RNN:** Chỉ chú ý đến các phần tử trước đó theo thứ tự tuần tự
- **Self-Attention:** Nhìn TẤT CẢ cùng lúc, không quan tâm thứ tự

**Ví dụ:**

Session: [v₁, v₂, v₃, v₄, v₅]

- **RNN:** v₅ chỉ "nhìn thấy" v₄ trực tiếp, v₃ gián tiếp qua v₄, v₂ càng gián tiếp hơn...
- **Self-Attention:** v₅ "nhìn thấy" v₁, v₂, v₃, v₄ cùng lúc với mức độ chú ý khác nhau

#### 5.4.2 Công thức Self-Attention Layer

**Đầu vào:** H = [β₁v₁, β₂v₂, ..., βₙvₙ] (các node vector đã được target attention điều chỉnh)

```
E = softmax((HWQ)(HWK)ᵀ / √d) · (HWV)              (8)
```

Trong đó:
- WQ, WK, WV ∈ R²ᵈˣᵈ là các ma trận chiếu (projection matrices)
- HWQ = Query (truy vấn): "Tôi đang tìm gì?"
- HWK = Key (khóa): "Tôi có gì?"
- HWV = Value (giá trị): "Tôi chứa thông tin gì?"
- √d là hệ số scaling để tránh gradient quá lớn

**Giải thích bằng phép ẩn dụ:**

Hãy tưởng tượng bạn đang tìm sách trong thư viện:
- **Query (Q):** Bạn có một "từ khóa tìm kiếm" trong đầu
- **Key (K):** Mỗi cuốn sách có một "nhãn đề mục"
- **Value (V):** Nội dung thực sự của cuốn sách

Self-attention so sánh Query với tất cả Keys → tìm ra cuốn sách nào phù hợp nhất → lấy Value của những cuốn sách đó.

#### 5.4.3 Point-Wise Feed-Forward Network

Sau self-attention, mô hình áp dụng một mạng truyền thẳng để thêm tính phi tuyến:

```
F = ReLU(EW₁ + b₁)W₂ + b₂ + E                       (9)
```

Trong đó:
- W₁, W₂ ∈ Rᵈˣᵈ là ma trận trọng số
- b₁, b₂ là bias vectors
- ReLU là hàm kích hoạt: ReLU(x) = max(0, x)
- **+ E ở cuối là Residual Connection** (kết nối dư)

**Tại sao cần Residual Connection?**
- Self-attention có thể gây "mất mát thông tin" khi truyền qua nhiều lớp
- Residual connection cho phép thông tin từ lớp trước "nhảy qua" các lớp giữa
- Giống như việc bạn vừa học kiến thức mới, vừa giữ lại kiến thức cũ

#### 5.4.4 Multi-Layer Self-Attention

Mô hình có thể xếp chồng nhiều lớp self-attention:

```
F⁽¹⁾ = F                                    (lớp 1)
F⁽ᵏ⁾ = SAN(F⁽ᵏ⁻¹⁾)                          (lớp k, với k > 1)     (11)
```

Trong đó SAN là toàn bộ quá trình self-attention + feed-forward.

**Tại sao cần nhiều lớp?**
- Mỗi lớp nắm bắt một loại đặc trưng khác nhau
- Lớp thấp: nắm bắt quan hệ cục bộ (giữa các sản phẩm gần nhau)
- Lớp cao: nắm bắt quan hệ toàn cục (giữa các sản phẩm xa nhau)

**Ví dụ:**
- Lớp 1: Nhận ra "Áo" và "Quần" thường đi cùng nhau
- Lớp 2: Nhận ra "Áo + Quần + Giày" tạo thành một bộ trang phục hoàn chỉnh
- Lớp 3: Nhận ra phong cách tổng thể của người dùng (formal, casual, sport...)

### 5.5 Thành phần 5: Hybrid Session Embedding

#### 5.5.1 Kết hợp sở thích dài hạn và ngắn hạn

```
S_f = ω · Fₙ⁽ᵏ⁾ + (1 - ω) · hₙ                    (12)
```

Trong đó:
- **Fₙ⁽ᵏ⁾** ∈ Rᵈ: Hàng thứ n của ma trận F⁽ᵏ⁾ từ self-attention layers → **Sở thích dài hạn** (global embedding)
- **hₙ**: Vector của sản phẩm CUỐI CÙNG được click → **Sở thích ngắn hạn** (local embedding)
- **ω**: Trọng số kết hợp (0 ≤ ω ≤ 1)

**Ý nghĩa:**
- **Sở thích dài hạn (Fₙ⁽ᵏ⁾):** Thể hiện xu hướng tổng thể của người dùng trong toàn bộ session, được self-attention tinh chỉnh
- **Sở thích ngắn hạn (hₙ):** Thể hiện sự quan tâm NGAY LẬP TỨC (sản phẩm cuối cùng thường phản ánh ý định hiện tại rõ nhất)
- **Kết hợp:** Cả hai đều quan trọng → kết hợp có trọng số

#### 5.5.2 Ví dụ minh họa

Session: [Áo → Quần → Giày → Mũ → Cà vạt]

- **Sở thích ngắn hạn (hₙ):** Vector của "Cà vạt" → Người dùng ĐANG quan tâm đến phụ kiện
- **Sở thích dài hạn (Fₙ⁽ᵏ⁾):** Thể hiện xu hướng tổng thể → Người dùng đang mua đồ đi làm/formal
- **Kết hợp (S_f):** Người dùng đang mua đồ đi làm và hiện tại đang quan tâm đến phụ kiện

### 5.6 Thành phần 6: Prediction Layer (Lớp dự đoán)

#### 5.6.1 Tính xác suất cho mỗi sản phẩm

```
ŷᵢ = softmax(S_fᵀ · vᵢ)                             (13)
```

- S_f là vector session cuối cùng (hybrid embedding)
- vᵢ là vector embedding của sản phẩm ứng viên i
- ŷᵢ là xác suất sản phẩm i được click tiếp theo

#### 5.6.2 Hàm mất mát (Loss Function)

```
J = -Σ[yᵢ·log(ŷᵢ) + (1-ŷᵢ)·log(1-ŷᵢ)] + λ·||θ||²   (14)
```

Trong đó:
- y là vector one-hot encoding của sản phẩm đúng
- λ·||θ||² là L2 regularization (tránh overfitting)
- θ là tập hợp tất cả tham số học được

#### 5.6.3 Huấn luyện

- **Optimizer:** Adam
- **Learning rate:** 0.001, giảm 10 lần sau mỗi 3 epochs
- **Batch size:** 100
- **Hidden dimensionality:** 100

---

## 6. Thực nghiệm và kết quả

### 6.1 Dataset

#### 6.1.1 Diginetica
- **Nguồn:** CIKM Cup 2016
- **Nội dung:** Dữ liệu giao dịch thương mại điện tử
- **Tiền xử lý:**
  - Giữ lại sản phẩm xuất hiện > 5 lần
  - Giữ lại session có > 2 items
  - Test set: sessions của các tuần cuối

#### 6.1.2 Yoochoose
- **Nguồn:** RecSys Challenge 2015
- **Nội dung:** Stream click trên website thương mại điện tử trong 6 tháng
- **Tiền xử lý:** Tương tự Diginetica
- **Test set:** sessions của các ngày cuối
- **Phiên bản:** Sử dụng 1/64 dữ liệu mới nhất

### 6.2 Baseline Algorithms

| STT | Phương pháp | Mô tả |
|---|---|---|
| 1 | POP | Gợi ý sản phẩm phổ biến nhất |
| 2 | Item-KNN | Gợi ý sản phẩm tương tự (dựa trên cosine similarity) |
| 3 | BPR-MF | Factorization-based, tối ưu pairwise ranking |
| 4 | FPMC | Kết hợp Matrix Factorization + Markov Chain |
| 5 | GRU4REC | RNN-based (GRU) cho session-based recommendation |
| 6 | STAMP | Short-term attention/memory priority model |
| 7 | SR-GNN | GNN-based, state-of-the-art trước đó |
| 8 | TAGNN | GNN + target attentive network |

### 6.3 Kết quả chính

#### Bảng kết quả chi tiết:

| Phương pháp | Diginetica | | Yoochoose 1/64 | |
|---|---|---|---|---|
| | P@20 | MRR@20 | P@20 | MRR@20 |
| POP | 0.87 | 0.19 | 6.74 | 1.63 |
| Item-KNN | 35.69 | 11.54 | 51.59 | 21.79 |
| BPR-MF | 5.21 | 1.89 | 31.28 | 12.07 |
| FPMC | 26.52 | 6.94 | 45.61 | 15.01 |
| GRU4REC | 29.40 | 8.31 | 60.67 | 22.90 |
| STAMP | 45.59 | 14.29 | 68.69 | 29.64 |
| SR-GNN | 50.72 | 17.56 | 70.56 | 30.92 |
| TAGNN | 51.29 | 17.93 | 70.98 | 31.03 |
| **OUR MODEL** | **52.02** | **18.58** | **71.45** | **31.29** |

#### 6.3.1 Nhận xét

1. **Mô hình đề xuất đạt kết quả tốt nhất** trên tất cả dataset và metric
2. **TAGNN > SR-GNN:** Target attention giúp cải thiện kết quả
3. **SR-GNN > STAMP > GRU4REC:** GNN nắm bắt chuyển đổi phức tạp tốt hơn RNN
4. **Deep learning > Phương pháp cổ điển:** Tất cả phương pháp neural network đều vượt trội

### 6.4 Ablation Study (Nghiên cứu loại bỏ thành phần)

#### 6.4.1 Ảnh hưởng của số lượng Self-Attention Blocks

Số lượng blocks (k) được thay đổi từ 1 đến 6:

**Kết quả:**
- Performance tăng khi tăng k đến một giá trị phù hợp
- Sau đó GIẢM khi tiếp tục tăng k
- Lý do: Quá nhiều block làm mô hình khó nắm bắt đặc trưng từ các lớp thấp

**Bài học:** Không phải càng nhiều lớp càng tốt. Cần chọn số lớp tối ưu.

#### 6.4.2 Ảnh hưởng của các phương pháp Session Embedding

So sánh 2 phương án không đầy đủ:

| Phương án | Mô tả | Kết quả |
|---|---|---|
| Scheme 1 | Chỉ dùng long-term embedding (attention-based) | Tốt hơn Scheme 2 |
| Scheme 2 | Chỉ dùng short-term embedding (last item) | Kém hơn |
| **Đầy đủ** | Kết hợp cả hai | **Tốt nhất** |

**Nhận xét:**
- Scheme 2 (chỉ dùng last item) vẫn hoạt động khá tốt → Sản phẩm cuối cùng chứa nhiều thông tin
- Scheme 1 (chỉ dùng global attention) tốt hơn Scheme 2 → Global preference quan trọng hơn local preference
- Kết hợp cả hai → Tốt nhất → Cả dài hạn và ngắn hạn đều quan trọng

---

## 7. Phân tích chuyên sâu

### 7.1 Tại sao Target-Aware Attention quan trọng?

#### 7.1.1 So sánh trực quan

**Không có Target-Aware Attention (SR-GNN):**

```
Session: [Áo → Quần → Giày → Cà vạt]

Vector session cố định:
S = [0.3, -0.5, 0.8, 0.1, ...]

Dùng S để đánh giá TẤT CẢ sản phẩm:
- Thắt lưng: score = S · V(thắt lưng) = 0.45
- Tất/vớ: score = S · V(tất) = 0.38
```

→ Vector S giống nhau cho mọi target item.

**Có Target-Aware Attention (Mô hình đề xuất):**

```
Session: [Áo → Quần → Giày → Cà vạt]

Khi target = "Thắt lưng":
S(thắt lưng) = [0.2, -0.7, 0.5, 0.3, ...]  ← thiên về "Quần"
score = S(thắt lưng) · V(thắt lưng) = 0.52  ← cao hơn!

Khi target = "Tất/vớ":
S(tất) = [0.1, -0.3, 0.8, 0.2, ...]  ← thiên về "Giày"
score = S(tất) · V(tất) = 0.48  ← chính xác hơn!
```

→ Mỗi target item có vector session RIÊNG, phù hợp hơn.

### 7.2 Tại sao Self-Attention quan trọng?

#### 7.2.1 So sánh với cách làm của SR-GNN

**SR-GNN dùng soft attention đơn giản:**
```
αᵢ = qᵀ · σ(W₁·vₙ + W₂·vᵢ + c)
```
- Chỉ tính trọng số dựa trên vector của node i và node cuối cùng
- Không xét mối quan hệ giữa TẤT CẢ các cặp node

**Self-Attention:**
```
E = softmax((HWQ)(HWK)ᵀ / √d) · (HWV)
```
- Mỗi node "chú ý" đến TẤT CẢ các node khác
- Nắm bắt được mối quan hệ PHỨC TẠP giữa mọi cặp node
- Nhiều lớp → nắm bắt được đặc trưng ở nhiều mức độ trừu tượng

#### 7.2.2 Ví dụ minh họa

Session: [Áo sơ mi trắng → Quần tây đen → Giày da → Cà vạt đỏ → Áo sơ mi trắng]

**Self-Attention có thể nhận ra:**
- "Áo sơ mi trắng" xuất hiện 2 lần → quan trọng
- "Áo + Quần + Giày + Cà vạt" → bộ trang phục formal hoàn chỉnh
- Màu sắc: trắng + đen + đỏ → phong cách tương phản

**SR-GNN attention đơn giản:**
- Chỉ so sánh mỗi sản phẩm với sản phẩm cuối cùng
- Không nắm bắt được các mối quan hệ phức tạp trên

### 7.3 Mối quan hệ giữa các thành phần

```
GNN                    → Hiểu cấu trúc session (ai liên quan đến ai)
    ↓
Target-Aware Attention → Hiểu sở thích cụ thể (tùy target item)
    ↓
Self-Attention         → Hiểu mức độ ưu tiên (cái nào quan trọng hơn)
    ↓
Hybrid Embedding       → Kết hợp toàn diện (dài hạn + ngắn hạn)
```

Mỗi thành phần bổ sung cho nhau:
- **GNN** mà không có Target-Aware → vector session cố định, không linh hoạt
- **Target-Aware** mà không có Self-Attention → không nắm bắt chính xác priority
- **Self-Attention** mà không có GNN → không nắm bắt được cấu trúc đồ thị

### 7.4 So sánh với các mô hình tiền nhiệm

#### 7.4.1 So với SR-GNN

| Thành phần | SR-GNN | Mô hình đề xuất |
|---|---|---|
| Session Graph | ✅ | ✅ |
| Gated GNN | ✅ | ✅ |
| Target-Aware Attention | ❌ | ✅ |
| Self-Attention | ❌ | ✅ |
| Multi-layer | ❌ | ✅ |
| Residual Connection | ❌ | ✅ |
| Session Embedding | Global + Local (attention đơn giản) | Target-specific + Self-attention |

#### 7.4.2 So với TAGNN

| Thành phần | TAGNN | Mô hình đề xuất |
|---|---|---|
| Session Graph | ✅ | ✅ |
| Gated GNN | ✅ | ✅ |
| Target-Aware Attention | ✅ | ✅ |
| Self-Attention | ❌ | ✅ |
| Nắm bắt priority chính xác | ❌ | ✅ |

#### 7.4.3 So với SR-GNN + Self-Attention (Xu et al.)

| Thành phần | Xu et al. | Mô hình đề xuất |
|---|---|---|
| Session Graph | ✅ | ✅ |
| Gated GNN | ✅ | ✅ |
| Self-Attention | ✅ | ✅ |
| Target-Aware Attention | ❌ | ✅ |
| Sở thích cụ thể theo target | ❌ | ✅ |

---

## 8. Kết luận và hướng phát triển

### 8.1 Tóm tắt

Bài báo đề xuất mô hình **Attention-Enhanced GNN** cho session-based recommendation với 3 thành phần chính:

1. **Graph Neural Network:** Nắm bắt chuyển đổi phức tạp giữa các sản phẩm
2. **Target-Aware Attentive Network:** Kích hoạt sở thích cụ thể tương ứng với từng target item
3. **Self-Attention Network:** Nắm bắt chính xác mức độ ưu tiên khác nhau của các sản phẩm

Mô hình đạt kết quả **state-of-the-art** trên 2 dataset thực tế (Diginetica và Yoochoose).

### 8.2 Hạn chế và hướng phát triển

#### Hạn chế 1: Cách xây dựng session graph đơn giản
- Chỉ xây dựng đồ thị từ các cạnh liên tiếp
- Không nắm bắt đầy đủ các mối quan hệ phức tạp hơn

**Hướng khắc phục:** Tối ưu hóa cách xây dựng session graph

#### Hạn chế 2: Không sử dụng kiến thức bên ngoài
- Chỉ dùng dữ liệu hành vi người dùng
- Bỏ qua các thông tin bổ sung như: mạng xã hội, knowledge base của sản phẩm...

**Hướng khắc phục:** Tích hợp external knowledge base

### 8.3 Ý nghĩa thực tiễn

Mô hình này có thể áp dụng cho:
1. **Thương mại điện tử:** Gợi ý sản phẩm tiếp theo
2. **Streaming media:** Gợi ý video/bài hát tiếp theo
3. **Tin tức:** Gợi ý bài báo tiếp theo
4. **Bất kỳ dịch vụ nào** có session ẩn danh

---

## 9. So sánh với SR-GNN

### 9.1 Điểm giống nhau

| Yếu tố | SR-GNN | Bài báo này |
|---|---|---|
| Bài toán | Session-based recommendation | Session-based recommendation |
| Session Graph | ✅ | ✅ |
| Gated GNN | ✅ | ✅ |
| Kết hợp dài hạn + ngắn hạn | ✅ | ✅ |
| Dataset | Yoochoose, Diginetica | Yoochoose, Diginetica |
| Metrics | P@20, MRR@20 | P@20, MRR@20 |

### 9.2 Điểm khác biệt

| Yếu tố | SR-GNN (2019) | Bài báo này (2020) |
|---|---|---|
| Attention cho global embedding | Soft attention đơn giản | Self-attention multi-layer |
| Session embedding | Cố định cho mọi target item | Thay đổi theo target item |
| Target-Aware Attention | ❌ | ✅ |
| Residual Connection | ❌ | ✅ |
| Point-Wise Feed-Forward | ❌ | ✅ |
| Multi-layer Self-Attention | ❌ | ✅ |

### 9.3 So sánh kết quả

| Dataset | SR-GNN P@20 | Bài này P@20 | Cải thiện |
|---|---|---|---|
| Yoochoose 1/64 | 70.56 | 71.45 | +0.89 |
| Diginetica | 50.72 | 52.02 | +1.30 |

→ Cải thiện không quá lớn nhưng **nhất quán** trên cả 2 dataset.

### 9.4 Nhận xét cá nhân

Bài báo này là một **cải tiến tự nhiên** của SR-GNN:
- Giữ lại những gì SR-GNN làm tốt (GNN, session graph)
- Bổ sung Target-Aware Attention (từ TAGNN)
- Bổ sung Self-Attention (từ Xu et al.)
- Kết hợp cả hai thành một mô hình thống nhất

Tuy nhiên, mức độ cải tiến không mang tính đột phá - đây là sự kết hợp của các ý tưởng đã có.

---

## Phụ lục: Bảng thuật ngữ Anh-Việt

| Tiếng Anh | Tiếng Việt | Giải thích |
|-----------|-----------|-----------|
| Target Item | Sản phẩm mục tiêu | Sản phẩm đang được dự đoán |
| Target-Aware Attention | Chú ý có ý thức mục tiêu | Attention thay đổi theo target item |
| Self-Attention | Tự chú ý | Mỗi phần tử chú ý đến tất cả phần tử khác |
| Long-term Interest | Sở thích dài hạn | Xu hướng tổng thể trong session |
| Short-term Interest | Sở thích ngắn hạn | Sự quan tâm tức thời (last click) |
| Residual Connection | Kết nối dư | Cho phép thông tin "nhảy qua" các lớp |
| Point-Wise Feed-Forward | Truyền thẳng từng điểm | Mạng neural xử lý từng vị trí độc lập |
| Multi-layer | Đa lớp | Nhiều lớp neural chồng lên nhau |
| Ablation Study | Nghiên cứu ablation | Loại bỏ từng thành phần để đánh giá |
| Projection Matrix | Ma trận chiếu | Biến đổi vector sang không gian khác |
| Query / Key / Value | Truy vấn / Khóa / Giá trị | 3 thành phần của attention mechanism |
| Scaling Factor | Hệ số tỉ lệ | √d, tránh gradient quá lớn |
| Dropout | Dropout | Kỹ thuật regularization, tắt ngẫu nhiên một số node |
| ReLU | ReLU | Hàm kích hoạt: max(0, x) |
| One-hot Encoding | Mã hóa one-hot | Vector có 1 số 1, còn lại là 0 |
| L2 Regularization | Điều chuẩn L2 | Phạt trọng số lớn, tránh overfitting |
