import docker

client = docker.from_env()

def restart_container(container_name):

    try:
        container = client.containers.get(container_name)

        container.restart()

        return {
            "success": True,
            "message": f"{container_name} restarted successfully"
        }

    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }