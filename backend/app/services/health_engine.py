from app.docker_monitor.container import get_all_containers
from app.services.remediation import restart_container
IGNORE_IMAGES = [
    "hello-world:latest"
]


def analyze_containers():

    incidents = []

    containers = get_all_containers()

    for container in containers:
        image_tags = container["image"]

        if any(img in IGNORE_IMAGES for img in image_tags):
            continue

        # Exited container
        if container["status"] == "exited":
            incidents.append({
                "type": "ContainerStopped",
                "severity": "medium",
                "container": container["name"],
                "message": f'{container["name"]} is exited'
            })

        # Unhealthy container
        if container["health"] == "unhealthy":
            incidents.append({
                "type": "UnhealthyContainer",
                "severity": "high",
                "container": container["name"],
                "message": f'{container["name"]} failed healthcheck'
            })

    return incidents