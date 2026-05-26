import time

print("nginx: starting worker processes...", flush=True)
time.sleep(8)
print("[error] connect() failed (111: Connection refused) while connecting to upstream", flush=True)

# Touch lockfile to trigger healthcheck failure
with open("/tmp/unhealthy", "w") as f:
    f.write("unhealthy")

while True:
    time.sleep(3600)
