"""
Recovery Engine — deterministic restart with health verification.

attempt_deterministic_restart(container_name, incident, investigation_id)
    → RecoveryResult

Steps:
  1. Pre-flight: check policies (cooldown, retry limit, operator lock, manual stop).
  2. If pre-flight passes: docker restart.
  3. Poll container health for up to POLICIES.recovery_timeout_secs.
  4. Record remediation timestamp + retry count.
  5. Return RecoveryResult (always populated — never raises).
"""

import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

import docker

from app.runtime.policy_registry import POLICIES
from app.runtime.state import (
    manually_stopped,
    operator_lock,
    remediation_timestamps,
    remediation_retry_counts,
    append_audit,
)

try:
    _client = docker.from_env()
except Exception:
    _client = None


# ── Result schema ──────────────────────────────────────────────────────────────

@dataclass
class RecoveryResult:
    container_name:    str
    investigation_id:  str
    attempted:         bool          = False
    success:           bool          = False
    reason_skipped:    Optional[str] = None   # why restart was not attempted
    restart_reason:    str           = ""     # incident-derived (exited, unhealthy, etc.)
    pre_restart_status: str          = ""     # container status before restart
    post_health:       str           = ""     # status/health after poll
    elapsed_seconds:   float         = 0.0
    verified_healthy:  bool          = False
    error:             Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


# ── Pre-flight checks ──────────────────────────────────────────────────────────

def _preflight(container_name: str) -> Optional[str]:
    """
    Returns a skip reason string if restart should NOT proceed, else None.
    Checks in priority order matching guardrails.py.
    """
    if container_name in manually_stopped:
        return "manually_stopped"

    if container_name in operator_lock:
        return "operator_locked"

    last = remediation_timestamps.get(container_name)
    if last:
        age = (datetime.now(timezone.utc) - last).total_seconds()
        if age < POLICIES.cooldown_seconds:
            remaining = int(POLICIES.cooldown_seconds - age)
            return f"cooldown:{remaining}s_remaining"

    count = remediation_retry_counts.get(container_name, 0)
    if count >= POLICIES.max_retries:
        return f"retry_limit:{count}/{POLICIES.max_retries}"

    return None


# ── Health poll ────────────────────────────────────────────────────────────────

def poll_health(container_name: str) -> tuple[str, bool]:
    """
    Poll container status/health until healthy or timeout.

    Returns (final_status_string, verified_healthy).
    """
    if not _client:
        return "docker_unavailable", False

    deadline = time.monotonic() + POLICIES.recovery_timeout_secs
    interval = POLICIES.recovery_poll_interval_secs

    while time.monotonic() < deadline:
        try:
            c = _client.containers.get(container_name)
            c.reload()
            status = c.status
            health = c.attrs.get("State", {}).get("Health", {}).get("Status", "no-healthcheck")

            if status == "running":
                if health in ("healthy", "no-healthcheck"):
                    return f"{status}/{health}", True
                # health is 'starting' or 'unhealthy' — keep polling
            elif status in ("exited", "dead", "removing"):
                return f"{status}", False

        except docker.errors.NotFound:
            return "not_found", False
        except Exception as e:
            return f"poll_error:{e}", False

        time.sleep(interval)

    # Timeout — read last known state
    try:
        c = _client.containers.get(container_name)
        c.reload()
        status = c.status
        health = c.attrs.get("State", {}).get("Health", {}).get("Status", "no-healthcheck")
        return f"{status}/{health}_timeout", status == "running"
    except Exception:
        return "timeout_unknown", False


# ── Main entry point ───────────────────────────────────────────────────────────

def attempt_deterministic_restart(
    container_name:   str,
    incident:         dict,
    investigation_id: str,
) -> RecoveryResult:
    """
    Deterministic restart with pre-flight, post-restart health verification,
    and audit recording.

    Always returns a RecoveryResult — never raises.
    """
    restart_reason = _derive_restart_reason(incident)
    result = RecoveryResult(
        container_name   = container_name,
        investigation_id = investigation_id,
        restart_reason   = restart_reason,
    )

    # ── Pre-flight ─────────────────────────────────────────────────────────────
    skip_reason = _preflight(container_name)
    if skip_reason:
        result.reason_skipped = skip_reason
        result.attempted      = False
        _audit(result, "skipped")
        print(f"[RECOVERY] Skipping {container_name}: {skip_reason}")
        return result

    # ── OOM guard ──────────────────────────────────────────────────────────────
    if POLICIES.oom_block_restart and incident.get("oom_detected"):
        result.reason_skipped = "oom_block_restart"
        result.attempted      = False
        _audit(result, "skipped")
        print(f"[RECOVERY] OOM guard blocked restart for {container_name}")
        return result

    # ── Get pre-restart status ─────────────────────────────────────────────────
    if _client:
        try:
            c = _client.containers.get(container_name)
            result.pre_restart_status = c.status
        except Exception:
            result.pre_restart_status = "unknown"

    result.attempted = True
    print(f"[RECOVERY] Attempting restart of {container_name} (reason: {restart_reason})")

    start = time.monotonic()

    # ── Restart ────────────────────────────────────────────────────────────────
    if not _client:
        result.error = "Docker client unavailable"
        result.success = False
        _audit(result, "failed")
        return result

    try:
        c = _client.containers.get(container_name)
        c.restart(timeout=10)
    except docker.errors.NotFound:
        result.error   = f"Container '{container_name}' not found"
        result.success = False
        _record_attempt(container_name)
        _audit(result, "failed")
        return result
    except Exception as e:
        result.error   = str(e)
        result.success = False
        _record_attempt(container_name)
        _audit(result, "failed")
        return result

    # ── Health verification ────────────────────────────────────────────────────
    post_health, verified = poll_health(container_name)
    elapsed = time.monotonic() - start

    result.post_health      = post_health
    result.verified_healthy = verified
    result.success          = verified
    result.elapsed_seconds  = round(elapsed, 2)

    _record_attempt(container_name)
    _audit(result, "success" if verified else "unverified")

    print(
        f"[RECOVERY] {container_name}: {'✓' if verified else '✗'} "
        f"post_health={post_health} elapsed={elapsed:.1f}s"
    )
    return result


# ── Helpers ────────────────────────────────────────────────────────────────────

def _derive_restart_reason(incident: dict) -> str:
    incident_type = incident.get("type", "Unknown")
    message       = incident.get("message", "")
    reasons = {
        "ContainerStopped":    "container exited unexpectedly",
        "UnhealthyContainer":  "container healthcheck is failing",
        "ManualInvestigation": "operator-triggered investigation",
        "ManualInspection":    "operator inspection",
    }
    return reasons.get(incident_type, message or incident_type)


def _record_attempt(container_name: str) -> None:
    remediation_timestamps[container_name]  = datetime.now(timezone.utc)
    remediation_retry_counts[container_name] = (
        remediation_retry_counts.get(container_name, 0) + 1
    )


def _audit(result: RecoveryResult, outcome: str) -> None:
    append_audit({
        "ts":               datetime.now(timezone.utc).isoformat(),
        "investigation_id": result.investigation_id,
        "tool":             "deterministic_restart",
        "parameters":       {"container_name": result.container_name},
        "risk_level":       "low",
        "actor":            "recovery_engine",
        "result":           {
            "success":         result.success,
            "outcome":         outcome,
            "reason_skipped":  result.reason_skipped,
            "restart_reason":  result.restart_reason,
            "post_health":     result.post_health,
            "elapsed_seconds": result.elapsed_seconds,
        },
        "duration_ms": int(result.elapsed_seconds * 1000),
    })
