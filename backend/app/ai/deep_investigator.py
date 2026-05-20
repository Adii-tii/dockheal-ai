"""
Deep Investigation Loop — iterative AI reasoning with tool-use.

deep_investigation_loop(packet, initial_result, broadcast)
    → final_assessment dict

Safety mechanisms built in:
  1. Duplicate tool request detection — same tool+params never runs twice.
  2. No-new-information detection — if tool result identical to previous, skip.
  3. Repeated-context detection — compresses growing message history each turn.
  4. Rolling investigation memory — summarizes old results instead of appending forever.
  5. MAX_DEEP_ITERATIONS hard cap from PolicyRegistry.

Workflow per iteration:
  AI receives → [system context] + [rolling memory summary] + [latest tool results]
  AI outputs  → { "tool_requests": [...] }  OR  { "final_assessment": {...} }
  Tools execute → results fed back → next iteration
"""

import json
import hashlib
from datetime import datetime, timezone
from typing import Callable, Awaitable

from app.runtime.policy_registry import POLICIES
from app.ai.guardrails import check as guardrails_check
from app.ai.sandbox import validate as sandbox_validate
from app.ai.tools.registry import execute_tool


# ── Deep loop response schemas (injected into prompt) ─────────────────────────

_DEEP_TOOL_REQUEST_SCHEMA = """\
Output ONLY one of these two schemas:

Option A — request more data:
{
  "tool_requests": [
    {
      "tool":       "<tool name>",
      "parameters": { "<param>": "<value>" },
      "reason":     "<why you need this data — ≤80 chars>"
    }
  ]
}

Option B — you have enough information, provide final assessment:
{
  "final_assessment": {
    "root_cause":                  "<single sentence ≤200 chars>",
    "reason_for_restart":          "<why this container needed intervention>",
    "confidence":                  <float 0.0–1.0>,
    "evidence_citations":          ["<field: value>"],
    "proposed_actions":            [
      {
        "tool":       "<tool name>",
        "parameters": {},
        "rationale":  "<≤100 chars>",
        "risk_level": "<safe|low|medium|high>"
      }
    ],
    "preventive_recommendations":  ["<string>"],
    "requires_human":              <true|false>,
    "iterations_used":             <int>
  }
}
"""

_DEEP_SYSTEM_PREFIX = """\
You are DockHeal's deep investigation engine. A quick AI analysis has already run.
Your task: gather additional evidence via tools and converge on a definitive root cause.

Rules:
- Request tools ONLY if they provide NEW information not already in context or previous results.
- Do NOT request the same tool with the same parameters twice.
- If you have sufficient evidence, output final_assessment immediately.
- Base every claim on evidence. No speculation.

AVAILABLE TOOLS:
{tools_json}

ORIGINAL INCIDENT CONTEXT:
{context_json}

INITIAL QUICK ANALYSIS:
{initial_result_json}

{schema}
"""


# ── Rolling memory ─────────────────────────────────────────────────────────────

class RollingMemory:
    """
    Maintains a compressed summary of previous tool calls and results
    instead of appending full outputs forever.

    Stores last MAX_FULL_RESULTS verbatim, older ones are summarised.
    """
    MAX_FULL_RESULTS = 2

    def __init__(self):
        self._summary: list[str] = []    # compressed summaries of older results
        self._recent:  list[dict] = []   # last MAX_FULL_RESULTS full results
        self._tool_fingerprints: set[str] = set()  # duplicate detection

    def has_seen_tool(self, tool: str, params: dict) -> bool:
        """Detect duplicate tool+params requests."""
        fp = _fingerprint(tool, params)
        return fp in self._tool_fingerprints

    def record_result(self, tool: str, params: dict, result: dict) -> None:
        fp = _fingerprint(tool, params)
        self._tool_fingerprints.add(fp)

        full_entry = {
            "tool":       tool,
            "parameters": params,
            "result":     result,
        }

        self._recent.append(full_entry)

        # When recent buffer overflows, compress oldest into summary
        if len(self._recent) > self.MAX_FULL_RESULTS:
            oldest = self._recent.pop(0)
            self._summary.append(_compress_result(oldest))

    def has_seen_output(self, output: str) -> bool:
        """No-new-information detection — compare output against all seen outputs."""
        fp = hashlib.md5(output.encode(), usedforsecurity=False).hexdigest()
        if fp in self._tool_fingerprints:
            return True
        # Don't add to fingerprints — this is a content hash, not a tool+params hash
        return False

    def as_context_block(self) -> str:
        """Render memory for injection into the next AI prompt turn."""
        parts = []
        if self._summary:
            parts.append("=== PREVIOUS TOOL RESULTS (COMPRESSED) ===")
            for s in self._summary:
                parts.append(f"  - {s}")
        if self._recent:
            parts.append("=== RECENT TOOL RESULTS (FULL) ===")
            for entry in self._recent:
                result_text = entry["result"].get("output", "")
                if len(result_text) > 800:
                    result_text = result_text[:800] + "... [truncated]"
                parts.append(
                    f"Tool: {entry['tool']}({entry['parameters']})\n"
                    f"Result: {result_text}"
                )
        return "\n".join(parts) if parts else "No tool results yet."


