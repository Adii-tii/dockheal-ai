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
LIFECYCLE_STATES = ["DETECTED", "INVESTIGATING", "VALIDATING", "EXECUTING", "RESOLVED",
                    "ESCALATED", "BLOCKED"]


def _set_state(investigation_id: str, state: str, extra: dict | None = None) -> dict:
    entry = investigation_states.get(investigation_id, {})
    entry["state"]      = state
    entry["updated_at"] = datetime.now(timezone.utc).isoformat()
    if extra:
        entry.update(extra)
    investigation_states[investigation_id] = entry
    return entry


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

    # ── Lifecycle: INVESTIGATING ───────────────────────────────────────────────
    _set_state(investigation_id, "INVESTIGATING", {"container": container_name})
    await broadcast({
        "type":             "AI_LIFECYCLE",
        "investigation_id": investigation_id,
        "container":        container_name,
        "from_state":       "DETECTED",
        "to_state":         "INVESTIGATING",
    })

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

    # ── Lifecycle: VALIDATING ─────────────────────────────────────────────────
    _set_state(investigation_id, "VALIDATING")
    await broadcast({
        "type":             "AI_LIFECYCLE",
        "investigation_id": investigation_id,
        "container":        container_name,
        "from_state":       "INVESTIGATING",
        "to_state":         "VALIDATING",
    })

    # ── Broadcast complete result (before execution) ───────────────────────────
    await broadcast({
        "type":             "AI_INVESTIGATION_COMPLETE",
        "investigation_id": investigation_id,
        "container":        container_name,
        "result":           ai_result,
        "lifecycle_state":  "VALIDATING",
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

    # ── Requires human → skip execution ───────────────────────────────────────
    if ai_result.get("requires_human") or not ai_result.get("proposed_actions"):
        await _finish(investigation_id, container_name, ai_result, broadcast, lifecycle="ESCALATED")
        return ai_result

    # ── Execute proposed actions through sandbox + guardrails ──────────────────
    _set_state(investigation_id, "EXECUTING")
    await broadcast({
        "type":             "AI_LIFECYCLE",
        "investigation_id": investigation_id,
        "container":        container_name,
        "from_state":       "VALIDATING",
        "to_state":         "EXECUTING",
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
            continue

        # Guardrail check
        gd = guardrails_check(tool_name, parameters, packet, investigation_id)
        if not gd.allowed:
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

        # Execute
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
    final_state = "RESOLVED" if any_executed else "ESCALATED"
    ai_result["execution_results"] = execution_results
    await _finish(investigation_id, container_name, ai_result, broadcast, lifecycle=final_state)

    return ai_result


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
