import docker

try:
    client = docker.from_env()
except Exception as e:
    print(f"CRITICAL: Could not connect to Docker in container.py: {e}")
    client = None

def get_all_containers():
    containers = client.containers.list(all=True)

    result = []

    for container in containers:

        attrs = container.attrs

        health = (
            attrs.get("State", {})
            .get("Health", {})
            .get("Status", "no-healthcheck")
        )

        restart_count = attrs.get("RestartCount", 0)
        started_at = attrs.get("State", {}).get("StartedAt", None)

        result.append({
            "id": container.short_id,
            "name": container.name,
            "image": container.image.tags,
            "status": container.status,
            "health": health,
            "restart_count": restart_count,
            "started_at": started_at,
        })

    return result