import docker
import threading
from app.runtime.state import manually_stopped
from app.runtime.event_buffer import push as push_event

try:
    client = docker.from_env()
except Exception as e:
    print(f"CRITICAL: Could not connect to Docker: {e}")
    client = None

event_handler_callback = None

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

    # User intentionally stopped container
    if action in ["stop", "kill"]:
        manually_stopped.add(container_name)
        print(f"[STATE] manually stopped -> {container_name}")

    # Container started again
    if action == "start":
        manually_stopped.discard(container_name)
        print(f"[STATE] removed manual stop -> {container_name}")

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