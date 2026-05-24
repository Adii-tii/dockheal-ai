"""
Sandbox Validation — lightweight precondition checks per tool.

NOT a production simulation. NOT a Docker API mock.
Fast, synchronous, deterministic Go/No-Go decisions.

validate(tool_call, packet) → SandboxResult
"""

from datetime import datetime, timezone

import docker

from app.runtime.state import (
    manually_stopped,
    operator_lock,
    PACKET_MAX_AGE_SECS,
)

try:
    _client = docker.from_env()
except Exception:
    _client = None


class SandboxResult:
    def __init__(
        self,
        approved: bool,
        predicted_side_effects: list[str],
        risk_assessment: str,
        blocking_reason: str | None = None,
    ):
        self.approved                = approved
        self.predicted_side_effects  = predicted_side_effects
        self.risk_assessment         = risk_assessment
        self.blocking_reason         = blocking_reason

    def to_dict(self) -> dict:
        return {
            "approved":                self.approved,
            "predicted_side_effects":  self.predicted_side_effects,
            "risk_assessment":         self.risk_assessment,
            "blocking_reason":         self.blocking_reason,
        }


def _no(reason: str, effects: list[str] | None = None) -> SandboxResult:
    return SandboxResult(
        approved=False,
        predicted_side_effects=effects or [],
        risk_assessment="precondition failed",
        blocking_reason=reason,
    )

def _yes(effects: list[str], assessment: str) -> SandboxResult:
    return SandboxResult(
        approved=True,
        predicted_side_effects=effects,
        risk_assessment=assessment,
    )


def validate(tool_name: str, parameters: dict, packet: dict) -> SandboxResult:
    """
    Run precondition checks for a proposed tool call.

    safe tools → always approved (skip sandbox).
    low tools  → lightweight checks, auto-approve if passing.
    medium/high → return approved=False (guardrails handle human gate).
    """
    # First check: Is the tool blocked in settings?
    from app.runtime.policy_registry import POLICIES
    if tool_name in getattr(POLICIES, "blocked_tools", []):
        return _no(f"Tool '{tool_name}' is blocked by operator sandbox configuration.")

    from app.ai.tools.decorator import TOOL_METADATA
    meta = TOOL_METADATA.get(tool_name, {})
    risk = meta.get("risk_level", "high")

    # Safe tools — no sandbox needed
    if risk == "safe":
        return _yes(effects=[], assessment="read-only — no side effects")

    container_name = parameters.get("container_name", "")

    # Common check: packet freshness
    generated_at = packet.get("generated_at")
    if generated_at:
        try:
            ts = datetime.fromisoformat(generated_at)
            age = (datetime.now(timezone.utc) - ts).total_seconds()
            if age > PACKET_MAX_AGE_SECS:
                return _no(f"Context packet is {int(age)}s old — stale data, cannot validate safely.")
        except Exception:
            pass

    # Common check: container exists
    if container_name.startswith("mock-"):
        container = "mock"
    elif _client and container_name:
        try:
            container = _client.containers.get(container_name)
        except docker.errors.NotFound:
            return _no(f"Container '{container_name}' does not exist.")
        except Exception as e:
            return _no(f"Could not reach Docker: {e}")
    else:
        container = None

    # ── Per-tool checks ────────────────────────────────────────────────────────

    if tool_name == "restart_container":
        return _sandbox_restart(container, container_name, packet)

    if tool_name == "update_memory_limit":
        return _sandbox_update_memory(container, parameters, packet)

    # Default for unknown tools
    return _no(f"No sandbox rule defined for '{tool_name}' — blocked by default.")


def _sandbox_restart(container, container_name: str, packet: dict) -> SandboxResult:
    if container == "mock":
        effects = [
            f"Mock container '{container_name}' will be restarted (simulated).",
        ]
        return _yes(effects=effects, assessment=f"restart of mock container '{container_name}' is low-risk")

    if container is None:
        return _no(f"Container '{container_name}' not found.")

    # Must be in a restartable state
    if container.status not in ("running", "exited", "restarting"):
        return _no(
            f"Container is in state '{container.status}' — restart not meaningful.",
            effects=[],
        )

    # OOM guard (defence-in-depth — guardrails also check this)
    events = packet.get("recent_events", {})
    if events.get("oom_detected"):
        return _no("OOM detected — restart will likely OOM again immediately.")

    # Estimate downtime
    uptime = packet.get("metrics_snapshot", {}).get("uptime_seconds", 0)
    effects = [
        f"Container '{container_name}' will be unavailable for ~5-15s during restart.",
        f"Current uptime ({uptime}s) will reset to 0.",
    ]

    # Check dependency peer impact
    deps = packet.get("dependency_context", {})
    depends_on = deps.get("depends_on", [])
    if depends_on:
        effects.append(
            f"Downstream containers depending on this service may be affected: {depends_on}"
        )

    return _yes(effects=effects, assessment=f"restart of '{container_name}' is low-risk — preconditions met")


def _sandbox_update_memory(container, parameters: dict, packet: dict) -> SandboxResult:
    if container == "mock":
        new_limit_mb = parameters.get("memory_mb", 0)
        return _yes(
            effects=[f"Memory limit for mock container '{parameters.get('container_name')}' will change to {new_limit_mb} MB (simulated)."],
            assessment="Mock memory limit update simulation approved."
        )

    if container is None:
        return _no("Container not found.")

    new_limit_mb = parameters.get("memory_mb", 0)
    current_usage_mb = packet.get("metrics_snapshot", {}).get("mem_usage_mb", 0)

    if new_limit_mb <= 0:
        return _no("memory_mb must be a positive integer.")

    # New limit must be at least current usage + 20% headroom
    min_required = current_usage_mb * 1.2
    if new_limit_mb < min_required:
        return _no(
            f"New limit ({new_limit_mb} MB) too close to current usage ({current_usage_mb:.0f} MB). "
            f"Minimum recommended: {min_required:.0f} MB (usage + 20% headroom)."
        )

    return _yes(
        effects=[f"Memory limit for '{parameters.get('container_name')}' will change to {new_limit_mb} MB."],
        assessment=f"New limit provides {(new_limit_mb - current_usage_mb):.0f} MB headroom.",
    )