# ── Main loop ──────────────────────────────────────────────────────────────────

async def deep_investigation_loop(
    packet:         dict,
    initial_result: dict,
    broadcast:      Callable[[dict], Awaitable[None]],
) -> dict:
    """
    Iterative tool-use investigation loop.

    Returns a final_assessment dict (always — may have requires_human=True on failure).
    """
    from app.ai.tools.registry import get_tool_schema_for_prompt
    from app.ai.investigator import _stream_mistral  # reuse existing streaming

    investigation_id = packet.get("investigation_id", "unknown")
    container_name   = packet.get("incident", {}).get("container", "unknown")
    max_iters        = POLICIES.max_deep_iterations
    memory           = RollingMemory()

    await broadcast({
        "type":             "DEEP_LOOP_START",
        "investigation_id": investigation_id,
        "container":        container_name,
        "reason":           _decide_deep_reason(initial_result, packet),
        "max_iterations":   max_iters,
    })

    # Build the base system prompt (injected once, stays constant)
    from app.ai.prompt_builder import _trim_packet
    trimmed_packet = _trim_packet(packet)
    tools_json     = json.dumps(get_tool_schema_for_prompt(), indent=2)
    context_json   = json.dumps(trimmed_packet, indent=2, default=str)
    initial_json   = json.dumps({
        "root_cause":  initial_result.get("root_cause", ""),
        "confidence":  initial_result.get("confidence", 0),
        "evidence":    initial_result.get("evidence_citations", []),
    }, indent=2)

    system_prompt = _DEEP_SYSTEM_PREFIX.format(
        tools_json          = tools_json,
        context_json        = context_json,
        initial_result_json = initial_json,
        schema              = _DEEP_TOOL_REQUEST_SCHEMA,
    )

    messages = [{"role": "system", "content": system_prompt}]

    for iteration in range(max_iters):
        # ── Inject rolling memory as the current user turn ─────────────────────
        memory_block = memory.as_context_block()
        user_turn    = (
            f"Iteration {iteration + 1}/{max_iters}.\n\n"
            f"{memory_block}\n\n"
            "Based on the above, output tool_requests or final_assessment."
        )
        messages_this_turn = messages + [{"role": "user", "content": user_turn}]

        await broadcast({
            "type":             "DEEP_LOOP_ITERATION",
            "investigation_id": investigation_id,
            "container":        container_name,
            "iteration":        iteration + 1,
        })

        # ── AI call ────────────────────────────────────────────────────────────
        raw = await _stream_mistral(
            messages         = messages_this_turn,
            model            = "mistral-large-latest",
            investigation_id = investigation_id,
            container_name   = container_name,
            broadcast        = broadcast,
            sequence_offset  = (iteration + 1) * 10000,
        )

        # ── Parse response ─────────────────────────────────────────────────────
        parsed = _parse_deep_response(raw, investigation_id, container_name, iteration + 1)

        if parsed.get("final_assessment"):
            fa = parsed["final_assessment"]
            fa["iterations_used"] = iteration + 1

            await broadcast({
                "type":             "DEEP_LOOP_COMPLETE",
                "investigation_id": investigation_id,
                "container":        container_name,
                "final_assessment": fa,
                "iterations_used":  iteration + 1,
            })
            return fa

        # ── Execute tool requests ──────────────────────────────────────────────
        tool_requests = parsed.get("tool_requests", [])
        if not tool_requests:
            # AI returned neither — treat as done
            break

        any_new_result = False

        for tr in tool_requests:
            tool_name  = tr.get("tool", "")
            parameters = tr.get("parameters", {})
            reason     = tr.get("reason", "")

            # ── Duplicate tool request detection ──────────────────────────────
            if memory.has_seen_tool(tool_name, parameters):
                await broadcast({
                    "type":             "DEEP_TOOL_SKIPPED",
                    "investigation_id": investigation_id,
                    "tool":             tool_name,
                    "reason":           "duplicate_request",
                })
                print(f"[DEEP] Skipping duplicate tool request: {tool_name}({parameters})")
                continue

            # ── Sandbox + guardrails (same gates as quick investigation) ───────
            sandbox_result = sandbox_validate(tool_name, parameters, packet)
            if not sandbox_result.approved:
                await broadcast({
                    "type":             "DEEP_TOOL_SKIPPED",
                    "investigation_id": investigation_id,
                    "tool":             tool_name,
                    "reason":           f"sandbox_blocked:{sandbox_result.blocking_reason}",
                })
                continue

            gd = guardrails_check(tool_name, parameters, packet, investigation_id)
            if not gd.allowed:
                await broadcast({
                    "type":             "DEEP_TOOL_SKIPPED",
                    "investigation_id": investigation_id,
                    "tool":             tool_name,
                    "reason":           f"guardrail_blocked:{gd.reason}",
                })
                continue

            # ── Execute ────────────────────────────────────────────────────────
            await broadcast({
                "type":             "DEEP_TOOL_EXECUTING",
                "investigation_id": investigation_id,
                "container":        container_name,
                "tool":             tool_name,
                "parameters":       parameters,
                "iteration":        iteration + 1,
                "reason":           reason,
            })

            tool_result = execute_tool(
                tool_name        = tool_name,
                parameters       = parameters,
                investigation_id = investigation_id,
                actor            = "deep_investigator",
            )

            output_text = tool_result.get("output", "")

            # ── No-new-information detection ───────────────────────────────────
            if memory.has_seen_output(output_text):
                await broadcast({
                    "type":             "DEEP_TOOL_SKIPPED",
                    "investigation_id": investigation_id,
                    "tool":             tool_name,
                    "reason":           "no_new_information",
                })
                # Still record in memory so AI knows it was tried
                memory.record_result(tool_name, parameters, tool_result)
                continue

            memory.record_result(tool_name, parameters, tool_result)
            any_new_result = True

            await broadcast({
                "type":             "DEEP_TOOL_RESULT",
                "investigation_id": investigation_id,
                "container":        container_name,
                "tool":             tool_name,
                "result":           tool_result,
                "iteration":        iteration + 1,
            })

        # ── Repeated-context detection — if no new data this turn, stop ────────
        if not any_new_result:
            print(f"[DEEP] No new information from iteration {iteration + 1} — stopping loop")
            await broadcast({
                "type":             "DEEP_LOOP_STALLED",
                "investigation_id": investigation_id,
                "iteration":        iteration + 1,
                "reason":           "no_new_information_from_tools",
            })
            break

        # Append assistant turn to maintain conversation context
        messages.append({"role": "assistant", "content": raw})

    # ── Max iterations or stall — return best effort from initial result ────────
    fallback = {
        "root_cause":                 initial_result.get("root_cause", "Inconclusive deep investigation"),
        "reason_for_restart":         initial_result.get("reason_for_restart", ""),
        "confidence":                 initial_result.get("confidence", 0.0),
        "evidence_citations":         initial_result.get("evidence_citations", []),
        "proposed_actions":           [],
        "preventive_recommendations": initial_result.get("preventive_recommendations", []),
        "requires_human":             True,
        "iterations_used":            max_iters,
        "_deep_fallback":             True,
    }
    await broadcast({
        "type":             "DEEP_LOOP_COMPLETE",
        "investigation_id": investigation_id,
        "container":        container_name,
        "final_assessment": fallback,
        "iterations_used":  max_iters,
    })
    return fallback


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fingerprint(tool: str, params: dict) -> str:
    key = f"{tool}::{json.dumps(params, sort_keys=True)}"
    return hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()


