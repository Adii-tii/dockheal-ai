"""
AI Investigator — Mistral streaming RCA engine.

investigate(packet, ws_broadcast_fn) → StructuredAIOutput dict

Pipeline:
  1. Build system prompt from packet.
  2. Stream Mistral response, broadcasting each chunk via WebSocket.
  3. Collect full response text.
  4. Parse into StructuredAIOutput.
  5. On parse failure → 1 retry with correction turn (max 2 API calls total).
  6. Run each proposed_action through sandbox → guardrails.
  7. Execute approved safe/low-risk actions.
  8. Broadcast final result.

Reasoning (chain-of-thought) is streamed to the UI and then discarded.
Only the final StructuredAIOutput is stored.
"""

import os
import json
import asyncio
from datetime import datetime, timezone
from typing import Callable, Awaitable

from dotenv import load_dotenv
from mistralai.client import Mistral

from app.ai.prompt_builder import build_system_prompt, build_user_message
from app.ai.output_parser import parse_output, build_correction_turn
from app.ai.sandbox import validate as sandbox_validate
from app.ai.guardrails import check as guardrails_check
from app.ai.tools.registry import execute_tool
from app.ai.deep_investigator import deep_investigation_loop
from app.runtime.state import (
    investigation_states,
    remediation_timestamps,
    remediation_retry_counts,
    context_store,
    COOLDOWN_SECONDS,
)

load_dotenv()

_API_KEY = os.getenv("API_KEY")

# Model selection: use large for escalated incidents
_MODEL_STANDARD  = "mistral-medium-latest"
_MODEL_ESCALATED = "mistral-large-latest"
_TEMPERATURE     = 0.2
_MAX_TOKENS      = 1024   # reasoning streams; final JSON is compact

# ── Lifecycle state transitions ────────────────────────────────────────────────
LIFECYCLE_STATES = ["DETECTED", "INVESTIGATING", "RCA_IDENTIFIED", "AWAITING_APPROVAL", "RECOVERING", "MONITORING", "RESOLVED", "REJECTED"]


def _set_state(investigation_id: str, state: str, extra: dict | None = None) -> dict:
    entry = investigation_states.get(investigation_id, {})
    entry["state"]      = state
    entry["updated_at"] = datetime.now(timezone.utc).isoformat()
    if extra:
        entry.update(extra)
    investigation_states[investigation_id] = entry
    return entry


async def append_timeline_event(
    investigation_id: str,
    event_type: str,
    title: str,
    description: str,
    source: str,
    severity: str,
    broadcast: Callable,
) -> None:
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": event_type,
        "title": title,
        "description": description,
        "source": source,
        "severity": severity,
    }
    entry = investigation_states.get(investigation_id, {})
    if "timeline" not in entry:
        entry["timeline"] = []
    entry["timeline"].append(event)
    investigation_states[investigation_id] = entry
    
    await broadcast({
        "type": "AI_TIMELINE_EVENT",
        "investigation_id": investigation_id,
        "event": event
    })


