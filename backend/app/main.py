from fastapi import FastAPI, WebSocket, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager

from app.web_sockets.manager import manager
from app.docker_monitor.events import listen_to_events
from app.docker_monitor.container import get_all_containers, async_get_all_containers
from app.services.health_engine import detect_incidents
from app.services.remediation import restart_container, start_container, delete_container, stop_container
from app.runtime.state import (
    manually_stopped, operator_lock, context_store,
    investigation_states, audit_log,
)
from app.docker_monitor.monitor_loop import start_monitor_loop
from app.docker_monitor.metrics import get_all_metrics, get_container_metrics, async_get_all_metrics
from app.context.aggregator import build_investigation_packet
from app.ai.investigator import investigate

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.ai.tools.alert_tools import set_ws_manager
    set_ws_manager(manager)
    loop = asyncio.get_running_loop()
    listen_to_events(lambda e: handle_docker_event(e, loop))

    # ── Seed manually_stopped from DB on startup ───────────────────────────────
    # Prevents auto-investigations firing for containers the user intentionally
    # stopped in a previous session (the in-memory set is blank after a restart).
    try:
        from app.db.config.config import AsyncSessionLocal
        from app.db.models.container import Container
        from sqlalchemy import select
        from app.runtime.state import manually_stopped
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(Container.container_name).where(Container.is_manually_stopped.is_(True))
            )
            for (name,) in res.all():
                manually_stopped.add(name)
        logger.info(f"[STARTUP] Seeded manually_stopped with {len(manually_stopped)} container(s): {manually_stopped}")
    except Exception as e:
        logger.warning(f"[STARTUP] Could not seed manually_stopped from DB: {e}")

    # ── Database Migration and Startup Cleanup ─────────────────────────────────
    try:
        from sqlalchemy import text
        from app.db.config.config import engine
        async with engine.connect() as conn:
            await conn.execution_options(isolation_level="AUTOCOMMIT")
            await conn.execute(text("ALTER TYPE lifecycle_state_enum ADD VALUE IF NOT EXISTS 'PAUSED'"))
        logger.info("[STARTUP] Altered type lifecycle_state_enum successfully (added 'PAUSED' if not exists).")
    except Exception as e:
        logger.warning(f"[STARTUP] Could not execute ALTER TYPE lifecycle_state_enum: {e}")

    try:
        from app.db.config.config import AsyncSessionLocal
        from app.db.models import Investigation, LifecycleState
        from app.db.utils.event_logger import update_lifecycle, log_timeline_event
        from app.db.dao.investigation_dao import ACTIVE_STATES
        from sqlalchemy import select

        async with AsyncSessionLocal() as session:
            async with session.begin():
                states_to_pause = [s for s in ACTIVE_STATES if s != LifecycleState.PAUSED]
                res = await session.execute(
                    select(Investigation).where(Investigation.lifecycle_state.in_(states_to_pause))
                )
                leftover_invs = res.scalars().all()
                for inv in leftover_invs:
                    await update_lifecycle(session, inv.id, LifecycleState.PAUSED)
                    await log_timeline_event(
                        session=session,
                        investigation_id=inv.id,
                        event_type="INVESTIGATION_PAUSED",
                        title="Investigation Paused",
                        description="Investigation was automatically paused on application startup.",
                        source_type="SYSTEM",
                    )
        logger.info(f"[STARTUP] Paused {len(leftover_invs)} leftover active investigations.")
    except Exception as e:
        logger.warning(f"[STARTUP] Could not pause leftover active investigations on startup: {e}")

    # Start monitor worker (monitor loop + metrics archiver loop)
    from app.docker_monitor.monitor_loop import start_monitor_loop, stop_monitor_loop
    start_monitor_loop()
    
    # Start notification worker
    from app.services.notification_worker import start_notification_worker, stop_notification_worker
    start_notification_worker()
    
    # Set API worker status to healthy
    from app.runtime.state import worker_statuses
    worker_statuses["api"] = "healthy"
    
    yield
    
    # Graceful shutdown / cleanup
    stop_monitor_loop()
    stop_notification_worker()
    
    # Cancel all active investigation tasks
    from app.runtime.state import active_tasks
    tasks_to_cancel = []
    for task_id, task in list(active_tasks.items()):
        if not task.done():
            task.cancel()
            tasks_to_cancel.append(task)
            
    if tasks_to_cancel:
        logger.info(f"[SHUTDOWN] Awaiting cancellation of {len(tasks_to_cancel)} active tasks...")
        await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
        logger.info("[SHUTDOWN] All active tasks cancelled and finalized.")
            
    # Set statuses to offline / stopped on shutdown
    for key in worker_statuses:
        worker_statuses[key] = "offline"


