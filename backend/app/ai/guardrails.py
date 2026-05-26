"""
Guardrail Engine — hard and soft policy rules.
Last gate before any tool execution. Cannot be overridden by AI confidence.

check(tool_call, packet, investigation_id) → GuardrailDecision
"""

from datetime import datetime, timezone
from typing import Literal

from app.runtime.policy_registry import POLICIES
from app.runtime.state import (
    manually_stopped,
    operator_lock,
    remediation_timestamps,
    remediation_retry_counts,
)

# Explicit whitelist of read-only diagnostic tools that bypass operational constraints
SAFE_DIAGNOSTIC_TOOLS = {"fetch_logs", "inspect_container", "send_alert"}


# ── Decision schema ────────────────────────────────────────────────────────────
class GuardrailDecision:
    def __init__(
        self,
        allowed: bool,
        action: Literal["execute", "warn", "block", "escalate"],
        reason: str,
        soft_warnings: list[str] | None = None,
    ):
        self.allowed        = allowed
        self.action         = action
        self.reason         = reason
        self.soft_warnings  = soft_warnings or []

    def to_dict(self) -> dict:
        return {
            "allowed":       self.allowed,
            "action":        self.action,
            "reason":        self.reason,
            "soft_warnings": self.soft_warnings,
        }


def _block(reason: str) -> GuardrailDecision:
    return GuardrailDecision(allowed=False, action="block", reason=reason)

def _escalate(reason: str) -> GuardrailDecision:
    return GuardrailDecision(allowed=False, action="escalate", reason=reason)

def _execute(warnings: list[str] | None = None) -> GuardrailDecision:
    return GuardrailDecision(allowed=True, action="execute", reason="all checks passed", soft_warnings=warnings)


