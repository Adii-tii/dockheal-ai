"""
Phase 1 container tools — restart, fetch_logs, inspect_container.

Constraints enforced here:
  - No subprocess, no shell, no os.system.
  - Only explicit named Docker SDK calls.
  - Each function returns a ToolResult via the @mcp_tool decorator.
  - Tools never access Docker API directly — always via the shared client.
"""

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
