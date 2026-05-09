import redis
r = redis.Redis(host='localhost', port=6379, db=0)

for key in r.scan_iter("*"):
    data_type = r.type(key).decode('utf-8')
    if data_type == 'string':
        print(f"{key}: {r.get(key)}\n")
    elif data_type == 'hash':
        print(f"{key}: {r.hgetall(key)}\n")
    elif data_type == 'list':
        print(f"{key}: {r.lrange(key, 0, -1)}\n")
    # Add other types as needed
