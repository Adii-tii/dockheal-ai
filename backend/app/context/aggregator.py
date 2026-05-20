"""
Operational Context Aggregation Layer
======================================
The single source of truth before any AI reasoning step.

build_investigation_packet(container_name, incident)
    → OperationalContext dict

The packet is structured so that:
  1. An LLM can receive it directly as a JSON block in its system prompt.
  2. All signals are pre-classified — the AI reasons, not filters.
  3. A severity_score and recommended_action are pre-computed so the AI
     starts from a grounded baseline, not a blank slate.

Packet schema
─────────────
{
  "schema_version":    str,
  "generated_at":      ISO-8601 UTC,
  "investigation_id":  str (uuid4),

  "incident": {
    "type":       str,
    "severity":   "P0" | "P1" | "P2" | "P3",
    "container":  str,
    "message":    str,
    "triggered_at": ISO-8601 UTC,
  },

  "container_state": {
    "id", "name", "image", "status", "health",
    "restart_count", "started_at", "exit_code",
    "oom_killed", "labels",
  },

  "metrics_snapshot": {
    "cpu_percent", "mem_usage_mb", "mem_limit_mb",
    "mem_percent", "uptime_seconds",
    "thresholds_breached": [...],
  },

  "recent_events": {
    "timeline", "critical_count", "oom_detected",
    "frequent_dies", "die_count",
  },

  "logs": {
    "raw_tail", "signals": {errors, warnings, stack_traces, crash_signals},
  },

  "dependency_context": {
    "compose_project", "depends_on", "network_peers",
    "compose_siblings", "unhealthy_peers", "peer_summaries",
  },

  "assessment": {
    "severity_score":      int   0-100,
    "likely_causes":       [str],
    "recommended_action":  str,
    "escalate":            bool,
  },
}
"""

import uuid
from datetime import datetime, timezone

from app.docker_monitor.metrics import get_container_metrics
from app.context.log_collector import collect_logs
from app.context.event_collector import collect_events
from app.context.dependency_mapper import collect_dependencies
from app.runtime.policy_registry import POLICIES

import docker

SCHEMA_VERSION = "1.0"

try:
    _docker_client = docker.from_env()
except Exception:
    _docker_client = None


# ── Threshold constants ────────────────────────────────────────────────────────
CPU_HIGH      = 85.0   # %
MEM_HIGH      = 80.0   # %
RESTART_WARN  = 3
RESTART_CRIT  = 10


def _get_container_state(container_name: str) -> dict:
    """Pull full container state from Docker attrs."""
    if not _docker_client:
        return {}
    try:
        c     = _docker_client.containers.get(container_name)
        attrs = c.attrs
        state = attrs.get("State", {})
        return {
            "id":            c.short_id,
            "name":          c.name,
            "image":         c.image.tags[0] if c.image.tags else "unknown",
            "status":        c.status,
            "health":        state.get("Health", {}).get("Status", "no-healthcheck"),
            "restart_count": attrs.get("RestartCount", 0),
            "started_at":    state.get("StartedAt"),
            "finished_at":   state.get("FinishedAt"),
            "exit_code":     state.get("ExitCode"),
            "oom_killed":    state.get("OOMKilled", False),
            "labels":        c.labels or {},
            "env_vars":      _safe_env(attrs),
        }
    except docker.errors.NotFound:
        return {"name": container_name, "status": "not_found"}
    except Exception as e:
        return {"name": container_name, "error": str(e)}


def _safe_env(attrs: dict) -> list[str]:
    """Return env vars with secret values redacted."""
    raw = attrs.get("Config", {}).get("Env") or []
    redacted = []
    _SECRET_KEYS = {"password", "secret", "token", "key", "auth", "credential"}
    for var in raw:
        k, _, v = var.partition("=")
        if any(s in k.lower() for s in _SECRET_KEYS):
            redacted.append(f"{k}=<REDACTED>")
        else:
            redacted.append(var)
    return redacted


