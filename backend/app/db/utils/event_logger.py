"""
Event Logger — centralized timeline logging and lifecycle transitions for investigations.
Guarantees database writes commit before broadcasts are sent to WebSockets.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import uuid

from sqlalchemy import select, func, event
from sqlalchemy.orm import Session, joinedload
from app.db.models import Investigation, InvestigationTimelineEvent, LifecycleState, SeverityLevel, SourceType
from app.web_sockets.manager import manager

logger = logging.getLogger(__name__)


async def broadcast_with_retry(message: dict, max_retries: int = 3, backoff: float = 0.5):
    """Broadcast websocket message with exponential backoff on failure."""
    for attempt in range(max_retries):
        try:
            await manager.broadcast(message)
            break
        except Exception as e:
            logger.warning(f"WebSocket broadcast attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                logger.error(f"WebSocket broadcast failed after {max_retries} attempts.")
            else:
                await asyncio.sleep(backoff * (2 ** attempt))


@event.listens_for(Session, "after_commit")
def trigger_broadcasts(session: Session):
    """Trigger queued websocket broadcasts after database transaction commits."""
    queue = session.info.get("broadcast_queue", [])
    if not queue:
        return
    try:
        loop = asyncio.get_running_loop()
        for msg in queue:
            loop.create_task(broadcast_with_retry(msg))
    except RuntimeError:
        # No running event loop (e.g. migrations or CLI tests)
        pass
    finally:
        queue.clear()


def queue_broadcast(session: Session, message: dict):
    """Helper to queue a broadcast message on the session."""
    session.info.setdefault("broadcast_queue", []).append(message)


async def log_timeline_event(
    session: Any,
    investigation_id: uuid.UUID,
    event_type: str,
    title: str,
    description: Optional[str] = None,
    source_type: SourceType = SourceType.AI_AGENT,
    severity: Optional[SeverityLevel] = None,
    correlation_id: Optional[str] = None,
    extra_context: Optional[dict] = None,
    raw_data: Optional[dict] = None,
    tool_output: Optional[dict] = None,
) -> InvestigationTimelineEvent:
    """
    Log a timeline event to the database.
    Acquires a row-level lock on the parent investigation to ensure sequence number integrity,
    generates the next sequence number, creates the record, and queues the websocket broadcast.
    """
    # 1. Row-level lock on the parent investigation
    stmt_inv = (
        select(Investigation)
        .where(Investigation.id == investigation_id)
        .with_for_update()
    )
    res = await session.execute(stmt_inv)
    investigation = res.scalar_one_or_none()
    if not investigation:
        raise ValueError(f"Investigation with ID {investigation_id} not found.")

    # 2. Compute next sequence number atomically
    stmt_seq = select(
        func.coalesce(func.max(InvestigationTimelineEvent.sequence_number), 0)
    ).where(InvestigationTimelineEvent.investigation_id == investigation_id)
    
    res_seq = await session.execute(stmt_seq)
    next_seq = res_seq.scalar_one() + 1

    # 3. Create event
    event_obj = InvestigationTimelineEvent(
        investigation_id=investigation_id,
        event_type=event_type,
        sequence_number=next_seq,
        correlation_id=correlation_id,
        title=title,
        description=description,
        source_type=source_type,
        severity=severity,
        extra_context=extra_context,
        raw_data=raw_data,
        tool_output=tool_output,
    )
    session.add(event_obj)
    await session.flush()

    # 4. Queue broadcast
    # Convert DB model attributes into serialization format for client consumption
    event_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": event_type,
        "sequence_number": next_seq,
        "correlation_id": correlation_id,
        "title": title,
        "description": description,
        "source": source_type.value if hasattr(source_type, "value") else str(source_type),
        "severity": severity.value if (severity and hasattr(severity, "value")) else (str(severity) if severity else None),
        "extra_context": extra_context,
        "raw_data": raw_data,
        "tool_output": tool_output,
    }

    queue_broadcast(session, {
        "type": "AI_TIMELINE_EVENT",
        "investigation_id": str(investigation_id),
        "event": event_data
    })

    return event_obj


async def update_lifecycle(
    session: Any,
    investigation_id: uuid.UUID,
    new_state: LifecycleState,
    correlation_id: Optional[str] = None,
    extra_fields: Optional[Dict[str, Any]] = None,
) -> Investigation:
    """
    Update the lifecycle state of an investigation.
    Runs under optimistic locking protection via SQLAlchemy mapper attributes.
    Queues a lifecycle websocket broadcast upon commit.
    """
    stmt = (
        select(Investigation)
        .options(joinedload(Investigation.container))
        .where(Investigation.id == investigation_id)
    )
    res = await session.execute(stmt)
    investigation = res.scalar_one_or_none()
    if not investigation:
        raise ValueError(f"Investigation with ID {investigation_id} not found.")

    old_state = investigation.lifecycle_state

    # Update state
    investigation.lifecycle_state = new_state
    if correlation_id:
        investigation.correlation_id = correlation_id
    if extra_fields:
        for k, v in extra_fields.items():
            setattr(investigation, k, v)

    # Queue broadcast
    container_name = (
        investigation.container.container_name if investigation.container else "unknown"
    )
    severity = (
        investigation.severity_level.value
        if hasattr(investigation.severity_level, "value")
        else str(investigation.severity_level)
    )

    queue_broadcast(session, {
        "type": "AI_LIFECYCLE",
        "investigation_id": str(investigation_id),
        "container": container_name,
        "severity": severity,
        "from_state": old_state.value if hasattr(old_state, "value") else str(old_state),
        "to_state": new_state.value if hasattr(new_state, "value") else str(new_state),
    })

    return investigation