app = FastAPI(lifespan=lifespan, title="DockHeal API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── API Call Logging Middleware ────────────────────────────────────────────────
# Exclude: websocket upgrades, health checks, and the logs endpoint itself
_LOG_EXCLUDE_PREFIXES = ("/ws", "/health", "/api-call-logs")


@app.middleware("http")
async def log_api_calls(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    duration_ms = (time.monotonic() - start) * 1000

    path = request.url.path
    if not any(path.startswith(p) for p in _LOG_EXCLUDE_PREFIXES):
        # Fire-and-forget — never block the response
        asyncio.create_task(_write_call_log(request.method, path, response.status_code, duration_ms))

    return response


async def _write_call_log(method: str, path: str, status_code: int, duration_ms: float):
    """Background coroutine — writes one API call log row to the DB."""
    try:
        from app.db.config.config import AsyncSessionLocal
        from app.db.models.api_call_log import ApiCallLog
        from datetime import datetime, timezone
        async with AsyncSessionLocal() as session:
            async with session.begin():
                session.add(ApiCallLog(
                    method=method,
                    path=path,
                    status_code=status_code,
                    duration_ms=round(duration_ms, 2),
                    created_at=datetime.now(timezone.utc),
                ))
    except Exception:
        pass  # Never let logging errors surface


# ── WebSocket ──────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        manager.disconnect(websocket)


def handle_docker_event(event, loop):
    action         = event.get("Action")
    attributes     = event.get("Actor", {}).get("Attributes", {})
    container_name = attributes.get("name")
    if loop and loop.is_running():
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({
                "type":      "DOCKER_EVENT",
                "action":    action,
                "container": container_name,
            }),
            loop,
        )


# ── Core ───────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"message": "DockHeal API v2.0", "status": "ok"}


@app.get("/health/api")
async def health_api():
    from app.runtime.state import worker_statuses
    status = worker_statuses.get("api", "unknown")
    if status != "healthy":
        raise HTTPException(status_code=503, detail={"status": status})
    return {"status": status}


@app.get("/health/monitor")
async def health_monitor():
    from app.runtime.state import worker_statuses
    status = worker_statuses.get("monitor", "unknown")
    if status != "healthy":
        raise HTTPException(status_code=503, detail={"status": status})
    return {"status": status}


@app.get("/health/ai-worker")
async def health_ai_worker():
    from app.runtime.state import worker_statuses
    status = worker_statuses.get("ai_worker", "unknown")
    if status != "healthy":
        raise HTTPException(status_code=503, detail={"status": status})
    return {"status": status}


@app.get("/health/notifications")
async def health_notifications():
    from app.runtime.state import worker_statuses
    status = worker_statuses.get("notifications", "unknown")
    if status != "healthy":
        raise HTTPException(status_code=503, detail={"status": status})
    return {"status": status}


@app.get("/containers")
async def containers():
    return await async_get_all_containers()


@app.get("/incidents")
async def incidents():
    containers = await async_get_all_containers()
    metrics = await async_get_all_metrics()
    return detect_incidents(containers, metrics)


@app.post("/restart/{container_name}")
async def restart(container_name: str):
    return restart_container(container_name)


@app.post("/start/{container_name}")
async def start(container_name: str):
    return start_container(container_name)


@app.post("/delete/{container_name}")
async def delete(container_name: str):
    return delete_container(container_name)


@app.post("/stop/{container_name}")
async def stop(container_name: str):
    return stop_container(container_name)


# ── Metrics ────────────────────────────────────────────────────────────────────

@app.get("/containers/metrics")
async def all_metrics():
    return await async_get_all_metrics()


@app.get("/containers/{container_name}/logs")
async def container_logs(container_name: str, tail: int = 100):
    from app.ai.tools.container_tools import fetch_logs_tool
    # fetch_logs_tool calls blocking Docker SDK calls — run in thread pool.
    res = await asyncio.to_thread(
        fetch_logs_tool,
        container_name=container_name,
        tail=tail,
        actor="operator"
    )
    if not res.get("success"):
        output = res.get("output", "")
        if "not found" in output.lower():
            raise HTTPException(status_code=404, detail=output)
        raise HTTPException(status_code=500, detail=output)
    return {"logs": res.get("output")}


# ── Operational Context ────────────────────────────────────────────────────────

@app.get("/context")
async def all_context():
    return list(context_store.values())


@app.get("/context/{container_name}")
async def get_context(container_name: str):
    if container_name in context_store:
        return context_store[container_name]
    packet = await asyncio.to_thread(
        build_investigation_packet,
        container_name,
        {"type": "ManualInspection", "severity": "P3", "message": "On-demand context request"},
    )
    if packet["container_state"].get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"Container '{container_name}' not found")
    context_store[container_name] = packet
    return packet


@app.post("/context/{container_name}/build")
async def force_build_context(container_name: str):
    packet = await asyncio.to_thread(
        build_investigation_packet,
        container_name,
        {"type": "ManualInspection", "severity": "P3", "message": "Force-rebuilt by operator"},
    )
    if packet["container_state"].get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"Container '{container_name}' not found")
    context_store[container_name] = packet
    return packet


# ── AI Investigation ───────────────────────────────────────────────────────────

