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

def start_container(container_name):
    try:
        container = client.containers.get(container_name)
        container.start()
        return {
            "success": True,
            "message": f"{container_name} started successfully"
        }
    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }

def delete_container(container_name):
    try:
        container = client.containers.get(container_name)
        container.remove(force=True)
        return {
            "success": True,
            "message": f"{container_name} deleted successfully"
        }
    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }

def stop_container(container_name):
    try:
        container = client.containers.get(container_name)
        container.stop()
        return {
            "success": True,
            "message": f"{container_name} stopped successfully"
        }
    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }