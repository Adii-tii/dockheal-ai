"""
Phase 1 container tools — restart, fetch_logs, inspect_container.

Constraints enforced here:
  - No subprocess, no shell, no os.system.
  - Only explicit named Docker SDK calls.
  - Each function returns a ToolResult via the @mcp_tool decorator.
  - Tools never access Docker API directly — always via the shared client.

All functions here are synchronous (required by the @mcp_tool decorator and
execute_tool registry). The blocking Docker calls inside each function are
safe to use from background threads. When calling from an async context use
`asyncio.to_thread(tool_fn, ...)` via `async_execute_tool` in registry.py.
"""

import asyncio
import docker
from app.ai.tools.decorator import mcp_tool, ToolResult

try:
    _client = docker.from_env()
except Exception as e:
    print(f"[CONTAINER_TOOLS] Docker unavailable: {e}")
    _client = None


@mcp_tool(
    name="restart_container",
    description="Restart a running Docker container. Sends SIGTERM then SIGKILL after timeout.",
    allowed_params=["container_name"],
    risk_level="low",
    phase=1,
)
def restart_container_tool(container_name: str) -> ToolResult:
    if container_name.startswith("mock-"):
        return ToolResult(
            success=True,
            output=f"{container_name} restarted successfully (was: exited, now: running)",
            side_effects=[f"Container '{container_name}' restarted"],
        )
    if not _client:
        return ToolResult(success=False, output="Docker client unavailable")
    try:
        container = _client.containers.get(container_name)
        prev_status = container.status
        container.restart(timeout=10)
        container.reload()
        return ToolResult(
            success=True,
            output=f"{container_name} restarted successfully (was: {prev_status}, now: {container.status})",
            side_effects=[f"Container '{container_name}' restarted"],
        )
    except docker.errors.NotFound:
        return ToolResult(success=False, output=f"Container '{container_name}' not found")
    except Exception as e:
        return ToolResult(success=False, output=str(e))


@mcp_tool(
    name="fetch_logs",
    description="Fetch the last N lines of stdout/stderr from a container. Read-only.",
    allowed_params=["container_name", "tail"],
    risk_level="safe",
    phase=1,
)
def fetch_logs_tool(container_name: str, tail: int = 50) -> ToolResult:
    if container_name.startswith("mock-"):
        if "oom" in container_name:
            logs = "[mock] 2026-05-23T18:00:00Z webapp: starting server...\n[mock] 2026-05-23T18:01:15Z webapp: allocate memory pool\n[mock] 2026-05-23T18:02:30Z FATAL: OutOfMemoryError: Java heap space\n[mock] 2026-05-23T18:02:31Z Kern: Out of memory: Kill process 12345 (java) score 850 or sacrifice child"
        elif "crash" in container_name:
            logs = "[mock] 2026-05-23T18:00:00Z db: starting PostgreSQL...\n[mock] 2026-05-23T18:00:01Z FATAL:  lock file \"postmaster.pid\" already exists\n[mock] 2026-05-23T18:00:01Z HINT:  Is another postmaster (PID 48) running in data directory \"/var/lib/postgresql/data\"?"
        elif "nginx" in container_name:
            logs = "[mock] 2026-05-23T18:00:00Z nginx: starting worker processes...\n[mock] 2026-05-23T18:05:12Z [error] 31#31: *124 connect() failed (111: Connection refused) while connecting to upstream, client: 127.0.0.1, server: localhost, request: \"GET /api/v1/users HTTP/1.1\", upstream: \"http://127.0.0.1:8080/api/v1/users\""
        elif "rate" in container_name:
            logs = "[mock] 2026-05-23T18:00:00Z gateway: rate limiter active\n[mock] 2026-05-23T18:02:40Z WARNING: rate limit breached for client 192.168.1.100 (1500 req/sec > limit 1000)"
        elif "disk" in container_name:
            logs = "[mock] 2026-05-23T18:00:00Z logger: flushing write buffer\n[mock] 2026-05-23T18:01:05Z ERROR: write failed: No space left on device (ENOSPC)"
        else:
            logs = "[mock] container logs"
        return ToolResult(success=True, output=logs)
    if not _client:
        return ToolResult(success=False, output="Docker client unavailable")
    tail = min(int(tail), 200)   # hard cap — AI cannot request unbounded logs
    try:
        container = _client.containers.get(container_name)
        raw: bytes = container.logs(tail=tail, timestamps=True)
        lines = raw.decode("utf-8", errors="replace").splitlines()
        return ToolResult(
            success=True,
            output="\n".join(lines),
            side_effects=[],   # read-only
        )
    except docker.errors.NotFound:
        return ToolResult(success=False, output=f"Container '{container_name}' not found")
    except Exception as e:
        return ToolResult(success=False, output=str(e))


@mcp_tool(
    name="inspect_container",
    description="Return key state fields from a container's attrs. Read-only.",
    allowed_params=["container_name"],
    risk_level="safe",
    phase=1,
)
def inspect_container_tool(container_name: str) -> ToolResult:
    if container_name.startswith("mock-"):
        import json
        summary = {
            "id":            f"mock-{container_name}-id",
            "name":          container_name,
            "status":        "exited" if "oom" in container_name or "crash" in container_name else "running",
            "image":         f"{container_name}:latest",
            "restart_count": 5 if "crash" in container_name else 0,
            "exit_code":     137 if "oom" in container_name else (1 if "crash" in container_name else 0),
            "oom_killed":    "oom" in container_name,
            "started_at":    "2026-05-23T18:00:00Z",
            "finished_at":   "2026-05-23T18:02:30Z",
            "health":        "unhealthy" if "nginx" in container_name else "healthy",
        }
        return ToolResult(
            success=True,
            output=json.dumps(summary, indent=2),
            side_effects=[],
        )
    if not _client:
        return ToolResult(success=False, output="Docker client unavailable")
    try:
        container = _client.containers.get(container_name)
        attrs = container.attrs
        state = attrs.get("State", {})
        # Return a constrained subset — not the full 200-field attrs blob
        summary = {
            "id":            container.short_id,
            "name":          container.name,
            "status":        container.status,
            "image":         container.image.tags[0] if container.image.tags else "unknown",
            "restart_count": attrs.get("RestartCount", 0),
            "exit_code":     state.get("ExitCode"),
            "oom_killed":    state.get("OOMKilled", False),
            "started_at":    state.get("StartedAt"),
            "finished_at":   state.get("FinishedAt"),
            "health":        state.get("Health", {}).get("Status", "no-healthcheck"),
        }
        import json
        return ToolResult(
            success=True,
            output=json.dumps(summary, indent=2),
            side_effects=[],
        )
    except docker.errors.NotFound:
        return ToolResult(success=False, output=f"Container '{container_name}' not found")
    except Exception as e:
        return ToolResult(success=False, output=str(e))


@mcp_tool(
    name="prune_docker_system",
    description="Prune unused Docker resources (stopped containers, dangling images, unused networks, and volumes) to reclaim disk space (resolves ENOSPC/disk full errors).",
    allowed_params=[],
    risk_level="medium",
    phase=1,
)
def prune_docker_system_tool() -> ToolResult:
    if not _client:
        return ToolResult(success=False, output="Docker client unavailable")
    try:
        reclaimed_bytes = 0
        
        # Prune containers
        res_c = _client.containers.prune()
        reclaimed_bytes += res_c.get("SpaceReclaimed", 0) or 0
        
        # Prune volumes
        res_v = _client.volumes.prune()
        reclaimed_bytes += res_v.get("SpaceReclaimed", 0) or 0
        
        # Prune images
        res_i = _client.images.prune()
        reclaimed_bytes += res_i.get("SpaceReclaimed", 0) or 0
        
        reclaimed_mb = reclaimed_bytes / (1024 * 1024)
        output = f"Successfully pruned unused Docker system resources. Reclaimed {reclaimed_mb:.2f} MB of disk space."
        return ToolResult(
            success=True,
            output=output,
            side_effects=["Pruned stopped containers, dangling images, and unused volumes."],
        )
    except Exception as e:
        return ToolResult(success=False, output=f"Failed to prune Docker system: {e}")


@mcp_tool(
    name="clear_container_logs",
    description="Clear (truncate) the log file of a container to free up disk space.",
    allowed_params=["container_name"],
    risk_level="medium",
    phase=1,
)
def clear_container_logs_tool(container_name: str) -> ToolResult:
    if container_name.startswith("mock-") or container_name.startswith("dockheal-sim-"):
        return ToolResult(
            success=True,
            output=f"Successfully truncated logs for container '{container_name}' (simulated).",
            side_effects=[f"Cleared logs of container '{container_name}'"],
        )
    if not _client:
        return ToolResult(success=False, output="Docker client unavailable")
    try:
        container = _client.containers.get(container_name)
        log_path = container.attrs.get("LogPath")
        if not log_path:
            return ToolResult(success=False, output=f"Could not locate log path for '{container_name}'")
        
        import os
        if os.path.exists(log_path):
            with open(log_path, "r+") as f:
                f.truncate(0)
            return ToolResult(
                success=True,
                output=f"Successfully truncated container log file: {log_path}",
                side_effects=[f"Cleared logs of container '{container_name}'"],
            )
        else:
            return ToolResult(success=False, output=f"Log file {log_path} does not exist or is inaccessible.")
    except Exception as e:
        return ToolResult(success=False, output=f"Failed to clear container logs: {e}")


# ── Phase 2 stubs (registered but hard-blocked by guardrails) ─────────────────

@mcp_tool(
    name="update_memory_limit",
    description="[PHASE 2] Update the memory limit of a running container.",
    allowed_params=["container_name", "memory_mb"],
    risk_level="medium",
    phase=2,
)
def update_memory_limit_tool(container_name: str, memory_mb: int) -> ToolResult:
    return ToolResult(success=False, output="Phase 2 tool — not yet enabled")


@mcp_tool(
    name="rollback_image",
    description="[PHASE 2] Pull previous image tag and redeploy container.",
    allowed_params=["container_name", "image_tag"],
    risk_level="high",
    phase=2,
)
def rollback_image_tool(container_name: str, image_tag: str) -> ToolResult:
    return ToolResult(success=False, output="Phase 2 tool — not yet enabled")
