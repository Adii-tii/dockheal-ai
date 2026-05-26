from app.docker_monitor.container import get_all_containers

from app.runtime.state import manually_stopped
from app.runtime.state import active_incidents


IGNORE_IMAGES = [
    "hello-world:latest"
]


def detect_incidents(containers: list | None = None, metrics: list | None = None):
    """
    Detect incidents from the current container state.

    Args:
        containers: Optional pre-fetched container list from async_get_all_containers().
                    When provided the Docker SDK is NOT called again, eliminating a
                    duplicate blocking call in the monitor loop.
                    When None (e.g. called directly from /incidents), falls back to
                    get_all_containers() — callers should wrap with asyncio.to_thread.
    """
    incidents = []

    if containers is None:
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
                "severity": "P2",
                "container": name,
                "message": f"{name} exited unexpectedly"
            })

        # Unhealthy container detection
        if container["health"] == "unhealthy":

            print(f"[DETECTED] unhealthy container -> {name}")

            active_incidents.add(name)

            incidents.append({
                "type": "UnhealthyContainer",
                "severity": "P1",
                "container": name,
                "message": f"{name} failed healthcheck"
            })

        # CPU spike detection
        if metrics:
            metric_entry = next((m for m in metrics if m["name"] == name), None)
            if metric_entry and metric_entry.get("cpu_percent", 0.0) >= 85.0:
                print(f"[DETECTED] CPU spike -> {name}")
                active_incidents.add(name)
                incidents.append({
                    "type": "CpuSpike",
                    "severity": "P2",
                    "container": name,
                    "message": f"{name} CPU utilization spiked to {metric_entry['cpu_percent']}%"
                })

    return incidents