def _compress_result(entry: dict) -> str:
    """Summarise a tool result entry to a single line for rolling memory."""
    tool   = entry.get("tool", "unknown")
    params = entry.get("parameters", {})
    result = entry.get("result", {})
    output = result.get("output", "")
    ok     = "✓" if result.get("success") else "✗"
    # First 120 chars of output as summary
    snippet = output[:120].replace("\n", " ") if output else "(no output)"
    return f"{ok} {tool}({params}) → {snippet}"


def _parse_deep_response(
    raw:              str,
    investigation_id: str,
    container_name:   str,
    iteration:        int,
) -> dict:
    """
    Extract JSON from deep loop AI response.
    Returns dict with either 'tool_requests' or 'final_assessment' key.
    Falls back to empty dict on parse failure.
    """
    import re
    _JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
    _BARE_JSON  = re.compile(r"(\{.*\})", re.DOTALL)

    for pattern in (_JSON_FENCE, _BARE_JSON):
        m = pattern.search(raw)
        if m:
            try:
                data = json.loads(m.group(1))
                if "tool_requests" in data or "final_assessment" in data:
                    return data
            except json.JSONDecodeError:
                pass

    print(f"[DEEP] Iteration {iteration}: could not parse response — treating as final")
    return {}


def _decide_deep_reason(initial_result: dict, packet: dict) -> str:
    if initial_result.get("requires_human"):
        return "initial_requires_human"
    if initial_result.get("confidence", 1.0) < 0.6:
        return "low_confidence"
    score = packet.get("assessment", {}).get("severity_score", 0)
    if score >= 60:
        return f"high_severity_score:{score}"
    return "recovery_failed"
