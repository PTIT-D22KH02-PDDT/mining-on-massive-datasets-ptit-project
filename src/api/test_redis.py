import os
import redis

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)

for key in r.scan_iter("*"):
    data_type = r.type(key).decode('utf-8')
    if data_type == 'string':
        print(f"{key}: {r.get(key)}\n")
    elif data_type == 'hash':
        print(f"{key}: {r.hgetall(key)}\n")
    elif data_type == 'list':
        print(f"{key}: {r.lrange(key, 0, -1)}\n")