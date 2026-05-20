"""
Dependency mapper — discovers related containers by:

1. Shared Docker networks  (most reliable)
2. docker-compose project label (com.docker.compose.project)
3. Explicit "depends_on" encoded in compose labels
   (com.docker.compose.depends_on)

Returns a dependency context block describing sibling containers
so the AI understands blast-radius and can reason about cascading failures.
"""

import docker

try:
    client = docker.from_env()
except Exception as e:
    print(f"[DEPENDENCY_MAPPER] Docker unavailable: {e}")
    client = None


def _get_network_peers(target_container, all_containers) -> list[str]:
    """Containers sharing at least one non-default network with target."""
    target_nets = set(
        target_container.attrs.get("NetworkSettings", {}).get("Networks", {}).keys()
    ) - {"bridge", "host", "none"}

    if not target_nets:
        return []

    peers = []
    for c in all_containers:
        if c.id == target_container.id:
            continue
        c_nets = set(
            c.attrs.get("NetworkSettings", {}).get("Networks", {}).keys()
        ) - {"bridge", "host", "none"}
        if target_nets & c_nets:
            peers.append(c.name)
    return peers


def _get_compose_siblings(target_container, all_containers) -> list[str]:
    """Containers in the same docker-compose project."""
    labels = target_container.labels or {}
    project = labels.get("com.docker.compose.project")
    if not project:
        return []

    return [
        c.name for c in all_containers
        if c.id != target_container.id
        and (c.labels or {}).get("com.docker.compose.project") == project
    ]


def _summarise_peer(c) -> dict:
    """Lightweight summary of a peer container for the context packet."""
    attrs  = c.attrs
    health = (
        attrs.get("State", {})
             .get("Health", {})
             .get("Status", "no-healthcheck")
    )
    return {
        "name":          c.name,
        "status":        c.status,
        "health":        health,
        "image":         c.image.tags[0] if c.image.tags else "unknown",
        "restart_count": attrs.get("RestartCount", 0),
    }


def collect_dependencies(container_name: str) -> dict:
    """
    Returns:
        compose_project    – project name if compose-managed, else None
        depends_on         – explicit depends_on labels (list of names)
        network_peers      – containers on the same user-defined networks
        compose_siblings   – all containers in the same compose project
        unhealthy_peers    – subset of peers that are unhealthy/exited
        peer_summaries     – list of lightweight dicts for all related containers
    """
    if not client:
        return {
            "compose_project": None,
            "depends_on": [],
            "network_peers": [],
            "compose_siblings": [],
            "unhealthy_peers": [],
            "peer_summaries": [],
        }

    try:
        target = client.containers.get(container_name)
    except docker.errors.NotFound:
        return {
            "compose_project": None,
            "depends_on": [],
            "network_peers": [],
            "compose_siblings": [],
            "unhealthy_peers": [],
            "peer_summaries": [],
        }

    all_containers = client.containers.list(all=True)

    labels         = target.labels or {}
    compose_project = labels.get("com.docker.compose.project")
    depends_on_raw  = labels.get("com.docker.compose.depends_on", "")
    depends_on      = [d.strip() for d in depends_on_raw.split(",") if d.strip()]

    network_peers    = _get_network_peers(target, all_containers)
    compose_siblings = _get_compose_siblings(target, all_containers)

    # Union of all related container names
    related_names = set(network_peers) | set(compose_siblings) | set(depends_on)

    peer_summaries = []
    unhealthy_peers = []

    for c in all_containers:
        if c.name in related_names:
            summary = _summarise_peer(c)
            peer_summaries.append(summary)
            if summary["status"] in ("exited", "dead") or summary["health"] == "unhealthy":
                unhealthy_peers.append(c.name)

    return {
        "compose_project":  compose_project,
        "depends_on":       depends_on,
        "network_peers":    network_peers,
        "compose_siblings": compose_siblings,
        "unhealthy_peers":  unhealthy_peers,
        "peer_summaries":   peer_summaries,
    }
