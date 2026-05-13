from fastapi import FastAPI, WebSocket
from app.web_sockets.manager import ConnectionManager
from app.docker_monitor.events import listen_to_events
from app.docker_monitor.container import get_all_containers
from app.services.health_engine import analyze_containers
from app.services.remediation import restart_container
import asyncio

app = FastAPI()

manager = ConnectionManager()

# Stores FastAPI's main async event loop
main_loop = None


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)

    try:
        while True:
            await websocket.receive_text()

    except:
        manager.disconnect(websocket)


def handle_docker_event(event):
    """
    Called whenever Docker emits an event.
    """

    asyncio.run_coroutine_threadsafe(
        manager.broadcast({
            "type": event.get("Type"),
            "action": event.get("Action"),
            "actor": event.get("Actor", {})
        }),
        main_loop
    )


@app.on_event("startup")
async def startup_event():
    global main_loop

    # Save FastAPI's running event loop
    main_loop = asyncio.get_running_loop()

    # Start Docker event listener
    listen_to_events(handle_docker_event)


@app.get("/")
async def root():
    return {"message": "DockHand backend running"}

@app.get("/containers")
async def containers():
    return get_all_containers()

@app.get("/incidents")
async def incidents():
    return analyze_containers()

@app.post("/restart/{container_name}")
async def restart(container_name: str):
    return restart_container(container_name)