def check(
    tool_name: str,
    parameters: dict,
    packet: dict,
    investigation_id: str,
) -> GuardrailDecision:
    """
    Run all guardrail rules against a proposed tool call.

    Args:
        tool_name:        Name of the tool to be executed.
        parameters:       Parameters the AI proposed.
        packet:           The full OperationalContext investigation packet.
        investigation_id: UUID of the current investigation.

    Returns:
        GuardrailDecision — check .allowed before executing.
    """
    container_name = parameters.get("container_name") or packet.get("incident", {}).get("container", "")
    assessment     = packet.get("assessment", {})
    events         = packet.get("recent_events", {})
    deps           = packet.get("dependency_context", {})
    metrics        = packet.get("metrics_snapshot", {})
    soft_warnings: list[str] = []

    # ── HARD RULES — checked in priority order ─────────────────────────────────

    from app.ai.tools.decorator import TOOL_METADATA
    meta = TOOL_METADATA.get(tool_name, {})

    # Explicit safe diagnostic tools bypass all hard blocks and severity/remediation gates
    if tool_name in SAFE_DIAGNOSTIC_TOOLS:
        from app.context.aggregator import CPU_HIGH, MEM_HIGH
        score = assessment.get("severity_score", 0)
        if score >= 60:
            soft_warnings.append(f"High severity_score ({score}) — monitor closely after execution.")

        if not packet.get("ai_result", {}).get("evidence_citations"):
            soft_warnings.append("AI action not grounded in telemetry citations.")

        confidence = packet.get("ai_result", {}).get("confidence", 1.0)
        if confidence < 0.75:
            soft_warnings.append(f"AI confidence {confidence:.0%} — below 75% threshold.")

        unhealthy_peers = deps.get("unhealthy_peers", [])
        if len(unhealthy_peers) >= 1:
            soft_warnings.append(
                f"Peer containers also degraded: {', '.join(unhealthy_peers)}. "
                f"Restarting this container may not resolve the incident."
            )
        return _execute(soft_warnings)

    # 1. Phase 2 tool hard-block
    if meta.get("phase", 1) == 2:
        return _block(f"'{tool_name}' is a Phase 2 tool and cannot be executed autonomously yet.")

    # 2. Manual stop protection
    if container_name in manually_stopped:
        return _block(f"'{container_name}' was manually stopped — autonomous action blocked.")

    # 3. Operator lock
    if container_name in operator_lock:
        return _block(f"'{container_name}' is held by operator lock. Release with POST /unlock/{container_name}.")

    # 4. Cooldown window
    last_action = remediation_timestamps.get(container_name)
    if last_action:
        age = (datetime.now(timezone.utc) - last_action).total_seconds()
        if age < POLICIES.cooldown_seconds:
            remaining = int(POLICIES.cooldown_seconds - age)
            return _block(f"Cooldown active for '{container_name}' — {remaining}s remaining.")

    # 5. Retry limit
    retry_count = remediation_retry_counts.get(container_name, 0)
    if retry_count >= POLICIES.max_retries:
        return _escalate(
            f"'{container_name}' has been remediated {retry_count} times this incident window. "
            f"Max retries ({POLICIES.max_retries}) reached — escalating to human."
        )

    # 6. Stale packet guard (only applies to non-read-only tools)
    if meta.get("risk_level") not in ("safe",):
        generated_at = packet.get("generated_at")
        if generated_at:
            try:
                ts = datetime.fromisoformat(generated_at)
                age_secs = (datetime.now(timezone.utc) - ts).total_seconds()
                if age_secs > POLICIES.packet_max_age_secs:
                    return _block(
                        f"Context packet is {int(age_secs)}s old (max {POLICIES.packet_max_age_secs}s). "
                        f"Rebuild with POST /context/{container_name}/build before retrying."
                    )
            except Exception:
                pass

    # 7. OOM + restart guard
    if tool_name == "restart_container" and events.get("oom_detected"):
        return _escalate(
            "OOM kill detected — restarting won't fix the root cause. "
            "Increase memory limit or investigate leak before restarting."
        )

    # 8. Severity gate (read from POLICIES — not hardcoded)
    score = assessment.get("severity_score", 0)
    if score >= POLICIES.severity_gate:
        return _escalate(
            f"severity_score={score} ≥ {POLICIES.severity_gate} — human confirmation required before any action."
        )

    # 9. High risk tool gate (Phase 1: block all high risk)
    if meta.get("risk_level") == "high":
        return _escalate(
            f"'{tool_name}' is high-risk. Escalating to human — autonomous high-risk execution disabled in Phase 1."
        )

    # 10. Medium risk tool gate (requires human approval)
    if meta.get("risk_level") == "medium":
        return _escalate(
            f"'{tool_name}' is medium-risk. Awaiting operator approval."
        )

    # 11. Cascade guard
    unhealthy_peers = deps.get("unhealthy_peers", [])
    if len(unhealthy_peers) >= 3:
        return _escalate(
            f"{len(unhealthy_peers)} peer containers are unhealthy — possible infra-level failure. "
            f"Single-container remediation unlikely to help. Human review required."
        )

    # 12. Blast radius guard (only meaningful if tool takes multiple targets — future)
    # Placeholder for when batch actions are introduced.

    # ── SOFT WARNINGS — execution proceeds but frontend is notified ────────────

    from app.context.aggregator import CPU_HIGH, MEM_HIGH
    if score >= 60:
        soft_warnings.append(f"High severity_score ({score}) — monitor closely after execution.")

    if not packet.get("ai_result", {}).get("evidence_citations"):
        soft_warnings.append("AI action not grounded in telemetry citations.")

    confidence = packet.get("ai_result", {}).get("confidence", 1.0)
    if confidence < 0.75:
        soft_warnings.append(f"AI confidence {confidence:.0%} — below 75% threshold.")

    if len(unhealthy_peers) >= 1:
        soft_warnings.append(
            f"Peer containers also degraded: {', '.join(unhealthy_peers)}. "
            f"Restarting this container may not resolve the incident."
        )

    # ── APPROVED ───────────────────────────────────────────────────────────────
    return _execute(soft_warnings)