@app.post("/investigate/{container_name}")
async def trigger_investigation(container_name: str, request: Request):
    # Parse optional JSON payload
    operator_logs = None
    try:
        body = await request.json()
        operator_logs = body.get("operator_logs")
    except Exception:
        pass

    from app.runtime.state import investigation_states, active_tasks, context_store
    from app.db.config.config import AsyncSessionLocal
    from app.db.models.container import Container
    from app.db.models import Investigation, LifecycleState, SeverityLevel
    from app.db.utils.event_logger import update_lifecycle, log_timeline_event
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    import uuid
    from datetime import datetime, timezone
    
    # Single session: read container + active investigation, then write in same connection.
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(Container).where(Container.container_name == container_name)
        )
        container = res.scalar_one_or_none()
        if not container:
            raise HTTPException(status_code=404, detail=f"Container '{container_name}' not found")
        
        # Check for active investigation for this container in the DB
        # Active is not in: RESOLVED, REJECTED, TIMED_OUT, ESCALATED.
        res_inv = await session.execute(
            select(Investigation)
            .options(selectinload(Investigation.timeline_events))
            .where(
                Investigation.container_id == container.id,
                Investigation.lifecycle_state.notin_([
                    LifecycleState.RESOLVED,
                    LifecycleState.REJECTED,
                    LifecycleState.TIMED_OUT,
                    LifecycleState.ESCALATED,
                ])
            )
            .order_by(Investigation.created_at.desc())
            .limit(1)
        )
        db_inv = res_inv.scalar_one_or_none()

        if db_inv:
            inv_id_str = str(db_inv.id)
            # If it is running (not PAUSED), handle restart or return already_running
            if db_inv.lifecycle_state != LifecycleState.PAUSED:
                if operator_logs:
                    if inv_id_str in active_tasks:
                        cancellation_reasons[inv_id_str] = "restarted"
                        active_tasks[inv_id_str].cancel()
                        import asyncio
                        try:
                            await active_tasks[inv_id_str]
                        except asyncio.CancelledError:
                            pass
                        active_tasks.pop(inv_id_str, None)
                else:
                    return {"status": "already_running", "investigation_id": inv_id_str}
            
            # It is PAUSED, so resume it! Update memory state first.
            entry = investigation_states.get(inv_id_str, {})
            entry.update({
                "state": "INVESTIGATING",
                "container": container_name,
                "updated_at": datetime.now(timezone.utc).isoformat()
            })
            investigation_states[inv_id_str] = entry

            # Write resume state — same session, same connection
            async with session.begin():
                await update_lifecycle(session, db_inv.id, LifecycleState.INVESTIGATING)
                await log_timeline_event(
                    session,
                    db_inv.id,
                    event_type="INVESTIGATION_RESUMED",
                    title="Investigation Resumed",
                    description="The investigation has been resumed by the operator." + (f" Custom logs attached: '{operator_logs[:80]}...'" if operator_logs else ""),
                    source_type="SYSTEM",
                )

            # Build resume packet with previous thoughts and timeline history
            timeline_logs = []
            for ev in sorted(db_inv.timeline_events, key=lambda e: e.sequence_number or 0):
                timeline_logs.append(f"[{ev.created_at.isoformat()}] {ev.title}: {ev.description or ''}")
            
            previous_trace = {
                "thoughts": db_inv.thoughts or "",
                "timeline": "\n".join(timeline_logs)
            }

            packet = await asyncio.to_thread(
                build_investigation_packet,
                container_name,
                {"type": "ManualInvestigation", "severity": "P2", "message": "Operator-triggered resume" + (f" (attached custom logs)" if operator_logs else "")},
            )
            packet["investigation_id"] = inv_id_str
            packet["previous_investigation_trace"] = previous_trace
            if operator_logs:
                if "logs" not in packet:
                    packet["logs"] = {}
                packet["logs"]["operator_provided_logs"] = operator_logs
            context_store[container_name] = packet
            status_msg = "resumed"
        else:
            # Create a new investigation
            inv_id = uuid.uuid4()
            inv_id_str = str(inv_id)

            # Update memory state first
            investigation_states[inv_id_str] = {
                "state": "INVESTIGATING",
                "container": container_name,
                "startedAt": datetime.now(timezone.utc).isoformat(),
                "thoughts": "",
                "timeline": []
            }

            # Create record in DB — same session, same connection
            async with session.begin():
                new_inv = Investigation(
                    id=inv_id,
                    container_id=container.id,
                    title=f"Incident in container {container_name}",
                    incident_summary="Operator triggered investigation manually." + (f" Custom logs attached: '{operator_logs[:60]}...'" if operator_logs else ""),
                    severity_level=SeverityLevel.P2,
                    lifecycle_state=LifecycleState.DETECTED,
                    started_at=datetime.now(timezone.utc),
                    created_by="operator",
                )
                session.add(new_inv)
                await session.flush()
                
                # Transition to INVESTIGATING
                await update_lifecycle(session, inv_id, LifecycleState.INVESTIGATING)
                await log_timeline_event(
                    session,
                    inv_id,
                    event_type="INVESTIGATION_STARTED",
                    title="Investigation Started",
                    description=f"AI Agent initialized for {container_name}." + (f" Custom logs attached: '{operator_logs[:80]}...'" if operator_logs else ""),
                    source_type="SYSTEM",
                )

            # Build operational context packet
            packet = await asyncio.to_thread(
                build_investigation_packet,
                container_name,
                {"type": "ManualInvestigation", "severity": "P2", "message": "Operator-triggered" + (f" (attached custom logs)" if operator_logs else "")},
            )
            packet["investigation_id"] = inv_id_str
            if operator_logs:
                if "logs" not in packet:
                    packet["logs"] = {}
                packet["logs"]["operator_provided_logs"] = operator_logs
            context_store[container_name] = packet
            status_msg = "started"


    # Spawn the AI investigator task in the background
    async def broadcast(msg: dict):
        await manager.broadcast(msg)

    task = asyncio.create_task(investigate(packet, broadcast))
    active_tasks[inv_id_str] = task

    return {"status": status_msg, "investigation_id": inv_id_str}


@app.post("/investigate/{container_name}/pause")
async def pause_investigation(container_name: str):
    from app.runtime.state import investigation_states, active_tasks, cancellation_reasons
    from app.db.config.config import AsyncSessionLocal
    from app.db.models.container import Container
    from app.db.models import Investigation, LifecycleState
    from app.db.utils.event_logger import update_lifecycle, log_timeline_event
    from sqlalchemy import select
    from datetime import datetime, timezone
    
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(Container).where(Container.container_name == container_name)
        )
        container = res.scalar_one_or_none()
        if not container:
            raise HTTPException(status_code=404, detail=f"Container '{container_name}' not found")
        
        res_inv = await session.execute(
            select(Investigation)
            .where(
                Investigation.container_id == container.id,
                Investigation.lifecycle_state.notin_([
                    LifecycleState.RESOLVED,
                    LifecycleState.REJECTED,
                    LifecycleState.TIMED_OUT,
                    LifecycleState.ESCALATED,
                ])
            )
            .order_by(Investigation.created_at.desc())
            .limit(1)
        )
        db_inv = res_inv.scalar_one_or_none()

    if not db_inv:
        return {"status": "no_active_investigation"}

    inv_id_str = str(db_inv.id)
    if db_inv.lifecycle_state == LifecycleState.PAUSED:
        return {"status": "already_paused", "investigation_id": inv_id_str}

    # If there is an active running task, cancel it and set reason to "paused"
    if inv_id_str in active_tasks:
        cancellation_reasons[inv_id_str] = "paused"
        active_tasks[inv_id_str].cancel()
        return {"status": "pausing", "investigation_id": inv_id_str}
    else:
        # No running task found, transition state to PAUSED directly in DB & memory
        entry = investigation_states.get(inv_id_str, {})
        entry.update({
            "state": "PAUSED",
            "container": container_name,
            "updated_at": datetime.now(timezone.utc).isoformat()
        })
        investigation_states[inv_id_str] = entry

        async with AsyncSessionLocal() as session:
            async with session.begin():
                await update_lifecycle(session, db_inv.id, LifecycleState.PAUSED)
                await log_timeline_event(
                    session,
                    db_inv.id,
                    event_type="INVESTIGATION_PAUSED",
                    title="Investigation Paused",
                    description="Investigation was paused by the operator.",
                    source_type="SYSTEM",
                )
        return {"status": "paused", "investigation_id": inv_id_str}


