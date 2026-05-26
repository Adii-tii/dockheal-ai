"""
MCP Tool Registry — routes MCPToolCall objects to tool implementations.

Registration is explicit — every tool must be imported and added to TOOL_REGISTRY.
The AI cannot call a tool that isn't registered here.
"""

from app.ai.tools.container_tools import (
    restart_container_tool,
    fetch_logs_tool,
    inspect_container_tool,
    update_memory_limit_tool,
    rollback_image_tool,
    prune_docker_system_tool,
    clear_container_logs_tool,
)
from app.ai.tools.alert_tools import send_alert_tool
from app.ai.tools.decorator import TOOL_METADATA

# ── Registry ───────────────────────────────────────────────────────────────────
# Name → callable wrapper (decorated with @mcp_tool)
TOOL_REGISTRY: dict = {
    "restart_container":    restart_container_tool,
    "fetch_logs":           fetch_logs_tool,
    "inspect_container":    inspect_container_tool,
    "send_alert":           send_alert_tool,
    "prune_docker_system":  prune_docker_system_tool,
    "clear_container_logs": clear_container_logs_tool,
    # Phase 2 — registered but hard-blocked by guardrails
    "update_memory_limit":  update_memory_limit_tool,
    "rollback_image":       rollback_image_tool,
}


def execute_tool(
    tool_name: str,
    parameters: dict,
    investigation_id: str = "manual",
    actor: str = "ai_auto",
) -> dict:
    """
    Route an MCPToolCall to its implementation.

    Returns a ToolResult dict. Never raises — errors are encoded in the result.
    Caller (guardrails layer) is responsible for checking approval before calling this.
    """
    fn = TOOL_REGISTRY.get(tool_name)
    if fn is None:
        return {
            "success": False,
            "output":  f"Unknown tool '{tool_name}'. Registry: {list(TOOL_REGISTRY.keys())}",
            "side_effects": [],
        }

    return fn(
        investigation_id=investigation_id,
        actor=actor,
        **parameters,
    )


import asyncio as _asyncio

async def async_execute_tool(
    tool_name: str,
    parameters: dict,
    investigation_id: str = "manual",
    actor: str = "ai_auto",
) -> dict:
    """
    Async-safe tool executor.

    Tool functions are synchronous and make blocking Docker SDK calls internally.
    This wrapper runs the entire tool in a thread pool so the event loop is
    never frozen during container.restart(), container.logs(), or inspect calls.
    """
    return await _asyncio.to_thread(
        execute_tool,
        tool_name,
        parameters,
        investigation_id,
        actor,
    )


def get_tool_schema_for_prompt() -> list[dict]:
    """
    Returns a minimal tool schema list for injection into the AI system prompt.
    Only Phase 1 tools are included — Phase 2 tools are hidden from the AI.
    """
    return [
        {
            "name":           meta["name"],
            "description":    meta["description"],
            "allowed_params": meta["allowed_params"],
            "risk_level":     meta["risk_level"],
        }
        for meta in TOOL_METADATA.values()
        if meta["phase"] == 1
    ]
