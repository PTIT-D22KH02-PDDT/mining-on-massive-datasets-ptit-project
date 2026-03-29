# Attention-Enhanced Graph Neural Networks for Session-Based Recommendation


Link bài báo: https://www.mdpi.com/2227-7390/8/9/1607


## Đặt vấn đề và nghiên cứu
Bài báo tập trung vào hệ thống gợi ý dựa trên phiên (session-based recommendation), nơi danh tính người dùng thường ẩn danh và hệ thống chỉ có thể dựa vào các hành vi nhấp chuột trong một phiên làm việc hiện tại
. Tác giả chỉ ra hai hạn chế lớn của các phương pháp hiện tại (như SR-GNN hay RNN):

- Sở thích cố định: Các mô hình cũ thường tạo ra một vector đại diện phiên cố định, không tính đến sự đa dạng của sở thích người dùng đối với các món đồ mục tiêu (target items) khác nhau
.

- Khó xác định độ ưu tiên: Khó khăn trong việc nắm bắt chính xác mức độ quan trọng khác nhau của từng món đồ trong sở thích dài hạn của người dùng
.


## Mô hình đề xuất
Mô hình gồm 4 giai đoạn chính:

Bước 1: Xây dựng đồ thị phiên (Session Graph)

- Mỗi phiên làm việc được chuyển thành một đồ thị có hướng, trong đó mỗi nút là một món đồ người dùng đã nhấp vào
.
- Các cạnh thể hiện thứ tự nhấp chuột (món đồ A dẫn đến món đồ B)
. Nếu một cặp món đồ xuất hiện nhiều lần, cạnh đó sẽ có trọng số cao hơn.

Bước 2: Học vector món đồ (GNN Layer)

- Sử dụng mạng nơ-ron đồ thị (GNN) để học các đặc trưng của từng món đồ
.
- Mạng này sử dụng cơ chế cổng cập nhật (update gate) và cổng đặt lại (reset gate) (tương tự như GRU) để quyết định thông tin nào từ các món đồ lân cận cần được giữ lại hoặc loại bỏ khi cập nhật trạng thái cho món đồ hiện tại
.

Bước 3: Mạng chú ý nhận biết mục tiêu (Target-aware Attentive Network)

- Đây là điểm cải tiến quan trọng nhất:

- Mô hình tính toán điểm tương quan giữa tất cả món đồ tron g phiên với món đồ mục tiêu (món đồ định gợi ý)
.

- Thay vì tạo ra một bản tóm tắt phiên duy nhất, cơ chế này giúp vector đại diện phiên thay đổi linh hoạt tùy thuộc vào món đồ mà hệ thống đang cân nhắc gợi ý
.

Bước 4: Lớp tự chú ý (Self-Attention Layers)

- Để nắm bắt các phụ thuộc toàn cầu (global dependencies) mà không phụ thuộc vào khoảng cách giữa các món đồ trong phiên, tác giả sử dụng Self-attention
.
- Nó giúp mô hình tự so sánh tất cả các món đồ với nhau để lọc ra những món đồ thực sự quan trọng, giúp biểu diễn sở thích dài hạn của người dùng chính xác hơn
.
- Tác giả còn thêm lớp Point-wise Feed-Forward và kết nối dư (residual connection) để tăng tính phi tuyến và tránh mất mát thông tin trong quá trình truyền tải dữ liệu


## Kết hợp sở thích và dự đoán


- Biểu diễn hỗn hợp (Hybrid Embedding): Sở thích cuối cùng của người dùng ($S_f$) được tạo ra bằng cách kết hợp sở thích dài hạn (từ lớp Self-attention) và sở thích ngắn hạn (vector của món đồ cuối cùng được nhấp)
.
- Dự đoán: Hệ thống tính toán xác suất nhấp chuột cho tất cả các món đồ ứng viên bằng cách sử dụng hàm softmax dựa trên điểm tương đồng giữa biểu diễn phiên và vector nhúng của món đồ đó


## Đánh giá thực nghiệm

### Tập dữ liệu và Cài đặt
*   Nghiên cứu sử dụng hai tập dữ liệu thực tế lớn là **Diginetica** và **Yoochoose** (bản 1/64).
*   Các món đồ xuất hiện ít hơn 5 lần và phiên ngắn hơn 2 món đồ bị loại bỏ để đảm bảo chất lượng dữ liệu.

### Kết quả so sánh
Mô hình được so sánh với các đối thủ mạnh nhất như SR-GNN, STAMP, NARM, GRU4REC:
*   **Hiệu quả vượt trội:** Mô hình đề xuất đạt kết quả tốt nhất trên cả hai chỉ số **P@20** (Độ chính xác) và **MRR@20** (Thứ hạng trung bình của kết quả đúng) trên cả hai tập dữ liệu.
*   **Phân tích sự ảnh hưởng (Ablation Study):**
    *   Việc sử dụng **2-3 khối Self-attention** mang lại hiệu quả cao nhất; nếu quá nhiều khối sẽ gây khó khăn cho việc học các đặc trưng cấp thấp.
    *   Phương pháp kết hợp sở thích (Original) luôn tốt hơn việc chỉ dùng sở thích dài hạn hoặc chỉ dùng sở thích ngắn hạn đơn thuần.

## So sánh với SR-GNN
| Tiêu chí | SR-GNN (2019)  | Mô hình Mathematics (2020) |
| :--- | :--- | :--- |
| **Cơ chế Attention** | Dùng soft-attention cơ bản để tóm tắt phiên. | Thêm **Target-aware Attention** và **Self-attention** đa lớp. |
| **Tính linh hoạt** | Vector đại diện phiên là cố định cho mọi món đồ ứng viên. | Vector đại diện phiên **biến đổi** theo món đồ mục tiêu đang xem xét. |
| **Xử lý nhiễu** | Lọc nhiễu thông qua soft-attention đơn giản. | Lọc nhiễu tinh vi hơn nhờ cơ chế tự so sánh (Self-attention) giữa các món đồ. |
| **Hiệu suất** | Là mô hình tiên tiến tại thời điểm 2019. | **Vượt mặt SR-GNN** trên tất cả các chỉ số thực nghiệm. |

**Kết luận:** Mô hình là một bước nâng cấp đáng kể của SR-GNN. Nó biến một hệ thống "quan sát sơ đồ" thành một hệ thống "tư vấn thông minh" biết thay đổi cách nhìn nhận lịch sử của bạn dựa trên từng món đồ cụ thể mà nó muốn giới thiệu cho bạn.