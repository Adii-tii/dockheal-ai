"""
Container telemetry collector.

For each running container, reads:
  - cpu_percent    – % of one CPU core in use  (float, 2-decimal)
  - mem_usage_mb   – resident memory in MiB     (float, 1-decimal)
  - mem_limit_mb   – container memory limit in MiB (float, 1-decimal)
  - mem_percent    – memory utilisation %       (float, 2-decimal)
  - restart_count  – total restart count        (int)
  - uptime_seconds – seconds since last start   (int)

`stream=False` means Docker returns ONE snapshot immediately — no blocking.
CPU% is calculated using the delta formula the Docker CLI uses:
  cpu% = (cpu_delta / system_delta) * num_cpus * 100
"""

import docker
from datetime import datetime, timezone

try:
    client = docker.from_env()
except Exception as e:
    print(f"CRITICAL: Could not connect to Docker in metrics.py: {e}")
    client = None


def _cpu_percent(stats: dict) -> float:
    """Derive CPU % from a single stats snapshot (uses delta fields)."""
    try:
        cpu_stats = stats["cpu_stats"]
        precpu_stats = stats["precpu_stats"]

        cpu_delta = (
            cpu_stats["cpu_usage"]["total_usage"]
            - precpu_stats["cpu_usage"]["total_usage"]
        )
        system_delta = (
            cpu_stats.get("system_cpu_usage", 0)
            - precpu_stats.get("system_cpu_usage", 0)
        )

        # Number of CPUs available to the container
        num_cpus = len(cpu_stats["cpu_usage"].get("percpu_usage") or []) or 1

        if system_delta > 0 and cpu_delta >= 0:
            return round((cpu_delta / system_delta) * num_cpus * 100, 2)
        return 0.0
    except (KeyError, ZeroDivisionError):
        return 0.0


def _mem_stats(stats: dict) -> dict:
    """Extract memory usage, limit, and percent."""
    try:
        mem = stats["memory_stats"]
        usage = mem.get("usage", 0)

        # Subtract cache so we match what `docker stats` shows
        cache = mem.get("stats", {}).get("cache", 0)
        rss = max(usage - cache, 0)

        limit = mem.get("limit", 1)
        pct = round((rss / limit) * 100, 2) if limit > 0 else 0.0

        return {
            "mem_usage_mb": round(rss / (1024 ** 2), 1),
            "mem_limit_mb": round(limit / (1024 ** 2), 1),
            "mem_percent": pct,
        }
    except (KeyError, ZeroDivisionError):
        return {"mem_usage_mb": 0.0, "mem_limit_mb": 0.0, "mem_percent": 0.0}


def _uptime_seconds(attrs: dict) -> int:
    """Seconds elapsed since the container last started."""
    try:
        started_at_str = attrs["State"]["StartedAt"]
        # Docker timestamps look like: 2024-11-01T12:34:56.789012345Z
        # Strip nanoseconds beyond 6 digits so Python's fromisoformat can parse it
        started_at_str = started_at_str[:26] + "Z"
        started_at = datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - started_at
        return max(int(delta.total_seconds()), 0)
    except Exception:
        return 0


def get_all_metrics() -> list[dict]:
    """
    Return telemetry for every container (running or not).
    For stopped containers, stats are zeros.
    """
    if not client:
        return []

    results = []

    for container in client.containers.list(all=True):
        attrs = container.attrs
        restart_count = attrs.get("HostConfig", {}).get("RestartPolicy", {})
        # RestartCount lives directly in State
        restart_count = attrs.get("RestartCount", 0)
        uptime = _uptime_seconds(attrs) if container.status == "running" else 0

        entry = {
            "id": container.short_id,
            "name": container.name,
            "status": container.status,
            "restart_count": restart_count,
            "uptime_seconds": uptime,
            # stats only meaningful while running
            "cpu_percent": 0.0,
            "mem_usage_mb": 0.0,
            "mem_limit_mb": 0.0,
            "mem_percent": 0.0,
        }

        if container.status == "running":
            try:
                # stream=False → single snapshot, non-blocking
                stats = container.stats(stream=False)
                entry["cpu_percent"] = _cpu_percent(stats)
                entry.update(_mem_stats(stats))
            except Exception as e:
                print(f"[METRICS] Could not get stats for {container.name}: {e}")

        results.append(entry)

    return results


def get_container_metrics(name: str) -> dict | None:
    """Single-container metrics by name. Returns None if not found."""
    if not client:
        return None
    try:
        container = client.containers.get(name)
    except docker.errors.NotFound:
        return None

    attrs = container.attrs
    restart_count = attrs.get("RestartCount", 0)
    uptime = _uptime_seconds(attrs) if container.status == "running" else 0

    entry = {
        "id": container.short_id,
        "name": container.name,
        "status": container.status,
        "restart_count": restart_count,
        "uptime_seconds": uptime,
        "cpu_percent": 0.0,
        "mem_usage_mb": 0.0,
        "mem_limit_mb": 0.0,
        "mem_percent": 0.0,
    }

    if container.status == "running":
        try:
            stats = container.stats(stream=False)
            entry["cpu_percent"] = _cpu_percent(stats)
            entry.update(_mem_stats(stats))
        except Exception as e:
            print(f"[METRICS] Could not get stats for {name}: {e}")

    return entry
