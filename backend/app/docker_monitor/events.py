import docker
import threading

client = docker.from_env()

def listen_to_events(callback):
    """
    Continuously listens to Docker events
    and sends them to the callback function.
    """

    def stream():
        for event in client.events(decode=True):
            callback(event)

    thread = threading.Thread(target=stream, daemon=True)
    thread.start()