## python -m  src.test.test_redis

import os
from dotenv import load_dotenv
import redis

load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

print(f"Kết nối tới Redis tại {REDIS_HOST}:{REDIS_PORT} ")

# Kết nối tới Redis, decode_responses=True giúp tự động chuyển bytes thành string (đỡ phải .decode("utf-8"))
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)

try:

    if r.ping():
        print("Kết nối Redis thành công!\n")

    print("--- Đang chèn dữ liệu mẫu để test... ---")
    
    r.set("user:1001:name", "Sandaria", ex=10)                            

    r.hset("user:1001:info", mapping={"age": "22", "role": "dev"})
    r.expire("user:1001:info", 10)  # <-- Cài hết hạn 10 giây cho Hash
    
    r.rpush("user:1001:cart", "item_A", "item_B", "item_C")         
    r.expire("user:1001:cart", 10)  # <-- Cài hết hạn 10 giây cho List
    
    print("Đã chèn dữ liệu mẫu thành công.\n")

    # 3. Quét và in ra toàn bộ dữ liệu đang có (Đoạn code của bạn)
    print("--- Danh sách Key và Dữ liệu trong Redis: ---")
    for key in r.scan_iter("*"):
        # Vì đã có decode_responses=True ở trên, r.type(key) sẽ trả về string luôn, không cần .decode()
        data_type = r.type(key)
        
        if data_type == "string":
            print(f"[String] {key} -> {r.get(key)}")
        elif data_type == "hash":
            print(f"[Hash]   {key} -> {r.hgetall(key)}")
        elif data_type == "list":
            print(f"[List]   {key} -> {r.lrange(key, 0, -1)}")
            
    print("Kết thúc test")

except redis.exceptions.ConnectionError as e:
    print(f"Không thể kết nối tới Redis! Hãy kiểm tra lại Redis Server hoặc cấu hình PORT.")
    print(f"Chi tiết lỗi: {e}")
