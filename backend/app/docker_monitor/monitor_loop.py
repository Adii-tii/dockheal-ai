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
from app.docker_monitor.container import async_get_all_containers
from app.docker_monitor.metrics import async_get_all_metrics

logger = logging.getLogger(__name__)

# To control task cancellation and graceful shutdown
monitor_task = None
metrics_archiver_task = None

async def sync_containers(containers: list | None = None):
    """Sync containers from Docker to PostgreSQL.

    Args:
        containers: Pre-fetched container list from async_get_all_containers().
                    When provided the Docker SDK is not called again — the monitor
                    loop fetches once and passes the result here to avoid a second
                    blocking call per cycle.
    """
    if containers is None:
        containers = await async_get_all_containers()
    
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
    # ── Fast-path: Check in-memory cooldown first ──────────────────────────────
    last = remediation_timestamps.get(container_name)
    if last:
        age = (datetime.now(timezone.utc) - last).total_seconds()
        if age < COOLDOWN_SECONDS:
            logger.info(f"[MONITOR] Skipping {container_name}: cooldown active ({int(COOLDOWN_SECONDS - age)}s remaining)")
            return

    investigation_id = str(uuid.uuid4())

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
                    id=uuid.UUID(investigation_id),
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
            logger.warning(f"[MONITOR] DB-level lock active: Unique constraint prevented duplicate investigation for {container_name}")
            return
        except Exception as e:
            logger.error(f"[MONITOR] Failed to create investigation in DB: {e}")
            return

    # ── Build investigation packet asynchronously (runs blocking Docker SDK in worker thread) ──
    logger.info(f"[CONTEXT] Building packet for {container_name} under lock {investigation_id}")
    try:
        packet = await asyncio.to_thread(build_investigation_packet, container_name, incident)
        # Force packet investigation_id to align with DB record
        packet["investigation_id"] = investigation_id
        context_store[container_name] = packet
        score = packet["assessment"]["severity_score"]
        logger.info(f"[CONTEXT] Ready — score={score}, id={investigation_id}")
    except Exception as e:
        logger.error(f"[CONTEXT] Failed to build packet for {container_name}: {e}")
        # Build fallback packet or escalate since packet generation failed
        investigation_states[investigation_id]["state"] = "ESCALATED"
        async with AsyncSessionLocal() as session:
            try:
                async with session.begin():
                    from app.db.utils.event_logger import update_lifecycle
                    await update_lifecycle(session, uuid.UUID(investigation_id), LifecycleState.ESCALATED)
            except Exception as db_err:
                logger.error(f"[MONITOR] Failed to mark failed packet-build investigation as ESCALATED in DB: {db_err}")
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
            # 1. Fetch containers ONCE — shared by sync and incident detection.
            #    async_get_all_containers() runs the blocking Docker SDK call in
            #    a thread pool so the event loop is never frozen.
            containers = await async_get_all_containers()
            metrics = await async_get_all_metrics()

            # 2. Sync to DB (reuses the already-fetched list — no second Docker call)
            await sync_containers(containers)

            # 3. Detect incidents (reuses the same list — no third Docker call)
            incidents = detect_incidents(containers, metrics)
            for incident in incidents:
                container_name = incident["container"]
                if container_name in manually_stopped:
                    continue

                # Process incident asynchronously
                await _handle_incident(incident, container_name)

            # 4. Clean up stale or resolved simulation containers
            await cleanup_simulation_containers()

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


async def cleanup_simulation_containers():
    """Finds all simulation containers and stops/removes them if their investigation is closed or if they are stale (>15m)."""
    import docker
    from app.db.models import Investigation, LifecycleState
    from app.db.config.config import AsyncSessionLocal
    from sqlalchemy import select
    from app.runtime.state import active_incidents
    
    try:
        client = docker.from_env()
        sim_containers = await asyncio.to_thread(
            client.containers.list,
            all=True,
            filters={"label": "dockheal-simulation=true"}
        )
    except Exception as e:
        logger.error(f"[CLEANUP] Failed to list simulation containers: {e}")
        return

    if not sim_containers:
        return

    async with AsyncSessionLocal() as session:
        for c in sim_containers:
            container_name = c.name
            try:
                # Get the latest investigation for this container name
                from app.db.models.container import Container
                res_inv = await session.execute(
                    select(Investigation)
                    .join(Container, Investigation.container_id == Container.id)
                    .where(Container.container_name == container_name)
                    .order_by(Investigation.created_at.desc())
                    .limit(1)
                )
                inv = res_inv.scalar_one_or_none()
                
                is_stale = False
                state = c.attrs.get("State", {})
                started_at_str = state.get("StartedAt", "")
                age_secs = 0.0
                if started_at_str:
                    try:
                        started_at = datetime.fromisoformat(started_at_str[:26] + "Z".replace("Z", "+00:00"))
                        age_secs = (datetime.now(timezone.utc) - started_at).total_seconds()
                        if age_secs > 900.0: # 15 minutes
                            is_stale = True
                    except Exception:
                        pass
                
                is_closed = False
                if inv:
                    if inv.lifecycle_state in (
                        LifecycleState.RESOLVED,
                        LifecycleState.REJECTED,
                        LifecycleState.TIMED_OUT,
                        LifecycleState.ESCALATED
                    ):
                        is_closed = True
                else:
                    # If no investigation is found, treat it as closed/orphaned simulation
                    # ONLY if the container is not extremely fresh (race condition prevention)
                    if age_secs > 30.0:
                        is_closed = True

                if is_closed or is_stale:
                    logger.info(f"[CLEANUP] Removing stale/closed simulation container: {container_name}")
                    # Run Docker operations in a thread pool to avoid blocking the event loop
                    await asyncio.to_thread(c.stop, timeout=2)
                    await asyncio.to_thread(c.remove)
                    active_incidents.discard(container_name)
            except Exception as ce:
                logger.warning(f"[CLEANUP] Error pruning simulation container {container_name}: {ce}")


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