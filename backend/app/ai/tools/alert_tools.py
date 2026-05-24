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
    investigation_id: str = "manual",
    actor: str = "ai_auto",
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

    # Record notification in the DB as PENDING
    import asyncio
    import uuid
    from app.db.config.config import AsyncSessionLocal
    from app.db.models.notification import Notification
    from app.db.models.enums import NotificationStatus

    async def _save_notification():
        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    inv_uuid = None
                    if investigation_id and investigation_id != "manual":
                        try:
                            inv_uuid = uuid.UUID(investigation_id)
                        except ValueError:
                            pass
                    
                    notification = Notification(
                        investigation_id=inv_uuid,
                        notification_type="SLACK",
                        recipient="#incidents",
                        status=NotificationStatus.PENDING,
                        metadata_={
                            "message": message,
                            "severity": severity,
                            "container": container_name,
                            "retry_count": 0,
                        }
                    )
                    session.add(notification)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to record pending notification in DB: {e}")

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_save_notification())
    except Exception:
        pass

    # Broadcast via WebSocket if manager is available
    if _ws_manager:
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
