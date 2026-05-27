## python -m  src.test.test_load_covisited_matrix_to_redis

# xóa dữ liệu trong redis-cli:    FLUSHDB
# Xem value của key:              LRANGE <tên key> 0 -1 

# truy vấn ra 1 value của key thì enter cái ra luôn. 
# Ram lưu trữ 1.8M chiếm tầm 0.8GB 

import os
from dotenv import load_dotenv
import redis
from src.core.constant import COVISITATION_MATRIX_FILEPATH
from src.core import SparkService

load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

# covisited_path = DATASETS_DIR / "co_visited_unified.parquet"


def send_partition_to_redis(partition):
    """
    Hàm xử lý trên từng Partition (chạy tại Worker).
    Mỗi Worker sẽ tự mở kết nối độc lập tới Redis và dùng Pipeline để tối ưu tốc độ.
    """
    # Cấu hình kết nối Redis bên trong Worker (lấy từ môi trường của Worker)
    host = os.getenv("REDIS_HOST", "localhost")
    port = int(os.getenv("REDIS_PORT", "6379"))
    
    # Tạo kết nối Redis & Pipeline cho riêng partition này
    r = redis.Redis(host=host, port=port, db=0, decode_responses=True)
    pipe = r.pipeline(transaction=False)
    
    batch_size = 5000  # Gom 5000 dòng rồi mới "nổ súng" gửi 1 lần
    count = 0
    
    for row in partition:
        aid = row['aid']
        candidates = row['candidates']
        aid2_list = [str(c['aid2']) for c in candidates]
        
        if aid2_list:
            key = f"covis:{aid}"
            pipe.delete(key)
            pipe.rpush(key, *aid2_list)
            count += 1
            
        # Khi đủ batch_size thì thực thi lệnh ghi
        if count % batch_size == 0:
            pipe.execute()
            
    # Thực thi nốt số lượng dòng dư còn lại
    pipe.execute()


if __name__ == "__main__":
    print(f"Kết nối tới Redis tại {REDIS_HOST}:{REDIS_PORT}")
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
    try:
        if r.ping():
            print("Kết nối Redis thành công!\n")
    except redis.exceptions.ConnectionError as e:
        print(f"Không thể kết nối tới Redis!\nChi tiết lỗi: {e}")
        exit(1)

    # Khởi tạo Spark
    spark_service = SparkService()
    spark = spark_service.spark_session
    
    # Đọc dữ liệu
    df = spark.read.parquet(str(COVISITATION_MATRIX_FILEPATH))
    print(f"Tổng số dòng: {df.count()}")
    print("Spark đang xử lý song song và ghi dữ liệu xuống Redis...")

    # Giới hạn số lượng kết nối đồng thời vào Redis (tránh làm ngộp Redis)
    df_optimized = df.coalesce(10) 

    # Kích hoạt Spark chạy song song, truyền hàm xử lý đã tách ở ngoài vào
    df_optimized.foreachPartition(send_partition_to_redis)

    print("Đã hoàn thành load TOÀN BỘ dữ liệu vào Redis thành công!")
    spark.stop()
