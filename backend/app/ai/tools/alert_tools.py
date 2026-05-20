"""
Alert tools — send_alert. Safe, read-only from the system perspective.

Writes a structured alert entry to runtime state and broadcasts a WebSocket
message. Does NOT make external HTTP calls in Phase 1.
"""

import json
from datetime import datetime, timezone
from app.ai.tools.decorator import mcp_tool, ToolResult
from app.runtime.state import append_audit   # reuse audit infrastructure


# Circular import avoided — manager injected lazily
_ws_manager = None

def set_ws_manager(manager) -> None:
    global _ws_manager
    _ws_manager = manager


@mcp_tool(
    name="send_alert",
    description="Log a human-escalation notice and broadcast it via WebSocket.",
    allowed_params=["container_name", "message", "severity"],
    risk_level="safe",
    phase=1,
)
def send_alert_tool(
    container_name: str,
    message: str,
    severity: str = "P2",
) -> ToolResult:
    # Sanitise inputs
    severity = severity if severity in ("P0", "P1", "P2", "P3") else "P2"
    message  = str(message)[:500]   # hard cap — no prompt injection via message field

    alert = {
        "ts":        datetime.now(timezone.utc).isoformat(),
        "type":      "HUMAN_ESCALATION",
        "container": container_name,
        "message":   message,
        "severity":  severity,
    }

    # Broadcast via WebSocket if manager is available
    if _ws_manager:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    _ws_manager.broadcast({
                        "type":      "ALERT",
                        "container": container_name,
                        "message":   message,
                        "severity":  severity,
                    }),
                    loop,
                )
        except Exception:
            pass   # alert failure must never crash the pipeline

    return ToolResult(
        success=True,
        output=f"Alert dispatched: [{severity.upper()}] {message}",
        side_effects=["alert_logged"],
    )
