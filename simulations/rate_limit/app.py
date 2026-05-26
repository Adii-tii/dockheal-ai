print("gateway: rate limiter active", flush=True)
print("WARNING: rate limit breached for client 192.168.1.100 (1500 req/sec > limit 1000)", flush=True)

# Infinite loop to occupy the allowed CPU quota
while True:
    pass