@app.post("/investigate/{container_name}/stop")
async def stop_investigation(container_name: str):
    from app.runtime.state import investigation_states, active_tasks, cancellation_reasons
    from app.db.config.config import AsyncSessionLocal
    from app.db.models.container import Container
    from app.db.models import Investigation, LifecycleState
    from app.db.utils.event_logger import update_lifecycle, log_timeline_event
    from sqlalchemy import select
    from datetime import datetime, timezone
    
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(Container).where(Container.container_name == container_name)
        )
        container = res.scalar_one_or_none()
        if not container:
            raise HTTPException(status_code=404, detail=f"Container '{container_name}' not found")
        
        res_inv = await session.execute(
            select(Investigation)
            .where(
                Investigation.container_id == container.id,
                Investigation.lifecycle_state.notin_([
                    LifecycleState.RESOLVED,
                    LifecycleState.REJECTED,
                    LifecycleState.TIMED_OUT,
                    LifecycleState.ESCALATED,
                ])
            )
            .order_by(Investigation.created_at.desc())
            .limit(1)
        )
        db_inv = res_inv.scalar_one_or_none()

    if not db_inv:
        return {"status": "no_active_investigation"}

    inv_id_str = str(db_inv.id)

    # If there is an active running task, cancel it and set reason to "stopped"
    if inv_id_str in active_tasks:
        cancellation_reasons[inv_id_str] = "stopped"
        active_tasks[inv_id_str].cancel()
        return {"status": "stopping", "investigation_id": inv_id_str}
    else:
        # No running task found, transition state to REJECTED directly in DB & memory
        entry = investigation_states.get(inv_id_str, {})
        entry.update({
            "state": "REJECTED",
            "container": container_name,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "final_result": {
                "investigation_id": inv_id_str,
                "container": container_name,
                "root_cause": "Investigation stopped.",
                "confidence": 0.0,
                "evidence_citations": [],
                "proposed_actions": [],
                "requires_human": False,
            }
        })
        investigation_states[inv_id_str] = entry

        async with AsyncSessionLocal() as session:
            async with session.begin():
                await update_lifecycle(session, db_inv.id, LifecycleState.REJECTED)
                await log_timeline_event(
                    session,
                    db_inv.id,
                    event_type="INVESTIGATION_STOPPED",
                    title="Investigation Stopped",
                    description="Investigation was stopped/aborted by the operator.",
                    source_type="SYSTEM",
                )
        return {"status": "stopped", "investigation_id": inv_id_str}


