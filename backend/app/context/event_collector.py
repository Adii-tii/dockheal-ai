"""
Docker event collector.

Reads recent events for a container from the in-memory event buffer
(populated by the running event listener thread) and structures them
into a timeline suitable for AI reasoning.

Each event entry produced:
    action      – e.g. "start", "die", "oom", "health_status: unhealthy"
    timestamp   – ISO string from Docker or buffer receipt time
    exit_code   – parsed from Attributes if present (die events)
    oom_killed  – True if the event was an OOM kill
"""

from app.runtime.event_buffer import get_for_container

# Actions that strongly indicate a problem
_CRITICAL_ACTIONS = {
    "die", "oom", "kill", "out-of-memory",
    "health_status: unhealthy", "destroy",
}


def collect_events(container_name: str, limit: int = 30) -> dict:
    """
    Returns:
        timeline       – list of structured event dicts, newest first
        critical_count – number of critical-action events in window
        oom_detected   – True if any OOM event found
        frequent_dies  – True if >=3 "die" events found (crash-loop signal)
    """
    raw_events = get_for_container(container_name, limit=limit)

    timeline = []
    die_count = 0
    oom_detected = False

    for event in raw_events:
        action     = event.get("Action", "unknown")
        attributes = event.get("Actor", {}).get("Attributes", {})
        ts         = event.get("time")          # unix timestamp from Docker
        received   = event.get("_received_at")  # ISO string we added

        # Prefer Docker's own timestamp if available
        iso_time = received
        if ts:
            try:
                from datetime import datetime, timezone
                iso_time = datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
            except Exception:
                pass

        exit_code = attributes.get("exitCode")
        oom_flag  = attributes.get("oomKilled", "false").lower() == "true"

        if action == "die":
            die_count += 1
        if oom_flag or action == "oom":
            oom_detected = True

        timeline.append({
            "action":     action,
            "timestamp":  iso_time,
            "exit_code":  exit_code,
            "oom_killed": oom_flag,
            "is_critical": action in _CRITICAL_ACTIONS,
            "attributes": {
                k: v for k, v in attributes.items()
                if k not in ("name", "image")   # already known from container state
            },
        })

    return {
        "timeline":       timeline,
        "critical_count": sum(1 for e in timeline if e["is_critical"]),
        "oom_detected":   oom_detected,
        "frequent_dies":  die_count >= 3,
        "die_count":      die_count,
    }
