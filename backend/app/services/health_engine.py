from app.docker_monitor.container import get_all_containers

from app.runtime.state import manually_stopped
from app.runtime.state import active_incidents


IGNORE_IMAGES = [
    "hello-world:latest"
]


def detect_incidents():

    incidents = []

    containers = get_all_containers()

    for container in containers:

        name = container["name"]
        image_tags = container["image"]

        print(f"[CHECKING] {name}")

        # Ignore containers like hello-world
        if any(img in IGNORE_IMAGES for img in image_tags):

            print(f"[SKIP] ignored image -> {name}")

            continue

        # Ignore manually stopped containers
        if name in manually_stopped:

            print(f"[SKIP] manually stopped -> {name}")

            continue


        # Exited container detection
        if container["status"] == "exited":

            print(f"[DETECTED] exited container -> {name}")

            active_incidents.add(name)

            incidents.append({
                "type": "ContainerStopped",
                "severity": "medium",
                "container": name,
                "message": f"{name} exited unexpectedly"
            })

        # Unhealthy container detection
        if container["health"] == "unhealthy":

            print(f"[DETECTED] unhealthy container -> {name}")

            active_incidents.add(name)

            incidents.append({
                "type": "UnhealthyContainer",
                "severity": "high",
                "container": name,
                "message": f"{name} failed healthcheck"
            })

    return incidents