async def investigate(
    packet: dict,
    broadcast: Callable[[dict], Awaitable[None]],
) -> dict:
    """
    Main entry point. Runs the full AI investigation pipeline.

    Args:
        packet:    OperationalContext investigation packet.
        broadcast: Async callable that sends a dict to all WebSocket clients.

    Returns:
        StructuredAIOutput dict (or fallback with requires_human=True).
    """
    investigation_id = packet.get("investigation_id", "unknown")
    container_name   = packet.get("incident", {}).get("container", "unknown")
    score            = packet.get("assessment", {}).get("severity_score", 0)

    # Register the task
    current_task = asyncio.current_task()
    from app.runtime.state import active_tasks
    active_tasks[investigation_id] = current_task

    try:
        # ── Lifecycle: INVESTIGATING ───────────────────────────────────────────────
        severity = packet.get("incident", {}).get("severity", "P2")
        _set_state(investigation_id, "INVESTIGATING", {
            "container": container_name,
            "severity": severity
        })
        await broadcast({
            "type":             "AI_LIFECYCLE",
            "investigation_id": investigation_id,
            "container":        container_name,
            "severity":         severity,
            "from_state":       "DETECTED",
            "to_state":         "INVESTIGATING",
        })
        await append_timeline_event(investigation_id, "LOG_COLLECTION", "Investigation Started", f"AI Agent initialized for {container_name}. Analyzing context...", "AI_AGENT", "INFO", broadcast)

        if not _API_KEY:
            result = {
                "investigation_id": investigation_id,
                "container":        container_name,
                "root_cause":       "Mistral API key not configured.",
                "confidence":       0.0,
                "evidence_citations": [],
                "proposed_actions": [],
                "requires_human":   True,
            }
            await _finish(investigation_id, container_name, result, broadcast, lifecycle="ESCALATED")
            return result

        # ── Model selection ────────────────────────────────────────────────────────
        model = _MODEL_ESCALATED if score >= 60 else _MODEL_STANDARD

        # ── Build prompt ───────────────────────────────────────────────────────────
        system_prompt = build_system_prompt(packet)
        user_message  = build_user_message(container_name)

        messages = [
            {"role": "system",  "content": system_prompt},
            {"role": "user",    "content": user_message},
        ]

        # ── Stream Mistral response ────────────────────────────────────────────────
        full_text = await _stream_mistral(
            messages          = messages,
            model             = model,
            investigation_id  = investigation_id,
            container_name    = container_name,
            broadcast         = broadcast,
        )

        # ── Parse output ───────────────────────────────────────────────────────────
        ai_result = parse_output(full_text, investigation_id, container_name)

        # ── Retry if parse failed ──────────────────────────────────────────────────
        if ai_result.get("_parse_error"):
            await broadcast({
                "type":             "AI_THOUGHT",
                "investigation_id": investigation_id,
                "container":        container_name,
                "chunk":            "[Retrying — output schema validation failed]",
                "sequence":         9999,
            })

            correction = build_correction_turn(ai_result["_parse_error"])
            messages.append({"role": "assistant", "content": full_text})
            messages.append({"role": "user",      "content": correction})

            full_text_2 = await _stream_mistral(
                messages         = messages,
                model            = model,
                investigation_id = investigation_id,
                container_name   = container_name,
                broadcast        = broadcast,
                sequence_offset  = 10000,
            )
            ai_result = parse_output(full_text_2, investigation_id, container_name)
            # If still failing → fallback already has requires_human=True

        # ── Store result in packet for guardrail soft-warning access ──────────────
        packet["ai_result"] = ai_result

        # ── Lifecycle: RCA_IDENTIFIED ─────────────────────────────────────────────────
        _set_state(investigation_id, "RCA_IDENTIFIED")
        await broadcast({
            "type":             "AI_LIFECYCLE",
            "investigation_id": investigation_id,
            "container":        container_name,
            "from_state":       "INVESTIGATING",
            "to_state":         "RCA_IDENTIFIED",
        })
        await append_timeline_event(investigation_id, "RCA_GENERATED", "RCA Identified", "Root cause analysis report generated by AI.", "AI_AGENT", "INFO", broadcast)

        # ── Broadcast complete result (before execution) ───────────────────────────
        await broadcast({
            "type":             "AI_INVESTIGATION_COMPLETE",
            "investigation_id": investigation_id,
            "container":        container_name,
            "result":           ai_result,
            "lifecycle_state":  "RCA_IDENTIFIED",
        })

        # ── Deep investigation loop trigger ───────────────────────────────────────
        recovery = packet.get("recovery_attempt", {})
        needs_deep_loop = (
            not recovery.get("success") 
            or ai_result.get("requires_human") 
            or ai_result.get("confidence", 1.0) < 0.6
            or score >= 60
        )

        if needs_deep_loop:
            ai_result = await deep_investigation_loop(packet, ai_result, broadcast)
            packet["ai_result"] = ai_result

        # ── Requires human → skip execution if no actions ──────────────────────────
        if (ai_result.get("requires_human") and not ai_result.get("proposed_actions")) or not ai_result.get("proposed_actions"):
            await _finish(investigation_id, container_name, ai_result, broadcast, lifecycle="RESOLVED")
            return ai_result

        # ── Execute proposed actions through sandbox + guardrails ──────────────────
        _set_state(investigation_id, "RECOVERING")
        await broadcast({
            "type":             "AI_LIFECYCLE",
            "investigation_id": investigation_id,
            "container":        container_name,
            "from_state":       "RCA_IDENTIFIED",
            "to_state":         "RECOVERING",
        })

        execution_results = []
        any_executed      = False

        for action in ai_result.get("proposed_actions", []):
            tool_name  = action.get("tool")
            parameters = action.get("parameters", {})

            # Sandbox check
            sandbox_result = sandbox_validate(tool_name, parameters, packet)
            if not sandbox_result.approved:
                execution_results.append({
                    "tool":    tool_name,
                    "outcome": "sandbox_blocked",
                    "reason":  sandbox_result.blocking_reason,
                })
                await broadcast({
                    "type":             "TOOL_BLOCKED",
                    "investigation_id": investigation_id,
                    "container":        container_name,
                    "tool":             tool_name,
                    "layer":            "sandbox",
                    "reason":           sandbox_result.blocking_reason,
                })
                await append_timeline_event(investigation_id, "SANDBOX_BLOCKED", "Execution Blocked", f"{tool_name} was blocked by sandbox policies.", "SANDBOX", "WARN", broadcast)
                continue

            # Guardrail check
            gd = guardrails_check(tool_name, parameters, packet, investigation_id)
            requires_approval = ai_result.get("requires_human") or gd.action == "escalate"

            if not gd.allowed and not requires_approval:
                execution_results.append({
                    "tool":    tool_name,
                    "outcome": gd.action,
                    "reason":  gd.reason,
                })
                await broadcast({
                    "type":             "TOOL_BLOCKED",
                    "investigation_id": investigation_id,
                    "container":        container_name,
                    "tool":             tool_name,
                    "layer":            "guardrail",
                    "decision":         gd.to_dict(),
                })
                continue

            if requires_approval:
                _set_state(investigation_id, "AWAITING_APPROVAL")
                await broadcast({
                    "type":             "AI_LIFECYCLE",
                    "investigation_id": investigation_id,
                    "container":        container_name,
                    "from_state":       "RECOVERING",
                    "to_state":         "AWAITING_APPROVAL",
                })
                await append_timeline_event(investigation_id, "APPROVAL_REQUIRED", "Approval Required", f"Action {tool_name} requires operator sign-off.", "SYSTEM", "WARN", broadcast)
                
                from app.runtime.state import approval_events, approval_results
                approval_events[investigation_id] = asyncio.Event()
                try:
                    await asyncio.wait_for(approval_events[investigation_id].wait(), timeout=600)
                    res = approval_results.get(investigation_id, {})
                    if res.get("status") == "approved":
                        await append_timeline_event(investigation_id, "ACTION_APPROVED", "Action Approved", f"Approved by {res.get('user', 'Operator')}.", "OPERATOR", "INFO", broadcast)
                        _set_state(investigation_id, "RECOVERING")
                        await broadcast({"type": "AI_LIFECYCLE", "investigation_id": investigation_id, "container": container_name, "from_state": "AWAITING_APPROVAL", "to_state": "RECOVERING"})
                    else:
                        await append_timeline_event(investigation_id, "ACTION_REJECTED", "Action Rejected", f"Rejected by {res.get('user', 'Operator')}.", "OPERATOR", "WARN", broadcast)
                        execution_results.append({"tool": tool_name, "outcome": "rejected_by_operator"})
                        _set_state(investigation_id, "REJECTED")
                        await broadcast({"type": "AI_LIFECYCLE", "investigation_id": investigation_id, "container": container_name, "from_state": "AWAITING_APPROVAL", "to_state": "REJECTED"})
                        continue
                except asyncio.TimeoutError:
                    await append_timeline_event(investigation_id, "APPROVAL_TIMEOUT", "Approval Timeout", "No response in 10 minutes. Action auto-rejected.", "SYSTEM", "WARN", broadcast)
                    execution_results.append({"tool": tool_name, "outcome": "timeout_rejected"})
                    _set_state(investigation_id, "REJECTED")
                    await broadcast({"type": "AI_LIFECYCLE", "investigation_id": investigation_id, "container": container_name, "from_state": "AWAITING_APPROVAL", "to_state": "REJECTED"})
                    continue

            await append_timeline_event(investigation_id, "TOOL_EXECUTION", "Executing Action", f"Running {tool_name} with provided parameters.", "AI_AGENT", "INFO", broadcast)

            await broadcast({
                "type":             "TOOL_EXECUTING",
                "investigation_id": investigation_id,
                "container":        container_name,
                "tool":             tool_name,
                "parameters":       parameters,
                "warnings":         gd.soft_warnings,
            })

            tool_result = execute_tool(
                tool_name        = tool_name,
                parameters       = parameters,
                investigation_id = investigation_id,
                actor            = "ai_auto",
            )

            execution_results.append({
                "tool":    tool_name,
                "outcome": "executed",
                "result":  tool_result,
            })

            await broadcast({
                "type":             "TOOL_RESULT",
                "investigation_id": investigation_id,
                "container":        container_name,
                "tool":             tool_name,
                "result":           tool_result,
            })

            # Update remediation tracking
            _target = parameters.get("container_name", container_name)
            remediation_timestamps[_target]    = datetime.now(timezone.utc)
            remediation_retry_counts[_target]  = remediation_retry_counts.get(_target, 0) + 1

            if tool_result.get("success"):
                any_executed = True

        # ── Lifecycle: RESOLVED or ESCALATED ──────────────────────────────────────
        if any_executed:
            _set_state(investigation_id, "MONITORING")
            await broadcast({
                "type":             "AI_LIFECYCLE",
                "investigation_id": investigation_id,
                "container":        container_name,
                "from_state":       "RECOVERING",
                "to_state":         "MONITORING",
            })
            await append_timeline_event(investigation_id, "MONITORING_HEALTH", "Monitoring Health", f"Verifying container recovery for {container_name}...", "AI_AGENT", "INFO", broadcast)
            await asyncio.sleep(2)  # Simulate brief monitoring phase

        final_state = "RESOLVED" if any_executed else "ESCALATED"
        if final_state == "RESOLVED":
            await append_timeline_event(investigation_id, "INCIDENT_RESOLVED", "Incident Resolved", f"Container {container_name} is operating normally.", "SYSTEM", "INFO", broadcast)
        else:
            await append_timeline_event(investigation_id, "INCIDENT_ESCALATED", "Incident Escalated", "Unable to fully remediate. Escalating to human operators.", "SYSTEM", "WARN", broadcast)

        ai_result["execution_results"] = execution_results
        await _finish(investigation_id, container_name, ai_result, broadcast, lifecycle=final_state)

        return ai_result
    except asyncio.CancelledError:
        await _finish(
            investigation_id,
            container_name,
            {
                "investigation_id": investigation_id,
                "container":        container_name,
                "root_cause":       "Investigation stopped by user.",
                "confidence":       0.0,
                "evidence_citations": [],
                "proposed_actions": [],
                "requires_human":   False,
            },
            broadcast,
            lifecycle="RESOLVED"
        )
        raise
    finally:
        from app.runtime.state import active_tasks
        active_tasks.pop(investigation_id, None)


