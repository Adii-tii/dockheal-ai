import docker

try:
    client = docker.from_env()
except Exception as e:
    print(f"CRITICAL: Could not connect to Docker in container.py: {e}")
    client = None

def get_all_containers():
    if not client:
        return []
    try:
        containers = client.containers.list(all=True)
    except Exception as e:
        print(f"Error listing containers: {e}")
        return []

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
        labels = attrs.get("Config", {}).get("Labels", {}) or {}
        ports = attrs.get("NetworkSettings", {}).get("Ports", {}) or []
        if isinstance(ports, dict):
            # Convert ports dict to a list of dicts/strings to fit database JSONB list schema
            ports = [{"host_port": v, "container_port": k} for k, v in ports.items() if v]

        runtime_metadata = {
            "cgroups": attrs.get("HostConfig", {}).get("Cgroup", ""),
            "network_mode": attrs.get("HostConfig", {}).get("NetworkMode", ""),
        }

        result.append({
            "id": container.id,  # 64-character full ID
            "name": container.name,
            "image": container.image.tags,
            "status": container.status,
            "health": health,
            "restart_count": restart_count,
            "started_at": started_at,
            "labels": labels,
            "ports": ports,
            "runtime_metadata": runtime_metadata,
        })

    return result