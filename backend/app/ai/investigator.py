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
import uuid
import logging
from datetime import datetime, timezone
from typing import Callable, Awaitable

from dotenv import load_dotenv
from mistralai.client import Mistral

from app.ai.prompt_builder import build_system_prompt, build_user_message
from app.ai.output_parser import parse_output, build_correction_turn
from app.ai.sandbox import validate as sandbox_validate
from app.ai.guardrails import check as guardrails_check
from app.ai.tools.registry import execute_tool, async_execute_tool
from app.ai.deep_investigator import deep_investigation_loop
from app.runtime.state import (
    investigation_states,
    remediation_timestamps,
    remediation_retry_counts,
    context_store,
    COOLDOWN_SECONDS,
)

# DB imports
from app.db.config.config import AsyncSessionLocal
from app.db.models import LifecycleState, SeverityLevel, SourceType, RecoveryAction, RCAReport
from app.db.models.enums import ExecutionStatus
from app.db.utils.event_logger import update_lifecycle, log_timeline_event
from app.db.dao.rca_report_dao import RCAReportDAO
from sqlalchemy import select

logger = logging.getLogger(__name__)

load_dotenv()

_API_KEY = os.getenv("API_KEY")

# Model selection: use large for escalated incidents
_MODEL_STANDARD  = "mistral-medium-latest"
_MODEL_ESCALATED = "mistral-large-latest"
_TEMPERATURE     = 0.2
_MAX_TOKENS      = 1024   # reasoning streams; final JSON is compact

_mistral_semaphore = asyncio.Semaphore(1)

# ── Lifecycle state transitions ────────────────────────────────────────────────
LIFECYCLE_STATES = ["DETECTED", "INVESTIGATING", "RCA_IDENTIFIED", "AWAITING_APPROVAL", "RECOVERING", "MONITORING", "RESOLVED", "REJECTED", "TIMED_OUT", "ESCALATED"]


def _set_state(investigation_id: str, state: str, extra: dict | None = None) -> dict:
    entry = investigation_states.get(investigation_id, {})
    entry["state"]      = state
    entry["updated_at"] = datetime.now(timezone.utc).isoformat()
    if extra:
        entry.update(extra)
    investigation_states[investigation_id] = entry
    return entry


async def _update_db_state(
    investigation_id: uuid.UUID,
    new_state: LifecycleState,
    correlation_id: str | None = None,
    extra_fields: dict | None = None,
):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await update_lifecycle(session, investigation_id, new_state, correlation_id, extra_fields)


async def _log_db_timeline_event(
    investigation_id: uuid.UUID,
    event_type: str,
    title: str,
    description: str | None = None,
    source_type: SourceType = SourceType.AI_AGENT,
    severity: SeverityLevel | None = None,
    correlation_id: str | None = None,
    extra_context: dict | None = None,
    raw_data: dict | None = None,
    tool_output: dict | None = None,
):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await log_timeline_event(
                session,
                investigation_id,
                event_type,
                title,
                description,
                source_type,
                severity,
                correlation_id,
                extra_context,
                raw_data,
                tool_output,
            )


async def append_db_and_memory_timeline_event(
    investigation_id: uuid.UUID,
    event_type: str,
    title: str,
    description: str | None = None,
    source_type: SourceType = SourceType.AI_AGENT,
    severity: SeverityLevel | None = None,
    correlation_id: str | None = None,
    extra_context: dict | None = None,
    raw_data: dict | None = None,
    tool_output: dict | None = None,
) -> None:
    # 1. Update DB
    await _log_db_timeline_event(
        investigation_id=investigation_id,
        event_type=event_type,
        title=title,
        description=description,
        source_type=source_type,
        severity=severity,
        correlation_id=correlation_id,
        extra_context=extra_context,
        raw_data=raw_data,
        tool_output=tool_output,
    )
    
    # 2. Update memory
    inv_id_str = str(investigation_id)
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": event_type,
        "title": title,
        "description": description or "",
        "source": source_type.value if hasattr(source_type, "value") else str(source_type),
        "severity": severity.value if (severity and hasattr(severity, "value")) else (str(severity) if severity else "P3"),
    }
    entry = investigation_states.get(inv_id_str, {})
    if "timeline" not in entry:
        entry["timeline"] = []
    entry["timeline"].append(event)
    investigation_states[inv_id_str] = entry


