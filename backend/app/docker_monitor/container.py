import docker

client = docker.from_env()

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

        result.append({
            "id": container.short_id,
            "name": container.name,
            "image": container.image.tags,
            "status": container.status,
            "health": health
        })

    return result