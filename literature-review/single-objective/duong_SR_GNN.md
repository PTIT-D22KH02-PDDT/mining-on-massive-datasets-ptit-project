
# SR-GNN : Session-Based Recommendation with Graph Neural Networks

Link bài báo: https://arxiv.org/pdf/1811.00855


## Bối cảnh
Một số phương pháp trước đó:

- RNN: Chỉ mô hình hóa các chuyển đổi tuần tự giữa các mục liền kề, bỏ qua các kết nối phức tạp và ngầm định giữa các mục không liền kề trong một phiên

- Hạn chế trong biểu diễn: Khó khăn trong việc nắm bắt chính xác ý định người dùng khi có sự thay đổi sở thích nhanh chóng hoặc các lần nhấp chuột ngẫu nhiên (nhiễu)
 

## Mô hình SR-GNN

4 bước chính:
- Xây dựng đồ thị phiên (Session Graphs): Mỗi phiên được mô hình hóa thành một đồ thị có hướng, trong đó mỗi nút là một mục (item) và các cạnh biểu thị thứ tự nhấp chuột của người dùng
. Nếu các mục lặp lại, cạnh sẽ được gán trọng số chuẩn hóa dựa trên số lần xuất hiện

- Học vector item embeddings: sử dụng GGNN để học các vector ẩn cho tất cả các nút trong đồ thị
. Quá trình này sử dụng các cổng cập nhật (update gate) và cổng đặt lại (reset gate) để quyết định thông tin nào cần giữ lại hoặc loại bỏ khi lan truyền thông tin giữa các nút láng giềng


- Biểu diễn phiên (Session Representation): Để dự đoán mục tiếp theo, mô hình tạo ra một vector đại diện cho toàn bộ phiên thông qua cơ chế kết hợp:
    + Nhúng cục bộ ($s_l$): Chính là vector của mục được nhấp cuối cùng trong phiên, đại diện cho sở thích hiện tại
    + Nhúng toàn cục ($s_g$): Sử dụng cơ chế soft-attention để tổng hợp tất cả các vector nút trong đồ thị phiên, giúp xác định các mục quan trọng và loại bỏ nhiễu
    + Nhúng hỗn hợp ($s_h$): Kết hợp nhúng cục bộ và toàn cục thông qua một phép biến đổi tuyến tính

- Dự đoán mục tiếp theo: Điểm số gợi ý cho mỗi mục ứng viên được tính bằng tích vô hướng giữa vector nhúng của mục đó và vector biểu diễn phiên $s_h$, sau đó đưa qua lớp softmax để lấy xác suất


## Kết quả thực nghiệm và phân tích
Nghiên cứu sử dụng hai tập dữ liệu thực tế là Yoochoose và Diginetica để đánh giá
. Các kết quả chính bao gồm:    
- Vượt trội so với các mô hình tiên tiến: SR-GNN nhất quán đạt kết quả tốt hơn các phương pháp như RNN (GRU4Rec, NARM) và STAMP trên cả hai chỉ số P@20 và MRR@20.
- Khả năng thích ứng với độ dài phiên: SR-GNN hoạt động ổn định trên cả phiên ngắn và phiên dài, trong khi các mô hình RNN thường bị giảm hiệu suất nhanh chóng khi độ dài phiên tăng lên do khó khăn trong việc xử lý các chuỗi dài.
- Hiệu quả của cơ chế Attention: Việc kết hợp sở thích toàn cục thông qua attention giúp mô hình lọc bỏ các hành vi nhấp chuột không mục đích hoặc mang tính ngẫu nhiên của người dùng.

## Đóng góp
- Đưa mạng nơ-ron đồ thị vào bài toán gợi ý theo phiên để khai thác các mối quan hệ phức tạp giữa các mục
.
- Đề xuất chiến lược biểu diễn phiên kết hợp giữa sở thích hiện tại (local) và sở thích dài hạn trong phiên (global)
.
- Chứng minh bằng thực nghiệm rằng việc mô hình hóa phiên dưới dạng đồ thị là hiệu quả hơn so với dạng chuỗi đơn thuần  