async def _finish_db_and_memory(
    investigation_id: str,
    container_name: str,
    result: dict,
    packet: dict,
    execution_results: list,
    lifecycle: LifecycleState,
    correlation_id: str | None = None,
) -> None:
    inv_uuid = uuid.UUID(investigation_id) if isinstance(investigation_id, str) else investigation_id
    
    # 1. Update in-memory state
    _set_state(investigation_id, lifecycle.value, {"final_result": result})
    if container_name in context_store:
        context_store[container_name]["ai_result"] = result

    # 2. Update DB under optimistic locking
    extra_fields = {
        "root_cause": result.get("root_cause"),
        "confidence": result.get("confidence"),
        "ai_reasoning_summary": result.get("rca_report", {}).get("ai_reasoning_summary") if result.get("rca_report") else (result.get("root_cause") or ""),
        "decision_trace": {
            "proposed_actions": result.get("proposed_actions", []),
            "execution_results": execution_results,
            "preventive_recommendations": result.get("preventive_recommendations", []),
            "evidence_citations": result.get("evidence_citations", []),
            "reason_for_restart": result.get("reason_for_restart", ""),
        },
        "detected_signals": packet.get("assessment", {}).get("likely_causes", []),
        # Persist the full reasoning stream
        "thoughts": investigation_states.get(investigation_id, {}).get("thoughts") or "",
    }
    if lifecycle == LifecycleState.RESOLVED:
        extra_fields["resolved_at"] = datetime.now(timezone.utc)

    await _update_db_state(inv_uuid, lifecycle, correlation_id, extra_fields)


