import asyncio
import logging
import docker
import threading
from app.runtime.state import manually_stopped
from app.runtime.event_buffer import push as push_event

logger = logging.getLogger(__name__)

try:
    client = docker.from_env()
except Exception as e:
    print(f"CRITICAL: Could not connect to Docker: {e}")
    client = None

event_handler_callback = None


async def _persist_manually_stopped(container_name: str, stopped: bool) -> None:
    """Persist is_manually_stopped flag to DB so it survives server restarts."""
    try:
        from app.db.config.config import AsyncSessionLocal
        from app.db.dao.container_dao import ContainerDAO
        async with AsyncSessionLocal() as session:
            async with session.begin():
                dao = ContainerDAO(session)
                container = await dao.get_by_name(container_name)
                if container:
                    await dao.update_instance(container, is_manually_stopped=stopped)
    except Exception as e:
        logger.warning(f"[EVENTS] Failed to persist is_manually_stopped for {container_name}: {e}")


def handle_docker_event(event):
    action = event.get("Action")
    actor = event.get("Actor", {})
    attributes = actor.get("Attributes", {})
    container_name = attributes.get("name")

    if not container_name:
        return

    # Always record in the rolling buffer first
    push_event(event)

    print(f"[DOCKER EVENT] {action} -> {container_name}")

    # User intentionally stopped container — persist to DB so flag survives restart
    if action in ["stop", "kill"]:
        manually_stopped.add(container_name)
        print(f"[STATE] manually stopped -> {container_name}")
        # Fire-and-forget DB write
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_persist_manually_stopped(container_name, True))
        except RuntimeError:
            pass  # No running loop in event thread — monitor loop will sync on next cycle

    # Container started again — clear the flag in DB too
    if action == "start":
        manually_stopped.discard(container_name)
        print(f"[STATE] removed manual stop -> {container_name}")
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_persist_manually_stopped(container_name, False))
        except RuntimeError:
            pass


def listen_to_events(callback=None):
    """
    Continuously listens to Docker events.
    """
    global event_handler_callback
    event_handler_callback = callback

    def stream():
        for event in client.events(decode=True):
            # Internal processing for state management
            handle_docker_event(event)

            # Optional external callback for UI/broadcast
            if event_handler_callback:
                event_handler_callback(event)

    thread = threading.Thread(target=stream, daemon=True)
    thread.start()