async def _stream_mistral(
    messages:         list[dict],
    model:            str,
    investigation_id: str,
    container_name:   str,
    broadcast:        Callable[[dict], Awaitable[None]],
    sequence_offset:  int = 0,
) -> str:
    """
    Stream a Mistral chat completion, broadcasting each chunk as AI_THOUGHT.
    Returns the full concatenated response text.
    Reasoning chunks are sent to frontend and then discarded — not stored.
    """
    client    = Mistral(api_key=_API_KEY)
    full_text = ""
    sequence  = sequence_offset

    try:
        # mistralai v2.x async streaming
        result = await client.chat.stream_async(
            model    = model,
            messages = messages,
            temperature = _TEMPERATURE,
            max_tokens  = _MAX_TOKENS,
        )
        async for event in result:
            delta = ""
            try:
                delta = event.data.choices[0].delta.content or ""
            except Exception:
                pass

            if delta:
                full_text += delta
                sequence  += 1
                # Broadcast chunk — ephemeral, not stored after send
                await broadcast({
                    "type":             "AI_THOUGHT",
                    "investigation_id": investigation_id,
                    "container":        container_name,
                    "chunk":            delta,
                    "sequence":         sequence,
                })

    except Exception as e:
        await broadcast({
            "type":             "AI_THOUGHT",
            "investigation_id": investigation_id,
            "container":        container_name,
            "chunk":            f"[Stream error: {e}]",
            "sequence":         sequence + 1,
        })

    return full_text


async def _finish(
    investigation_id: str,
    container_name:   str,
    result:           dict,
    broadcast:        Callable[[dict], Awaitable[None]],
    lifecycle:        str = "RESOLVED",
) -> None:
    """Transition to terminal lifecycle state and broadcast."""
    prev = investigation_states.get(investigation_id, {}).get("state", "EXECUTING")
    _set_state(investigation_id, lifecycle, {"final_result": result})
    # Update context_store with final output
    if container_name in context_store:
        context_store[container_name]["ai_result"] = result

    await broadcast({
        "type":             "AI_LIFECYCLE",
        "investigation_id": investigation_id,
        "container":        container_name,
        "from_state":       prev,
        "to_state":         lifecycle,
    })