async def append_timeline_event(
    investigation_id: str,
    event_type: str,
    title: str,
    description: str,
    source: str,
    severity: str,
    broadcast: Callable,
) -> None:
    # Deprecated fallback for compatibility with deep_investigator if needed
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
    
    inv_uuid = uuid.UUID(investigation_id) if isinstance(investigation_id, str) else investigation_id
    correlation_id = packet.get("correlation_id") or f"corr_{uuid.uuid4().hex[:12]}"

    # Register the task
    current_task = asyncio.current_task()
    from app.runtime.state import active_tasks
    active_tasks[investigation_id] = current_task

    try:
        # ── Lifecycle: INVESTIGATING ───────────────────────────────────────────────
        severity_str = packet.get("incident", {}).get("severity", "P2")
        try:
            severity_val = SeverityLevel(severity_str)
        except ValueError:
            severity_val = SeverityLevel.P2

        _set_state(investigation_id, "INVESTIGATING", {
            "container": container_name,
            "severity": severity_str
        })
        await _update_db_state(inv_uuid, LifecycleState.INVESTIGATING, correlation_id)
        await append_db_and_memory_timeline_event(
            investigation_id=inv_uuid,
            event_type="LOG_COLLECTION",
            title="Investigation Started",
            description=f"AI Agent initialized for {container_name}. Analyzing context...",
            source_type=SourceType.AI_AGENT,
            severity=SeverityLevel.P3,
            correlation_id=correlation_id,
        )

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
            await _finish_db_and_memory(
                investigation_id=investigation_id,
                container_name=container_name,
                result=result,
                packet=packet,
                execution_results=[],
                lifecycle=LifecycleState.ESCALATED,
                correlation_id=correlation_id,
            )
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
        await _update_db_state(inv_uuid, LifecycleState.RCA_IDENTIFIED, correlation_id)
        await append_db_and_memory_timeline_event(
            investigation_id=inv_uuid,
            event_type="RCA_GENERATED",
            title="RCA Identified",
            description="Root cause analysis report generated by AI.",
            source_type=SourceType.AI_AGENT,
            severity=SeverityLevel.P3,
            correlation_id=correlation_id,
        )

        # Create RCA report in DB
        rca_data = ai_result.get("rca_report")
        if rca_data:
            try:
                async with AsyncSessionLocal() as session:
                    async with session.begin():
                        rca_dao = RCAReportDAO(session)
                        next_v = await rca_dao.next_version(inv_uuid)
                        rca_obj = RCAReport(
                            investigation_id=inv_uuid,
                            rca_version=next_v,
                            is_final=True,
                            incident_summary=rca_data.get("incident_summary"),
                            impact_assessment=rca_data.get("impact_assessment"),
                            what_failed=rca_data.get("what_failed"),
                            why_it_happened=rca_data.get("why_it_happened"),
                            action_proposed=rca_data.get("action_proposed"),
                            recovery_status=rca_data.get("recovery_status"),
                            long_term_prevention=rca_data.get("long_term_prevention"),
                            confidence_score=rca_data.get("confidence_score"),
                            ai_reasoning_summary=rca_data.get("ai_reasoning_summary"),
                            evidence_found=[rca_data.get("evidence_found")] if rca_data.get("evidence_found") else [],
                            contributing_factors=[rca_data.get("contributing_factors")] if rca_data.get("contributing_factors") else [],
                        )
                        session.add(rca_obj)
            except Exception as rca_err:
                logger.error(f"Failed to save RCAReport in DB: {rca_err}")

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
            # Broadcast the updated final result after the deep investigation loop completes
            await broadcast({
                "type":             "AI_INVESTIGATION_COMPLETE",
                "investigation_id": investigation_id,
                "container":        container_name,
                "result":           ai_result,
                "lifecycle_state":  "RCA_IDENTIFIED",
            })

        from app.runtime.policy_registry import POLICIES

        # ── Requires human → skip execution if no actions ──────────────────────────
        if (ai_result.get("requires_human") and not ai_result.get("proposed_actions")) or not ai_result.get("proposed_actions") or POLICIES.agent_mode == "Manual":
            await _finish_db_and_memory(
                investigation_id=investigation_id,
                container_name=container_name,
                result=ai_result,
                packet=packet,
                execution_results=[],
                lifecycle=LifecycleState.RESOLVED,
                correlation_id=correlation_id,
            )
            return ai_result

        # ── Execute proposed actions through sandbox + guardrails ──────────────────
        _set_state(investigation_id, "RECOVERING")
        await _update_db_state(inv_uuid, LifecycleState.RECOVERING, correlation_id)

        execution_results = []
        any_executed      = False

        for action in ai_result.get("proposed_actions", []):
            tool_name  = action.get("tool")
            parameters = action.get("parameters", {})

            # Sandbox check — runs a Docker container.get() call internally;
            # wrap in to_thread so it does not freeze the event loop.
            sandbox_result = await asyncio.to_thread(sandbox_validate, tool_name, parameters, packet)
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
                await append_db_and_memory_timeline_event(
                    investigation_id=inv_uuid,
                    event_type="SANDBOX_BLOCKED",
                    title="Execution Blocked",
                    description=f"{tool_name} was blocked by sandbox policies.",
                    source_type=SourceType.SYSTEM,
                    severity=SeverityLevel.P2,
                    correlation_id=correlation_id,
                )
                continue

            # Guardrail check
            gd = guardrails_check(tool_name, parameters, packet, investigation_id)

            # Immediate block handling — blocks cannot be bypassed or approved
            if gd.action == "block":
                execution_results.append({
                    "tool":    tool_name,
                    "outcome": "blocked",
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
                await append_db_and_memory_timeline_event(
                    investigation_id=inv_uuid,
                    event_type="GUARDRAIL_BLOCKED",
                    title="Execution Blocked by Guardrail",
                    description=f"{tool_name} was hard-blocked by guardrails: {gd.reason}",
                    source_type=SourceType.SYSTEM,
                    severity=SeverityLevel.P2,
                    correlation_id=correlation_id,
                )
                continue

            requires_approval = (POLICIES.agent_mode == "Co-Pilot") or ai_result.get("requires_human") or gd.action == "escalate"

            if requires_approval:
                extra_fields = {
                    "root_cause": ai_result.get("root_cause"),
                    "confidence": ai_result.get("confidence"),
                    "ai_reasoning_summary": ai_result.get("rca_report", {}).get("ai_reasoning_summary") if ai_result.get("rca_report") else (ai_result.get("root_cause") or ""),
                    "decision_trace": {
                        "proposed_actions": ai_result.get("proposed_actions", []),
                        "execution_results": [],
                        "preventive_recommendations": ai_result.get("preventive_recommendations", []),
                        "evidence_citations": ai_result.get("evidence_citations", []),
                        "reason_for_restart": ai_result.get("reason_for_restart", ""),
                    },
                }
                _set_state(investigation_id, "AWAITING_APPROVAL", {"final_result": ai_result, "result": ai_result})
                await _update_db_state(inv_uuid, LifecycleState.AWAITING_APPROVAL, correlation_id, extra_fields)
                await broadcast({
                    "type":             "AI_INVESTIGATION_COMPLETE",
                    "investigation_id": investigation_id,
                    "container":        container_name,
                    "result":           ai_result,
                    "lifecycle_state":  "AWAITING_APPROVAL",
                })
                await append_db_and_memory_timeline_event(
                    investigation_id=inv_uuid,
                    event_type="APPROVAL_REQUIRED",
                    title="Approval Required",
                    description=f"Action {tool_name} requires operator sign-off.",
                    source_type=SourceType.SYSTEM,
                    severity=SeverityLevel.P2,
                    correlation_id=correlation_id,
                )
                
                from app.runtime.state import approval_events, approval_results
                approval_events[investigation_id] = asyncio.Event()
                try:
                    try:
                        # 5-minute timeout deadline
                        await asyncio.wait_for(approval_events[investigation_id].wait(), timeout=300)
                        res = approval_results.get(investigation_id, {})
                        if res.get("status") == "approved":
                            await append_db_and_memory_timeline_event(
                                investigation_id=inv_uuid,
                                event_type="ACTION_APPROVED",
                                title="Action Approved",
                                description=f"Approved by {res.get('user', 'Operator')}.",
                                source_type=SourceType.HUMAN,
                                severity=SeverityLevel.P3,
                                correlation_id=correlation_id,
                            )
                            _set_state(investigation_id, "RECOVERING")
                            await _update_db_state(inv_uuid, LifecycleState.RECOVERING, correlation_id)
                        else:
                            await append_db_and_memory_timeline_event(
                                investigation_id=inv_uuid,
                                event_type="ACTION_REJECTED",
                                title="Action Rejected",
                                description=f"Rejected by {res.get('user', 'Operator')}.",
                                source_type=SourceType.HUMAN,
                                severity=SeverityLevel.P2,
                                correlation_id=correlation_id,
                            )
                            execution_results.append({"tool": tool_name, "outcome": "rejected_by_operator"})
                            _set_state(investigation_id, "REJECTED")
                            await _update_db_state(inv_uuid, LifecycleState.REJECTED, correlation_id)
                            break
                    except asyncio.TimeoutError:
                        is_high_severity = severity_str in ("P0", "P1")
                        timeout_state = LifecycleState.ESCALATED if is_high_severity else LifecycleState.TIMED_OUT
                        
                        _set_state(investigation_id, timeout_state.value)
                        await _update_db_state(inv_uuid, timeout_state, correlation_id)
                        
                        if timeout_state == LifecycleState.ESCALATED:
                            await append_db_and_memory_timeline_event(
                                investigation_id=inv_uuid,
                                event_type="APPROVAL_TIMEOUT",
                                title="Approval Timeout - Escalated",
                                description="No response in 5 minutes. Action auto-rejected and escalated.",
                                source_type=SourceType.SYSTEM,
                                severity=SeverityLevel.P1,
                                correlation_id=correlation_id,
                            )
                            execution_results.append({"tool": tool_name, "outcome": "timeout_escalated"})
                        else:
                            await append_db_and_memory_timeline_event(
                                investigation_id=inv_uuid,
                                event_type="APPROVAL_TIMEOUT",
                                title="Approval Timeout - Timed Out",
                                description="No response in 5 minutes. Action timed out.",
                                source_type=SourceType.SYSTEM,
                                severity=SeverityLevel.P2,
                                correlation_id=correlation_id,
                            )
                            execution_results.append({"tool": tool_name, "outcome": "timeout_rejected"})
                        
                        break
                finally:
                    logger.info(f"[APPROVAL] Purged memory structures for investigation {investigation_id} to prevent leaks.")
                    approval_events.pop(investigation_id, None)
                    approval_results.pop(investigation_id, None)

            await append_db_and_memory_timeline_event(
                investigation_id=inv_uuid,
                event_type="TOOL_EXECUTION",
                title="Executing Action",
                description=f"Running {tool_name} with provided parameters.",
                source_type=SourceType.AI_AGENT,
                severity=SeverityLevel.P2,
                correlation_id=correlation_id,
            )

            await broadcast({
                "type":             "TOOL_EXECUTING",
                "investigation_id": investigation_id,
                "container":        container_name,
                "tool":             tool_name,
                "parameters":       parameters,
                "warnings":         gd.soft_warnings,
            })

            # Create a RecoveryAction record in DB
            recovery_action_id = None
            try:
                async with AsyncSessionLocal() as session:
                    async with session.begin():
                        recovery_action = RecoveryAction(
                            investigation_id=inv_uuid,
                            action_name=tool_name,
                            action_type="CUSTOM",
                            execution_status=ExecutionStatus.RUNNING,
                            started_at=datetime.now(timezone.utc),
                            parameters=parameters,
                            correlation_id=correlation_id,
                        )
                        session.add(recovery_action)
                        await session.flush()
                        recovery_action_id = recovery_action.id
            except Exception as db_err:
                logger.error(f"Failed to insert RecoveryAction start record to DB: {db_err}")

            # Execute tool — all Docker SDK calls inside are blocking.
            # async_execute_tool offloads the entire call to a thread pool.
            tool_result = await async_execute_tool(
                tool_name        = tool_name,
                parameters       = parameters,
                investigation_id = investigation_id,
                actor            = "ai_auto",
            )

            # Log tool execution to timeline
            success = tool_result.get("success", False) if isinstance(tool_result, dict) else False
            out_str = tool_result.get("output", "") if isinstance(tool_result, dict) else str(tool_result)
            
            if tool_name == "restart_container" and success:
                await append_db_and_memory_timeline_event(
                    investigation_id=inv_uuid,
                    event_type="CONTAINER_RESTART",
                    title="Container Restarted by AI Agent",
                    description=f"Container '{container_name}' was restarted successfully by the AI agent at {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC. Reason: {action.get('rationale') or 'RCA remediation'}",
                    source_type=SourceType.AI_AGENT,
                    severity=SeverityLevel.P3,
                    correlation_id=correlation_id,
                )
            else:
                await append_db_and_memory_timeline_event(
                    investigation_id=inv_uuid,
                    event_type="TOOL_EXECUTED",
                    title=f"Tool Executed: {tool_name}",
                    description=f"Tool executed. Status: {'SUCCESS' if success else 'FAILED'}. Output: {out_str[:200]}...",
                    source_type=SourceType.AI_AGENT,
                    severity=SeverityLevel.P3 if success else SeverityLevel.P2,
                    correlation_id=correlation_id,
                )

            # Update the RecoveryAction record in DB
            if recovery_action_id:
                try:
                    success = tool_result.get("success", False) if isinstance(tool_result, dict) else False
                    status = ExecutionStatus.SUCCESS if success else ExecutionStatus.FAILED
                    logs = json.dumps(tool_result) if tool_result else ""
                    
                    async with AsyncSessionLocal() as session:
                        async with session.begin():
                            res = await session.execute(
                                select(RecoveryAction).where(RecoveryAction.id == recovery_action_id)
                            )
                            rec_act = res.scalar_one_or_none()
                            if rec_act:
                                rec_act.execution_status = status
                                rec_act.execution_logs = logs
                                rec_act.completed_at = datetime.now(timezone.utc)
                except Exception as db_err:
                    logger.error(f"Failed to update RecoveryAction end record in DB: {db_err}")

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
        is_resolved = False
        post_health = "no_action_executed"
        if any_executed:
            _set_state(investigation_id, "MONITORING")
            await _update_db_state(inv_uuid, LifecycleState.MONITORING, correlation_id)
            
            await append_db_and_memory_timeline_event(
                investigation_id=inv_uuid,
                event_type="MONITORING_HEALTH",
                title="Monitoring Health",
                description=f"Verifying container recovery for {container_name}...",
                source_type=SourceType.AI_AGENT,
                severity=SeverityLevel.P3,
                correlation_id=correlation_id,
            )
            # Run the robust polling health verification from recovery.py in a thread
            from app.services.recovery import poll_health
            post_health, verified = await asyncio.to_thread(poll_health, container_name)
            is_resolved = verified
        else:
            verified = False

        final_state = "RESOLVED" if is_resolved else "ESCALATED"
        if final_state == "RESOLVED":
            await append_db_and_memory_timeline_event(
                investigation_id=inv_uuid,
                event_type="INCIDENT_RESOLVED",
                title="Incident Resolved",
                description=f"Container {container_name} is operating normally. Health verification passed (status: {post_health}).",
                source_type=SourceType.SYSTEM,
                severity=SeverityLevel.P3,
                correlation_id=correlation_id,
            )
        else:
            desc = f"Unable to fully remediate container {container_name}. "
            if any_executed:
                desc += f"Health verification failed (status: {post_health})."
            else:
                desc += "No actions were successfully executed."
            desc += " Escalating to human operators."
            
            await append_db_and_memory_timeline_event(
                investigation_id=inv_uuid,
                event_type="INCIDENT_ESCALATED",
                title="Incident Escalated",
                description=desc,
                source_type=SourceType.SYSTEM,
                severity=SeverityLevel.P2,
                correlation_id=correlation_id,
            )

        ai_result["execution_results"] = execution_results
        final_lifecycle = LifecycleState.RESOLVED if final_state == "RESOLVED" else LifecycleState.ESCALATED
        
        await _finish_db_and_memory(
            investigation_id=investigation_id,
            container_name=container_name,
            result=ai_result,
            packet=packet,
            execution_results=execution_results,
            lifecycle=final_lifecycle,
            correlation_id=correlation_id,
        )

        return ai_result
    except asyncio.CancelledError:
        from app.runtime.state import cancellation_reasons
        reason = cancellation_reasons.pop(investigation_id, "paused")
        if reason == "restarted":
            raise
        if reason == "stopped":
            lifecycle_state = LifecycleState.REJECTED
            rc_message = "Investigation stopped/aborted."
            event_type = "INVESTIGATION_STOPPED"
            event_title = "Investigation Stopped"
            event_desc = "Investigation has been stopped/aborted by the operator."
        else:
            lifecycle_state = LifecycleState.PAUSED
            rc_message = "Investigation paused."
            event_type = "INVESTIGATION_PAUSED"
            event_title = "Investigation Paused"
            event_desc = "Investigation has been paused. The operator can resume it later."

        await _finish_db_and_memory(
            investigation_id=investigation_id,
            container_name=container_name,
            result={
                "investigation_id": investigation_id,
                "container":        container_name,
                "root_cause":       rc_message,
                "confidence":       0.0,
                "evidence_citations": [],
                "proposed_actions": [],
                "requires_human":   False,
            },
            packet=packet,
            execution_results=[],
            lifecycle=lifecycle_state,
            correlation_id=correlation_id,
        )
        await append_db_and_memory_timeline_event(
            investigation_id=inv_uuid,
            event_type=event_type,
            title=event_title,
            description=event_desc,
            source_type=SourceType.SYSTEM,
            severity=SeverityLevel.P3,
            correlation_id=correlation_id,
        )
        raise
    except Exception as e:
        logger.error(f"Investigation crashed with error: {e}", exc_info=True)
        await _finish_db_and_memory(
            investigation_id=investigation_id,
            container_name=container_name,
            result={
                "investigation_id": investigation_id,
                "container":        container_name,
                "root_cause":       f"Investigation crashed: {str(e)}",
                "confidence":       0.0,
                "evidence_citations": [],
                "proposed_actions": [],
                "requires_human":   True,
            },
            packet=packet,
            execution_results=[],
            lifecycle=LifecycleState.ESCALATED,
            correlation_id=correlation_id,
        )
        try:
            await append_db_and_memory_timeline_event(
                investigation_id=inv_uuid,
                event_type="INCIDENT_ESCALATED",
                title="Investigation Crashed",
                description=f"AI Agent encountered an internal crash: {str(e)}. Escalating to human operators.",
                source_type=SourceType.SYSTEM,
                severity=SeverityLevel.P1,
                correlation_id=correlation_id,
            )
        except Exception:
            pass
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
    async with _mistral_semaphore:
        max_retries = 3
        for attempt in range(max_retries):
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
                        # Accumulate in-memory (for persistence at end of investigation)
                        entry = investigation_states.get(investigation_id, {})
                        entry["thoughts"] = (entry.get("thoughts") or "") + delta
                        investigation_states[investigation_id] = entry
                        # Broadcast chunk
                        await broadcast({
                            "type":             "AI_THOUGHT",
                            "investigation_id": investigation_id,
                            "container":        container_name,
                            "chunk":            delta,
                            "sequence":         sequence,
                        })
                # If streaming succeeded, return the text
                return full_text
            except Exception as e:
                logger.error(f"[AI] Mistral stream attempt {attempt + 1}/{max_retries} failed for {container_name}: {e}")
                if attempt < max_retries - 1:
                    wait_time = 2 * (attempt + 1)
                    await broadcast({
                        "type":             "AI_THOUGHT",
                        "investigation_id": investigation_id,
                        "container":        container_name,
                        "chunk":            f"\n[Rate limit/API error, retrying in {wait_time}s...]\n",
                        "sequence":         sequence + 1,
                    })
                    await asyncio.sleep(wait_time)
                else:
                    # Final attempt failed
                    await broadcast({
                        "type":             "AI_THOUGHT",
                        "investigation_id": investigation_id,
                        "container":        container_name,
                        "chunk":            f"[Stream error: {e}]",
                        "sequence":         sequence + 1,
                    })
                    logger.error(f"[AI] Mistral stream failed permanently for {container_name}: {e}", exc_info=True)
                    return ""
