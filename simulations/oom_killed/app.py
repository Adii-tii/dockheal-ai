import time
import sys

print("webapp: starting server...", flush=True)
print("webapp: allocate memory pool", flush=True)
print("FATAL: OutOfMemoryError: Java heap space", flush=True)

# Gradual memory allocation to trigger OOM naturally with minimal memory
l = []
while True:
    l.append("x" * 512 * 1024) # 512KB allocations
    time.sleep(0.1)
