import sys

print("db: starting PostgreSQL...", flush=True)
print("FATAL:  lock file \"postmaster.pid\" already exists", flush=True)
print("HINT:  Is another postmaster (PID 48) running in data directory \"/var/lib/postgresql/data\"?", flush=True)
sys.exit(1)
