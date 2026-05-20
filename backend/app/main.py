from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import asyncio
import json
from contextlib import asynccontextmanager

from app.web_sockets.manager import manager
from app.docker_monitor.events import listen_to_events
from app.docker_monitor.container import get_all_containers
from app.services.health_engine import detect_incidents
from app.services.remediation import restart_container
from app.runtime.state import (
    manually_stopped, operator_lock, context_store,
    investigation_states, audit_log,
)
from app.docker_monitor.monitor_loop import start_monitor_loop
from app.docker_monitor.metrics import get_all_metrics, get_container_metrics
from app.context.aggregator import build_investigation_packet
from app.ai.investigator import investigate


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.ai.tools.alert_tools import set_ws_manager
    set_ws_manager(manager)
    loop = asyncio.get_running_loop()
    listen_to_events(lambda e: handle_docker_event(e, loop))
    start_monitor_loop()
    yield


app = FastAPI(lifespan=lifespan, title="DockHeal API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.get("/containers")
async def containers():
    return get_all_containers()


@app.get("/incidents")
async def incidents():
    return detect_incidents()


@app.post("/restart/{container_name}")
async def restart(container_name: str):
    return restart_container(container_name)


# ── Metrics ────────────────────────────────────────────────────────────────────

@app.get("/containers/metrics")
async def all_metrics():
    return get_all_metrics()


@app.get("/containers/{container_name}/metrics")
async def single_metrics(container_name: str):
    data = get_container_metrics(container_name)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Container '{container_name}' not found")
    return data


# ── Operational Context ────────────────────────────────────────────────────────

@app.get("/context")
async def all_context():
    return list(context_store.values())


@app.get("/context/{container_name}")
async def get_context(container_name: str):
    if container_name in context_store:
        return context_store[container_name]
    packet = build_investigation_packet(
        container_name,
        incident={"type": "ManualInspection", "severity": "low", "message": "On-demand context request"},
    )
    if packet["container_state"].get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"Container '{container_name}' not found")
    context_store[container_name] = packet
    return packet


@app.post("/context/{container_name}/build")
async def force_build_context(container_name: str):
    packet = build_investigation_packet(
        container_name,
        incident={"type": "ManualInspection", "severity": "low", "message": "Force-rebuilt by operator"},
    )
    if packet["container_state"].get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"Container '{container_name}' not found")
    context_store[container_name] = packet
    return packet


# ── AI Investigation ───────────────────────────────────────────────────────────

@app.post("/investigate/{container_name}")
async def trigger_investigation(container_name: str):
    if container_name in context_store:
        packet = context_store[container_name]
    else:
        packet = build_investigation_packet(
            container_name,
            incident={"type": "ManualInvestigation", "severity": "medium", "message": "Operator-triggered"},
        )
        if packet["container_state"].get("status") == "not_found":
            raise HTTPException(status_code=404, detail=f"Container '{container_name}' not found")
        context_store[container_name] = packet

    async def broadcast(msg: dict):
        await manager.broadcast(msg)

    result = await investigate(packet, broadcast)
    return result


@app.get("/investigate/{container_name}/stream")
async def stream_investigation(container_name: str):
    if container_name not in context_store:
        packet = build_investigation_packet(
            container_name,
            incident={"type": "ManualInvestigation", "severity": "medium", "message": "SSE-triggered"},
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


@app.get("/investigations")
async def get_investigations():
    return investigation_states


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