@app.post("/investigations/{investigation_id}/approve")
async def approve_investigation(investigation_id: str, user: str = "Operator"):
    from app.runtime.state import approval_events, approval_results, investigation_states
    from datetime import datetime, timezone
    
    logger.info(f"[APPROVAL] Attempting to approve: {investigation_id}. Active approval events: {list(approval_events.keys())}")
    
    target_key = None
    for k in approval_events.keys():
        if str(k) == str(investigation_id):
            target_key = k
            break

    if target_key is None:
        logger.warning(f"[APPROVAL] Mismatch: {investigation_id} not found in active approval events: {list(approval_events.keys())}")
        raise HTTPException(status_code=404, detail="Investigation not awaiting approval")
        
    approval_results[target_key] = {
        "status": "approved",
        "user": user,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    approval_events[target_key].set()
    logger.info(f"[APPROVAL] Approved: {investigation_id}")
    return {"status": "approved"}


@app.post("/investigations/{investigation_id}/reject")
async def reject_investigation(investigation_id: str, user: str = "Operator"):
    from app.runtime.state import approval_events, approval_results, investigation_states
    from datetime import datetime, timezone
    
    logger.info(f"[APPROVAL] Attempting to reject: {investigation_id}. Active approval events: {list(approval_events.keys())}")
    
    target_key = None
    for k in approval_events.keys():
        if str(k) == str(investigation_id):
            target_key = k
            break

    if target_key is None:
        logger.warning(f"[APPROVAL] Mismatch: {investigation_id} not found in active approval events: {list(approval_events.keys())}")
        raise HTTPException(status_code=404, detail="Investigation not awaiting approval")
        
    approval_results[target_key] = {
        "status": "rejected",
        "user": user,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    approval_events[target_key].set()
    logger.info(f"[APPROVAL] Rejected: {investigation_id}")
    return {"status": "rejected"}


@app.get("/investigate/{container_name}/stream")
async def stream_investigation(container_name: str):
    if container_name not in context_store:
        packet = await asyncio.to_thread(
            build_investigation_packet,
            container_name,
            {"type": "ManualInvestigation", "severity": "P2", "message": "SSE-triggered"},
        )
        if packet["container_state"].get("status") == "not_found":
            raise HTTPException(status_code=404, detail=f"Container '{container_name}' not found")
        context_store[container_name] = packet
    else:
        packet = context_store[container_name]

    async def event_generator():
        chunks = []

        async def collect_broadcast(msg: dict):
            chunks.append(msg)

        result = await investigate(packet, collect_broadcast)
        for chunk in chunks:
            yield f"data: {json.dumps(chunk)}\n\n"
        yield f"data: {json.dumps({'type': 'DONE', 'result': result})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── Operator Controls ──────────────────────────────────────────────────────────

@app.post("/lock/{container_name}")
async def lock_container(container_name: str):
    operator_lock.add(container_name)
    return {"locked": container_name, "message": "All autonomous actions blocked."}


@app.post("/unlock/{container_name}")
async def unlock_container(container_name: str):
    operator_lock.discard(container_name)
    return {"unlocked": container_name, "message": "Autonomous actions re-enabled."}


# ── Audit + State ──────────────────────────────────────────────────────────────

@app.get("/audit")
async def get_audit_log(limit: int = 50):
    return list(reversed(audit_log))[:min(limit, 200)]


# ── Developer: API Call Logs ────────────────────────────────────────────────────

@app.get("/api-call-logs")
async def get_api_call_logs(limit: int = 200):
    """
    Developer endpoint — returns total API call count and the most recent log entries.
    Use this to monitor call volume and avoid hitting LLM rate limits.
    """
    from app.db.config.config import AsyncSessionLocal
    from app.db.models.api_call_log import ApiCallLog
    from sqlalchemy import select, func

    async with AsyncSessionLocal() as session:
        # Total count
        count_res = await session.execute(select(func.count()).select_from(ApiCallLog))
        total = count_res.scalar_one()

        # Most recent N logs
        logs_res = await session.execute(
            select(ApiCallLog).order_by(ApiCallLog.created_at.desc()).limit(limit)
        )
        logs = logs_res.scalars().all()

    return {
        "total": total,
        "logs": [
            {
                "id": str(log.id),
                "method": log.method,
                "path": log.path,
                "status_code": log.status_code,
                "duration_ms": log.duration_ms,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ],
    }


@app.get("/investigations")
async def get_investigations():
    from app.db.config.config import AsyncSessionLocal
    from app.db.models import Investigation, LifecycleState
    from sqlalchemy import select, text
    from sqlalchemy.orm import joinedload, selectinload
    from datetime import datetime, timezone
    from app.runtime.state import investigation_states

    response_states = {}
    _TERMINAL = {LifecycleState.RESOLVED, LifecycleState.REJECTED, LifecycleState.TIMED_OUT, LifecycleState.ESCALATED}

    db_invs = []
    try:
        async with AsyncSessionLocal() as session:
            # Hard DB-level timeout — never let a slow query hang the server
            await session.execute(text("SET LOCAL statement_timeout = '8000'"))

            res = await session.execute(
                select(Investigation).options(
                    joinedload(Investigation.container),
                    selectinload(Investigation.rca_reports),
                    selectinload(Investigation.timeline_events),
                ).order_by(Investigation.created_at.desc()).limit(50)
            )
            db_invs = res.scalars().unique().all()
    except Exception as e:
        logger.warning(f"get_investigations DB query failed: {e}")
        db_invs = []

    for inv in db_invs:
        inv_id_str = str(inv.id)
        
        # Format timeline
        timeline_list = []
        for ev in sorted(inv.timeline_events, key=lambda e: e.sequence_number or 0):
            timeline_list.append({
                "timestamp": ev.created_at.isoformat(),
                "type": ev.event_type,
                "title": ev.title,
                "description": ev.description or "",
                "source": ev.source_type.value if hasattr(ev.source_type, "value") else str(ev.source_type),
                "severity": ev.severity.value if (ev.severity and hasattr(ev.severity, "value")) else (str(ev.severity) if ev.severity else "INFO"),
            })
            
        # Format RCA Report
        rca_report_dict = None
        if inv.rca_reports:
            latest_rca = sorted(inv.rca_reports, key=lambda r: r.rca_version, reverse=True)[0]
            
            evidence_found = latest_rca.evidence_found
            if isinstance(evidence_found, list):
                evidence_found = ", ".join(str(e) for e in evidence_found) if evidence_found else ""
            
            contributing_factors = latest_rca.contributing_factors
            if isinstance(contributing_factors, list):
                contributing_factors = ", ".join(str(c) for c in contributing_factors) if contributing_factors else ""

            rca_report_dict = {
                "rca_version": latest_rca.rca_version,
                "incident_summary": latest_rca.incident_summary or "",
                "impact_assessment": latest_rca.impact_assessment or "",
                "what_failed": latest_rca.what_failed or "",
                "why_it_happened": latest_rca.why_it_happened or "",
                "action_proposed": latest_rca.action_proposed or "",
                "recovery_status": latest_rca.recovery_status or "",
                "long_term_prevention": latest_rca.long_term_prevention or "",
                "confidence_score": latest_rca.confidence_score or 0.0,
                "ai_reasoning_summary": latest_rca.ai_reasoning_summary or "",
                "evidence_found": evidence_found,
                "contributing_factors": contributing_factors,
            }
        elif inv.root_cause or inv.ai_reasoning_summary:
            rca_report_dict = {
                "rca_version": 1,
                "incident_summary": inv.incident_summary or "",
                "what_failed": inv.root_cause or "",
                "why_it_happened": inv.root_cause or "",
                "long_term_prevention": "",
                "confidence_score": inv.confidence or 0.0,
                "ai_reasoning_summary": inv.ai_reasoning_summary or "",
                "evidence_found": "",
                "contributing_factors": "",
            }

        # Format result
        result_dict = None
        if rca_report_dict or inv.decision_trace:
            proposed_actions = []
            reason_for_restart = ""
            if isinstance(inv.decision_trace, dict):
                proposed_actions = inv.decision_trace.get("proposed_actions", [])
                reason_for_restart = inv.decision_trace.get("reason_for_restart", "")
            
            result_dict = {
                "rca_report": rca_report_dict,
                "proposed_actions": proposed_actions,
                "root_cause": inv.root_cause or "",
                "requires_human": True,
                "reason_for_restart": reason_for_restart,
            }

        # Merge with in-memory state if exists (to preserve live thoughts, etc.)
        in_mem = investigation_states.get(inv_id_str, {})
        
        response_states[inv_id_str] = {
            "investigation_id": inv_id_str,
            "state": inv.lifecycle_state.value if hasattr(inv.lifecycle_state, "value") else str(inv.lifecycle_state),
            "container": inv.container.container_name if inv.container else (in_mem.get("container") or "unknown"),
            "severity": inv.severity_level.value if hasattr(inv.severity_level, "value") else str(inv.severity_level),
            "startedAt": inv.started_at.isoformat() if inv.started_at else (inv.created_at.isoformat() if inv.created_at else None),
            "result": result_dict or in_mem.get("final_result") or in_mem.get("result"),
            "timeline": timeline_list or in_mem.get("timeline") or [],
            "thoughts": inv.thoughts or in_mem.get("thoughts") or "",
        }

    # Add any transient in-memory investigations that aren't in DB yet
    for inv_id_str, in_mem in investigation_states.items():
        if inv_id_str not in response_states:
            response_states[inv_id_str] = {
                "investigation_id": inv_id_str,
                "state": in_mem.get("state", "DETECTED"),
                "container": in_mem.get("container", "unknown"),
                "severity": in_mem.get("severity", "P2"),
                "startedAt": in_mem.get("startedAt") or in_mem.get("updated_at") or datetime.now(timezone.utc).isoformat(),
                "result": in_mem.get("final_result") or in_mem.get("result"),
                "timeline": in_mem.get("timeline") or [],
                "thoughts": in_mem.get("thoughts") or "",
            }

    return response_states


@app.post("/investigations/stop-all")
async def stop_all_investigations():
    from app.runtime.state import active_tasks, investigation_states
    from app.db.config.config import AsyncSessionLocal
    from app.db.models import Investigation, LifecycleState
    from app.db.utils.event_logger import update_lifecycle, log_timeline_event
    from sqlalchemy import select
    import uuid

    # Cancel in-memory running investigator tasks
    cancelled_count = len(active_tasks)
    for inv_id, task in list(active_tasks.items()):
        if not task.done():
            task.cancel()

    # Query all active investigations from DB and update their state to REJECTED (Aborted)
    async with AsyncSessionLocal() as session:
        async with session.begin():
            res = await session.execute(
                select(Investigation).where(
                    Investigation.lifecycle_state.notin_([
                        LifecycleState.RESOLVED,
                        LifecycleState.REJECTED,
                        LifecycleState.TIMED_OUT,
                        LifecycleState.ESCALATED
                    ])
                )
            )
            active_invs = res.scalars().all()
            for inv in active_invs:
                inv_id_str = str(inv.id)
                if inv_id_str in investigation_states:
                    investigation_states[inv_id_str]["state"] = "REJECTED"
                else:
                    investigation_states[inv_id_str] = {
                        "state": "REJECTED",
                        "container": "unknown"
                    }

                await update_lifecycle(session, inv.id, LifecycleState.REJECTED)
                await log_timeline_event(
                    session=session,
                    investigation_id=inv.id,
                    event_type="INVESTIGATION_ABORTED",
                    title="Investigation Aborted",
                    description="This investigation was manually aborted/stopped by the operator.",
                    source_type="SYSTEM",
                )

    return {"status": "ok", "cancelled_count": cancelled_count, "db_updated_count": len(active_invs)}


@app.get("/investigations/{investigation_id}")
async def get_investigation(investigation_id: str):
    state = investigation_states.get(investigation_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Investigation '{investigation_id}' not found")
    return state


# ── Policies ───────────────────────────────────────────────────────────────────

@app.get("/policies")
async def get_policies():
    from app.runtime.policy_registry import POLICIES
    from app.runtime.state import operator_lock, manually_stopped
    
    data = POLICIES.as_dict()
    data.update({
        "operator_locked":     list(operator_lock),
        "manually_stopped":    list(manually_stopped),
    })
    return data


@app.put("/policies")
async def update_policies(payload: dict):
    from app.runtime.policy_registry import POLICIES
    from app.runtime.state import operator_lock, manually_stopped
    
    # Filter out metadata fields not stored in POLICIES
    policy_payload = {k: v for k, v in payload.items() if k not in ("operator_locked", "manually_stopped")}
    POLICIES.update(**policy_payload)
    
    data = POLICIES.as_dict()
    data.update({
        "operator_locked":     list(operator_lock),
        "manually_stopped":    list(manually_stopped),
    })
    return data


# ── Sandbox Tools Controls ────────────────────────────────────────────────────

@app.get("/sandbox/tools")
async def get_sandbox_tools():
    from app.ai.tools.decorator import TOOL_METADATA
    from app.runtime.policy_registry import POLICIES
    
    return [
        {
            "name": meta["name"],
            "description": meta["description"],
            "allowed_params": meta["allowed_params"],
            "risk_level": meta["risk_level"],
            "phase": meta["phase"],
            "blocked": meta["name"] in POLICIES.blocked_tools,
        }
        for meta in TOOL_METADATA.values()
    ]


@app.post("/sandbox/tools/{tool_name}/block")
async def block_sandbox_tool(tool_name: str):
    from app.runtime.policy_registry import POLICIES
    if tool_name not in POLICIES.blocked_tools:
        POLICIES.blocked_tools.append(tool_name)
    return {"status": "ok", "blocked_tools": POLICIES.blocked_tools}


@app.post("/sandbox/tools/{tool_name}/unblock")
async def unblock_sandbox_tool(tool_name: str):
    from app.runtime.policy_registry import POLICIES
    if tool_name in POLICIES.blocked_tools:
        POLICIES.blocked_tools.remove(tool_name)
    return {"status": "ok", "blocked_tools": POLICIES.blocked_tools}


def run_simulation_container(case_id: str, container_name: str):
    import docker
    client = docker.from_env()

    # 1. Cleanup old container if it exists
    try:
        old = client.containers.get(container_name)
        old.stop(timeout=2)
        old.remove()
    except docker.errors.NotFound:
        pass
    except Exception:
        pass

    # 2. Setup strict hardware capped settings
    image = "python:3.11-alpine"
    command = ""
    healthcheck = None
    restart_policy = None
    mem_limit = "10m"
    memswap_limit = "10m"
    nano_cpus = 100000000 # 0.1 CPU core

    if case_id == "oom_killed":
        command = (
            "python -c \""
            "import time, sys\n"
            "print('webapp: starting server...', flush=True)\n"
            "print('webapp: allocate memory pool', flush=True)\n"
            "print('FATAL: OutOfMemoryError: Java heap space', flush=True)\n"
            "l = []\n"
            "while True:\n"
            "    l.append('x' * 512 * 1024)\n"
            "    time.sleep(0.1)"
            "\""
        )
        mem_limit = "10m"
        memswap_limit = "10m"
        nano_cpus = 100000000

    elif case_id == "crash_loop":
        command = (
            "python -c \""
            "import sys\n"
            "print('db: starting PostgreSQL...', flush=True)\n"
            "print('FATAL:  lock file \"postmaster.pid\" already exists', flush=True)\n"
            "print('HINT:  Is another postmaster (PID 48) running in data directory \"/var/lib/postgresql/data\"?', flush=True)\n"
            "sys.exit(1)"
            "\""
        )
        restart_policy = {"Name": "always"}
        mem_limit = "10m"
        memswap_limit = "10m"
        nano_cpus = 50000000 # 0.05 CPU core

    elif case_id == "rate_limit":
        command = (
            "python -c \""
            "print('gateway: rate limiter active', flush=True)\n"
            "print('WARNING: rate limit breached for client 192.168.1.100 (1500 req/sec > limit 1000)', flush=True)\n"
            "while True:\n"
            "    pass"
            "\""
        )
        mem_limit = "10m"
        memswap_limit = "10m"
        nano_cpus = 100000000

    elif case_id == "unhealthy_nginx":
        command = (
            "sh -c '"
            "echo \"nginx: starting worker processes...\"; "
            "sleep 8; "
            "echo \"[error] connect() failed (111: Connection refused) while connecting to upstream\"; "
            "touch /tmp/unhealthy; "
            "while true; do sleep 3600; done"
            "'"
        )
        healthcheck = {
            "Test": ["CMD-SHELL", "test ! -f /tmp/unhealthy"],
            "Interval": 3000000000, # 3s
            "Timeout": 1000000000,  # 1s
            "Retries": 1,
            "StartPeriod": 1000000000 # 1s
        }
        mem_limit = "15m"
        memswap_limit = "15m"
        nano_cpus = 50000000

    elif case_id == "disk_full":
        command = (
            "python -c \""
            "import time\n"
            "print('logger: flushing write buffer', flush=True)\n"
            "print('ERROR: write failed: No space left on device (ENOSPC)', flush=True)\n"
            "while True:\n"
            "    time.sleep(3600)"
            "\""
        )
        mem_limit = "10m"
        memswap_limit = "10m"
        nano_cpus = 50000000 # 0.05 CPU core

    else:
        raise ValueError(f"Unknown case_id: {case_id}")

    # 3. Spin up the container
    c = client.containers.run(
        image=image,
        command=command,
        name=container_name,
        detach=True,
        mem_limit=mem_limit,
        memswap_limit=memswap_limit,
        nano_cpus=nano_cpus,
        pids_limit=10,
        network_mode="none", # isolated networking
        restart_policy=restart_policy,
        healthcheck=healthcheck,
        labels={"dockheal-simulation": "true"},
        auto_remove=False,
    )
    return c.id, c.image.tags[0] if c.image.tags else image


async def run_simulation_investigation_loop(container_name: str, case_id: str, inv_id_str: str, broadcast_fn):
    import docker
    client = docker.from_env()

    # Wait for the container to reach the desired failure state (up to 15 seconds)
    for _ in range(15):
        await asyncio.sleep(1.0)
        try:
            c = client.containers.get(container_name)
            c.reload()
            
            is_failed = False
            if case_id in ("oom_killed", "crash_loop"):
                if c.status == "exited":
                    is_failed = True
            elif case_id == "unhealthy_nginx":
                health = c.attrs.get("State", {}).get("Health", {}).get("Status", "")
                if health == "unhealthy":
                    is_failed = True
            elif case_id == "rate_limit":
                from app.docker_monitor.metrics import get_container_metrics
                metrics = get_container_metrics(container_name)
                if metrics and metrics.get("cpu_percent", 0.0) >= 85.0:
                    is_failed = True
            elif case_id == "disk_full":
                is_failed = True
            
            if is_failed:
                break
        except Exception:
            pass

    severity = "P1" if case_id in ("oom_killed", "crash_loop", "unhealthy_nginx") else "P2"
    if case_id in ("oom_killed", "crash_loop"):
        inc_type = "ContainerStopped"
        msg = f"{container_name} exited unexpectedly"
    elif case_id == "unhealthy_nginx":
        inc_type = "UnhealthyContainer"
        msg = f"{container_name} failed healthcheck"
    elif case_id == "disk_full":
        inc_type = "DiskFull"
        msg = f"{container_name} log volume space exhausted (ENOSPC)"
    else:
        inc_type = "CpuSpike"
        msg = f"{container_name} CPU utilization spiked"

    incident = {
        "type": inc_type,
        "severity": severity,
        "container": container_name,
        "message": msg
    }

    try:
        # Sync containers and metrics to state so context builder has accurate metrics
        from app.docker_monitor.container import async_get_all_containers
        from app.docker_monitor.monitor_loop import sync_containers
        containers = await async_get_all_containers()
        await sync_containers(containers)

        packet = await asyncio.to_thread(build_investigation_packet, container_name, incident)
        packet["investigation_id"] = inv_id_str
        context_store[container_name] = packet

        await investigate(packet, broadcast_fn)
    except Exception as e:
        logger.error(f"Error in simulation investigation loop: {e}", exc_info=True)


@app.post("/simulate/trigger")
async def simulate_trigger(payload: dict):
    case_id = payload.get("case_id")
    container_name = f"dockheal-sim-{case_id}"

    from app.runtime.state import investigation_states, active_tasks, context_store, cancellation_reasons
    from app.db.config.config import AsyncSessionLocal
    from app.db.models.container import Container
    from app.db.models import Investigation, LifecycleState, SeverityLevel
    from app.db.utils.event_logger import update_lifecycle, log_timeline_event
    from sqlalchemy import select
    import uuid
    from datetime import datetime, timezone
    import asyncio

    # 1. Start the actual container
    try:
        container_id, image_name = await asyncio.to_thread(run_simulation_container, case_id, container_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start simulation container: {str(e)}")

    # 2. Ensure Container exists in DB
    async with AsyncSessionLocal() as session:
        async with session.begin():
            res = await session.execute(
                select(Container).where(Container.container_name == container_name)
            )
            container = res.scalar_one_or_none()
            if not container:
                container = Container(
                    container_name=container_name,
                    runtime_id=container_id,
                    image_name=image_name,
                    status="exited" if case_id in ("oom_killed", "crash_loop") else "running",
                    is_manually_stopped=False,
                )
                session.add(container)
                await session.flush()
            else:
                container.status = "exited" if case_id in ("oom_killed", "crash_loop") else "running"
                container.runtime_id = container_id
                container.image_name = image_name
            container_id_db = container.id

    # 3. Cancel any running active task and transition their DB status to REJECTED
    tasks_to_await = []
    async with AsyncSessionLocal() as session:
        async with session.begin():
            res_inv = await session.execute(
                select(Investigation)
                .where(
                    Investigation.container_id == container_id_db,
                    Investigation.lifecycle_state.notin_([
                        LifecycleState.RESOLVED,
                        LifecycleState.REJECTED,
                        LifecycleState.TIMED_OUT,
                        LifecycleState.ESCALATED,
                    ])
                )
            )
            old_invs = res_inv.scalars().all()
            for old in old_invs:
                old_id = str(old.id)
                if old_id in active_tasks:
                    cancellation_reasons[old_id] = "restarted"
                    active_tasks[old_id].cancel()
                    tasks_to_await.append(active_tasks[old_id])
                    active_tasks.pop(old_id, None)

                # Update in-memory state
                if old_id in investigation_states:
                    investigation_states[old_id]["state"] = "REJECTED"

                # Update database state to REJECTED to resolve UniqueViolationError
                await update_lifecycle(session, old.id, LifecycleState.REJECTED)
                await log_timeline_event(
                    session,
                    old.id,
                    event_type="INVESTIGATION_ABORTED",
                    title="Investigation Aborted",
                    description="This investigation was aborted because a new simulation was triggered.",
                    source_type="SYSTEM",
                )

    # Await cancelled tasks outside of transaction to avoid blocking connections
    for task in tasks_to_await:
        try:
            await task
        except asyncio.CancelledError:
            pass

    # 4. Create a new Investigation record
    inv_id = uuid.uuid4()
    inv_id_str = str(inv_id)

    investigation_states[inv_id_str] = {
        "state": "INVESTIGATING",
        "container": container_name,
        "startedAt": datetime.now(timezone.utc).isoformat(),
        "thoughts": "",
        "timeline": []
    }

    async with AsyncSessionLocal() as session:
        async with session.begin():
            new_inv = Investigation(
                id=inv_id,
                container_id=container_id_db,
                title=f"Simulated Incident: {case_id.replace('_', ' ').upper()}",
                incident_summary=f"Simulated test case triggered: {case_id}",
                severity_level=SeverityLevel.P1 if case_id in ("oom_killed", "crash_loop", "unhealthy_nginx") else SeverityLevel.P2,
                lifecycle_state=LifecycleState.DETECTED,
                started_at=datetime.now(timezone.utc),
                created_by="simulation",
            )
            session.add(new_inv)
            await session.flush()
            await update_lifecycle(session, inv_id, LifecycleState.INVESTIGATING)
            await log_timeline_event(
                session,
                inv_id,
                event_type="INVESTIGATION_STARTED",
                title="Simulation Initiated",
                description=f"AI Agent starting simulation on real container '{container_name}'.",
                source_type="SYSTEM",
            )

    # 5. Spawn background AI investigator loop
    async def broadcast(msg: dict):
        await manager.broadcast(msg)

    task = asyncio.create_task(run_simulation_investigation_loop(container_name, case_id, inv_id_str, broadcast))
    active_tasks[inv_id_str] = task

    return {"status": "started", "investigation_id": inv_id_str}
