import asyncio
import logging
import uuid
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError

from app.services.health_engine import detect_incidents
from app.services.recovery import attempt_deterministic_restart
from app.runtime.state import (
    active_incidents,
    manually_stopped,
    context_store,
    investigation_states,
    remediation_timestamps,
    COOLDOWN_SECONDS,
    worker_statuses,
)
from app.web_sockets.manager import manager
from app.context.aggregator import build_investigation_packet
from app.ai.investigator import investigate

from app.db.config.config import AsyncSessionLocal
from app.db.dao.container_dao import ContainerDAO
from app.db.dao.system_metric_dao import SystemMetricDAO
from app.db.dao.investigation_dao import InvestigationDAO
from app.db.models.investigation import Investigation
from app.db.models.enums import ContainerStatus, HealthStatus, LifecycleState, SeverityLevel

logger = logging.getLogger(__name__)

# To control task cancellation and graceful shutdown
monitor_task = None
metrics_archiver_task = None

async def sync_containers():
    """Sync all containers from Docker to PostgreSQL."""
    from app.docker_monitor.container import get_all_containers
    containers = get_all_containers()
    
    async with AsyncSessionLocal() as session:
        try:
            async with session.begin():
                container_dao = ContainerDAO(session)
                for c in containers:
                    try:
                        c_status = ContainerStatus(c["status"])
                    except ValueError:
                        c_status = ContainerStatus.UNKNOWN

                    try:
                        c_health = HealthStatus(c["health"])
                    except ValueError:
                        c_health = HealthStatus.NONE
                    
                    image_name = c["image"][0] if c["image"] else "unknown"
                    
                    await container_dao.upsert_by_runtime_id(
                        runtime_id=c["id"],
                        container_name=c["name"],
                        image_name=image_name,
                        status=c_status,
                        health_status=c_health,
                        labels=c.get("labels", {}),
                        ports=c.get("ports", []),
                        runtime_metadata=c.get("runtime_metadata", {}),
                        last_seen=datetime.now(timezone.utc),
                    )
        except Exception as e:
            logger.error(f"[MONITOR] Failed to sync containers to DB: {e}")


def _should_skip_investigation(container_name: str, active_inv_exists: bool) -> tuple[bool, str]:
    """Check if an investigation should be skipped based on in-memory or DB state."""
    # Cooldown window
    last = remediation_timestamps.get(container_name)
    if last:
        age = (datetime.now(timezone.utc) - last).total_seconds()
        if age < COOLDOWN_SECONDS:
            return True, f"cooldown active ({int(COOLDOWN_SECONDS - age)}s remaining)"

    if active_inv_exists:
        return True, "already has an active investigation"

    return False, ""


async def _handle_incident(incident: dict, container_name: str):
    # ── Build investigation packet ─────────────────────────────────────────────
    logger.info(f"[CONTEXT] Building packet for {container_name}")
    try:
        packet = build_investigation_packet(container_name, incident)
        context_store[container_name] = packet
        investigation_id = packet["investigation_id"]
        score = packet["assessment"]["severity_score"]
        logger.info(f"[CONTEXT] Ready — score={score}, id={investigation_id}")
    except Exception as e:
        logger.error(f"[CONTEXT] Failed to build packet for {container_name}: {e}")
        return

    # ── Check active investigation in DB & enforce lock ─────────────────────────
    async with AsyncSessionLocal() as session:
        try:
            async with session.begin():
                container_dao = ContainerDAO(session)
                investigation_dao = InvestigationDAO(session)
                
                container = await container_dao.get_by_name(container_name)
                if not container:
                    logger.warning(f"[MONITOR] Container {container_name} not found in DB. Cannot create investigation.")
                    return

                active_inv = await investigation_dao.get_active_for_container(container.id)
                active_inv_exists = active_inv is not None

                # ── Duplicate / cooldown guard ─────────────────────────────────────────────
                skip, reason = _should_skip_investigation(container_name, active_inv_exists)
                if skip:
                    logger.info(f"[MONITOR] Skipping {container_name}: {reason}")
                    return

                severity_val = SeverityLevel(incident.get("severity", "P2"))
                inv = Investigation(
                    id=uuid.UUID(investigation_id) if isinstance(investigation_id, str) else investigation_id,
                    container_id=container.id,
                    title=f"Incident in container {container_name}",
                    incident_summary=incident.get("message"),
                    severity_level=severity_val,
                    lifecycle_state=LifecycleState.DETECTED,
                    started_at=datetime.now(timezone.utc),
                    created_by="monitor_worker",
                )
                session.add(inv)
                # Keep in-memory investigation states synced for UI compatibility
                investigation_states[investigation_id] = {
                    "state": "DETECTED",
                    "container": container_name,
                }
        except IntegrityError as ie:
            # DB-level partial unique constraint blocked insert because container has active investigation
            logger.warning(f"[MONITOR] DB-level lock active: Unique constraint prevented duplicate investigation for {container_name}: {ie}")
            return
        except Exception as e:
            logger.error(f"[MONITOR] Failed to create investigation in DB: {e}")
            return

    # ── Broadcast INCIDENT (with context) ─────────────────────────────────────
    await manager.broadcast({
        "type":             "INCIDENT",
        "incident":         incident,
        "context":          packet,
        "investigation_id": investigation_id,
    })

    # ── Deterministic Recovery Attempt (Bypassed) ──────────────────────────────
    # Bypassed deterministic recovery attempt as requested by the user,
    # so we spin up the investigation first to analyze why the container failed.
    packet["recovery_attempt"] = {
        "attempted": False,
        "success": False,
        "reason_skipped": "spin_up_investigation_first"
    }
    active_incidents.add(container_name)

    # ── ALWAYS run AI investigation in parallel ────────────────────────────────
    logger.info(f"[AI] Invoking AI investigation for {container_name} (score={score})")
    
    async def run_ai():
        async def broadcast_fn(msg: dict):
            await manager.broadcast(msg)
        try:
            await investigate(packet, broadcast_fn)
        except Exception as e:
            logger.error(f"[AI] Investigation failed for {container_name}: {e}")
            investigation_states[investigation_id]["state"] = "ESCALATED"
            # Update DB lifecycle to ESCALATED
            async with AsyncSessionLocal() as session:
                try:
                    async with session.begin():
                        from app.db.utils.event_logger import update_lifecycle
                        await update_lifecycle(session, uuid.UUID(investigation_id), LifecycleState.ESCALATED)
                except Exception as db_err:
                    logger.error(f"[AI] Failed to update state to ESCALATED in DB: {db_err}")

    asyncio.create_task(run_ai())


