import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Callable, List, Dict, Any

from app.db.config.config import AsyncSessionLocal
from app.db.dao.notification_dao import NotificationDAO
from app.db.models.notification import Notification
from app.db.models.enums import NotificationStatus
from app.runtime.state import worker_statuses

logger = logging.getLogger(__name__)

# Control variables for the worker task
notification_task = None
_notification_hooks: List[Callable[[Notification, str], None]] = []

def register_notification_hook(callback: Callable[[Notification, str], None]) -> None:
    """
    Register a callback hook to be executed on notification events.
    The callback signature should be: callback(notification: Notification, event_type: str)
    Where event_type is 'sent', 'failed', or 'dead_lettered'.
    """
    if callback not in _notification_hooks:
        _notification_hooks.append(callback)

def _trigger_hooks(notification: Notification, event_type: str) -> None:
    for hook in _notification_hooks:
        try:
            hook(notification, event_type)
        except Exception as e:
            logger.error(f"[NOTIFICATION_WORKER] Hook execution failed: {e}", exc_info=True)

def _get_log_dir() -> str:
    # Resolve logs directory relative to backend
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    log_dir = os.path.join(base_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    return log_dir

def log_to_dead_letter(payload: Dict[str, Any], error_msg: str, category: str = "notifications") -> None:
    """Log a failed payload to the dead letter file."""
    log_dir = _get_log_dir()
    file_path = os.path.join(log_dir, f"dead_letter_{category}.log")
    
    timestamp = datetime.now(timezone.utc).isoformat()
    log_entry = {
        "timestamp": timestamp,
        "payload": payload,
        "error": error_msg
    }
    
    try:
        import json
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
        logger.warning(f"[DEAD_LETTER] Recorded failed {category} item to {file_path}")
    except Exception as e:
        logger.error(f"[DEAD_LETTER] Failed to write to dead letter log: {e}", exc_info=True)

async def dispatch_notification(notification: Notification) -> bool:
    """
    Simulates sending the notification to external systems.
    Returns True if successful, False otherwise.
    """
    # Simulate API latency
    await asyncio.sleep(0.5)
    
    recipient = notification.recipient
    meta = notification.metadata_ or {}
    message = meta.get("message", "")
    
    # Validation/Error triggers for testing retry & dead letter logic
    if "error" in recipient.lower() or "fail" in recipient.lower() or "error" in message.lower():
        raise RuntimeError("Simulated external delivery API connection failure.")
        
    logger.info(f"[NOTIFICATION_WORKER] Successfully sent {notification.notification_type} to {recipient}")
    return True

async def process_pending_notifications() -> int:
    """Query and process PENDING notifications from the DB."""
    async with AsyncSessionLocal() as session:
        notification_dao = NotificationDAO(session)
        # Fetch pending notifications
        pending = await notification_dao.get_pending(limit=20)
        if not pending:
            return 0
            
        processed_count = 0
        for notification in pending:
            # Check for retry backoff eligibility
            meta = dict(notification.metadata_ or {})
            retry_count = meta.get("retry_count", 0)
            last_attempt = meta.get("last_attempt_at")
            
            if last_attempt:
                last_dt = datetime.fromisoformat(last_attempt)
                age_seconds = (datetime.now(timezone.utc) - last_dt).total_seconds()
                # Exponential backoff: retry after 2^retry_count seconds (e.g. 2s, 4s, 8s...)
                backoff_required = 2 ** retry_count
                if age_seconds < backoff_required:
                    # Skip for now, not yet eligible to retry
                    continue
                    
            processed_count += 1
            meta["last_attempt_at"] = datetime.now(timezone.utc).isoformat()
            
            try:
                # Dispatch notification
                success = await dispatch_notification(notification)
                if success:
                    # Update status to SENT
                    await notification_dao.mark_sent(notification.id, metadata_=meta)
                    # Trigger success hook
                    _trigger_hooks(notification, "sent")
            except Exception as e:
                # Handle dispatch failure
                retry_count += 1
                meta["retry_count"] = retry_count
                meta["last_error"] = str(e)
                
                # Check if retry limit exceeded (max 3 attempts)
                if retry_count >= 3:
                    # Mark status as FAILED and dead-letter it
                    await notification_dao.update_by_id(
                        notification.id,
                        status=NotificationStatus.FAILED,
                        metadata_=meta
                    )
                    
                    payload = {
                        "id": str(notification.id),
                        "investigation_id": str(notification.investigation_id) if notification.investigation_id else None,
                        "notification_type": notification.notification_type,
                        "recipient": notification.recipient,
                        "metadata": meta,
                        "created_at": notification.created_at.isoformat() if hasattr(notification.created_at, "isoformat") else str(notification.created_at)
                    }
                    log_to_dead_letter(payload, str(e), category="notifications")
                    _trigger_hooks(notification, "dead_lettered")
                else:
                    # Mark as failed but keep it PENDING so it can be retried later
                    await notification_dao.update_by_id(
                        notification.id,
                        status=NotificationStatus.PENDING,
                        metadata_=meta
                    )
                    _trigger_hooks(notification, "failed")
                    
        await session.commit()
        return processed_count

async def notification_loop():
    """Main background loop for notification processing."""
    logger.info("[NOTIFICATION_WORKER] Starting background notification worker loop...")
    while True:
        try:
            worker_statuses["notifications"] = "healthy"
            processed = await process_pending_notifications()
            if processed > 0:
                logger.debug(f"[NOTIFICATION_WORKER] Processed {processed} notification(s).")
        except asyncio.CancelledError:
            logger.info("[NOTIFICATION_WORKER] Notification worker loop cancelled. Stopping.")
            break
        except Exception as e:
            logger.error(f"[NOTIFICATION_WORKER] Error in notification worker: {e}", exc_info=True)
            worker_statuses["notifications"] = "degraded"
            
        await asyncio.sleep(5)  # Poll every 5 seconds

def start_notification_worker():
    """Spawn the notification worker task."""
    global notification_task
    try:
        loop = asyncio.get_running_loop()
        notification_task = loop.create_task(notification_loop())
        logger.info("[NOTIFICATION_WORKER] Notification task spawned successfully.")
    except RuntimeError:
        logger.warning("[NOTIFICATION_WORKER] No running event loop. Running tasks requires a running loop context.")

def stop_notification_worker():
    """Stop the notification worker task."""
    global notification_task
    if notification_task and not notification_task.done():
        notification_task.cancel()
        logger.info("[NOTIFICATION_WORKER] Stop requested for notification task.")