def _assess(
    state: dict,
    metrics: dict,
    events: dict,
    logs: dict,
    deps: dict,
) -> dict:
    """
    Derive a severity_score (0-100), likely_causes list, and
    recommended_action from the aggregated signals.
    This is a deterministic heuristic — the AI refines it further.
    """
    score = 0
    causes = []

    restart_count = metrics.get("restart_count", 0) or state.get("restart_count", 0)
    cpu           = metrics.get("cpu_percent", 0)
    mem           = metrics.get("mem_percent", 0)
    oom           = state.get("oom_killed") or events.get("oom_detected", False)
    exit_code     = state.get("exit_code")
    status        = state.get("status", "")
    health        = state.get("health", "")

    # ── OOM kill ──────────────────────────────────────────────────────────────
    if oom:
        score += 40
        causes.append("OOM kill detected — container exhausted memory limit")

    # ── Crash loop ────────────────────────────────────────────────────────────
    if events.get("frequent_dies", False):
        score += 30
        causes.append(f"Crash loop: {events.get('die_count', 0)} die events in observation window")
    elif restart_count >= RESTART_CRIT:
        score += 25
        causes.append(f"High restart count ({restart_count}) suggests persistent failure")
    elif restart_count >= RESTART_WARN:
        score += 10
        causes.append(f"Elevated restart count ({restart_count})")

    # ── Non-zero exit ─────────────────────────────────────────────────────────
    if exit_code and str(exit_code) not in ("0", "None"):
        score += 15
        causes.append(f"Non-zero exit code: {exit_code}")

    # ── Resource pressure ─────────────────────────────────────────────────────
    if cpu >= CPU_HIGH:
        score += 10
        causes.append(f"CPU at {cpu}% (threshold {CPU_HIGH}%)")
    if mem >= MEM_HIGH:
        score += 15
        causes.append(f"Memory at {mem}% of limit")

    # ── Health / status ───────────────────────────────────────────────────────
    if health == "unhealthy":
        score += 20
        causes.append("Container healthcheck is failing")
    if status == "exited":
        score += 10
        causes.append("Container is in exited state")

    # ── Log signals ───────────────────────────────────────────────────────────
    signals     = logs.get("signals", {})
    crash_sigs  = signals.get("crash_signals", [])
    stack_traces = signals.get("stack_traces", [])
    error_lines  = signals.get("errors", [])

    if crash_sigs:
        score += 15
        causes.append(f"Crash signal in logs: {crash_sigs[0][:120]}")
    if stack_traces:
        score += 10
        causes.append("Stack trace detected in logs")
    elif error_lines:
        score += 5
        causes.append(f"Error lines in logs: {len(error_lines)} occurrences")

    # ── Cascading failure risk ────────────────────────────────────────────────
    unhealthy_peers = deps.get("unhealthy_peers", [])
    if unhealthy_peers:
        score += 10
        causes.append(f"Peer containers also degraded: {', '.join(unhealthy_peers[:3])}")

    score = min(score, 100)

    # ── Deterministic severity floors (cannot be lowered by AI) ─────────────────
    # Apply POLICIES floors AFTER point-based scoring.
    # These ensure OOM / crash loops / protected services always read as high.
    score = POLICIES.apply_deterministic_severity(
        base_score         = score,
        oom                = bool(oom),
        frequent_dies      = bool(events.get("frequent_dies", False)),
        high_restart_count = restart_count >= RESTART_CRIT,
    )

    # ── Recommended action ────────────────────────────────────────────────────
    if oom:
        action = "Increase container memory limit or investigate memory leak"
    elif events.get("frequent_dies") or restart_count >= RESTART_CRIT:
        action = "Investigate application crash loop — review logs for root cause before restarting"
    elif health == "unhealthy":
        action = "Diagnose healthcheck failure — check endpoint, DB connectivity, or disk"
    elif cpu >= CPU_HIGH:
        action = "Investigate CPU spike — check for runaway process or insufficient limits"
    elif mem >= MEM_HIGH:
        action = "Investigate memory growth — potential leak or undersized limit"
    elif status == "exited":
        action = "Container exited — review exit code and logs for cause"
    else:
        action = "Restart container and monitor — no critical signal detected"

    return {
        "severity_score":     score,
        "likely_causes":      causes if causes else ["No strong signal detected — requires manual inspection"],
        "recommended_action": action,
        "escalate":           score >= 60,
    }


def build_investigation_packet(container_name: str, incident: dict) -> dict:
    """
    Main entry point for the Operational Context Aggregation Layer.

    Collects all signals in parallel where possible, assembles and returns
    a fully structured investigation packet.

    Args:
        container_name: Name of the affected container.
        incident:       The raw incident dict from health_engine.detect_incidents().

    Returns:
        A structured OperationalContext dict ready to be passed to an AI model.
    """
    now = datetime.now(timezone.utc).isoformat()

    # ── Collect all signals ───────────────────────────────────────────────────
    # Note: kept sequential for now because docker.stats() is blocking anyway.
    # A future version can parallelise log + event + dep collection.

    state   = _get_container_state(container_name)
    metrics = get_container_metrics(container_name) or {}
    events  = collect_events(container_name)
    logs    = collect_logs(container_name)
    deps    = collect_dependencies(container_name)

    # ── Threshold breach summary ──────────────────────────────────────────────
    thresholds_breached = []
    if metrics.get("cpu_percent", 0) >= CPU_HIGH:
        thresholds_breached.append(f"cpu > {CPU_HIGH}%")
    if metrics.get("mem_percent", 0) >= MEM_HIGH:
        thresholds_breached.append(f"mem > {MEM_HIGH}%")
    if (metrics.get("restart_count") or state.get("restart_count", 0)) >= RESTART_WARN:
        thresholds_breached.append(f"restart_count >= {RESTART_WARN}")

    metrics_snapshot = {
        "cpu_percent":         metrics.get("cpu_percent", 0.0),
        "mem_usage_mb":        metrics.get("mem_usage_mb", 0.0),
        "mem_limit_mb":        metrics.get("mem_limit_mb", 0.0),
        "mem_percent":         metrics.get("mem_percent", 0.0),
        "uptime_seconds":      metrics.get("uptime_seconds", 0),
        "thresholds_breached": thresholds_breached,
    }

    # ── Assessment ────────────────────────────────────────────────────────────
    assessment = _assess(state, metrics, events, logs, deps)

    # ── Assemble packet ───────────────────────────────────────────────────────
    return {
        "schema_version":   SCHEMA_VERSION,
        "generated_at":     now,
        "investigation_id": str(uuid.uuid4()),

        "incident": {
            "type":         incident.get("type", "Unknown"),
            "severity":     incident.get("severity", "P2"),
            "container":    container_name,
            "message":      incident.get("message", ""),
            "triggered_at": now,
        },

        "container_state":    state,
        "metrics_snapshot":   metrics_snapshot,
        "recent_events":      events,
        "logs":               logs,
        "dependency_context": deps,
        "assessment":         assessment,
    }