async def monitor_loop():
    """Main background monitor loop."""
    logger.info("[MONITOR] Starting background monitor loop...")
    while True:
        try:
            worker_statuses["monitor"] = "healthy"
            # 1. Sync containers
            await sync_containers()

            # 2. Detect incidents
            incidents = detect_incidents()
            for incident in incidents:
                container_name = incident["container"]
                if container_name in manually_stopped:
                    continue

                # Process incident asynchronously
                await _handle_incident(incident, container_name)

        except asyncio.CancelledError:
            logger.info("[MONITOR] Monitor loop task cancelled. Stopping.")
            break
        except Exception as e:
            logger.error(f"[MONITOR] Error in monitor loop: {e}", exc_info=True)
            worker_statuses["monitor"] = "degraded"
        
        await asyncio.sleep(30)


async def metrics_archiver_loop():
    """Metrics archival loop running every hour."""
    logger.info("[MONITOR] Starting background metrics archiver loop...")
    while True:
        try:
            # Run metrics archival downsampler once every hour (3600 seconds)
            await asyncio.sleep(3600)
            logger.info("[MONITOR] Running hourly metrics archival downsampler...")
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    metric_dao = SystemMetricDAO(session)
                    deleted_rows = await metric_dao.archive_old_metrics(retention_hours=24)
                    logger.info(f"[MONITOR] Aggregated and deleted {deleted_rows} old raw metric records.")
        except asyncio.CancelledError:
            logger.info("[MONITOR] Metrics archiver task cancelled. Stopping.")
            break
        except Exception as e:
            logger.error(f"[MONITOR] Error in metrics archiver loop: {e}", exc_info=True)


def start_monitor_loop():
    """Spawns monitor loop and metrics archiver loop as async tasks."""
    global monitor_task, metrics_archiver_task
    try:
        # Get the running event loop
        loop = asyncio.get_running_loop()
        monitor_task = loop.create_task(monitor_loop())
        metrics_archiver_task = loop.create_task(metrics_archiver_loop())
        logger.info("[MONITOR] Monitor and archiver tasks spawned successfully.")
    except RuntimeError:
        # Fallback if no running loop in the thread (e.g. CLI or tests)
        logger.warning("[MONITOR] No running event loop. Running tasks requires a running loop context.")


def stop_monitor_loop():
    """Cancels the monitor and archiver tasks."""
    global monitor_task, metrics_archiver_task
    if monitor_task and not monitor_task.done():
        monitor_task.cancel()
        logger.info("[MONITOR] Stop requested for monitor loop.")
    if metrics_archiver_task and not metrics_archiver_task.done():
        metrics_archiver_task.cancel()
        logger.info("[MONITOR] Stop requested for archiver loop.")