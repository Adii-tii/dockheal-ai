"""
Prompt builder — token-budget-aware system prompt assembly.

Builds the Mistral system message from an OperationalContext packet.
Enforces strict budget so the prompt never exceeds ~3000 tokens.

Priority order when trimming (least → most important):
  1. logs.raw_tail           (first to drop — verbose, low signal density)
  2. dependency_context.peer_summaries (partial trim)
  3. recent_events.timeline  (trim to 10 events)
  4. logs.signals            (kept — pre-classified, high signal)
  5. container_state, metrics_snapshot, assessment (never trimmed)

The AI is told to cite specific packet fields in every claim.
"Think step by step" is NOT used — evidence citation is mandatory.
"""

import json

from app.ai.tools.registry import get_tool_schema_for_prompt

# Approximate characters per token for rough budget estimation
_CHARS_PER_TOKEN = 4
_TOKEN_BUDGET    = 3000
_CHAR_BUDGET     = _TOKEN_BUDGET * _CHARS_PER_TOKEN   # 12 000 chars


# ── Output schema injected literally into the prompt ───────────────────────────
_OUTPUT_SCHEMA = """
{
  "investigation_id": "<string — copy from context>",
  "container":        "<string — container name>",
  "rca_report": {
      "rca_version": 1,
      "incident_summary": "<string — max 120 chars>",
      "impact_assessment": "<string — max 120 chars>",
      "what_failed": "<string — max 120 chars>",
      "evidence_found": "<string — max 150 chars>",
      "why_it_happened": "<string — max 150 chars>",
      "contributing_factors": "<string — max 120 chars>",
      "action_proposed": "<string — max 120 chars>",
      "recovery_status": "<string — max 120 chars>",
      "long_term_prevention": "<string — max 150 chars>",
      "confidence_score": <float between 0.0 and 1.0>,
      "ai_reasoning_summary": "<string — max 150 chars>"
  },
  "proposed_actions": [
    {
      "tool":        "<tool name from available_tools>",
      "parameters":  { "<param>": "<value>" },
      "rationale":   "<string — max 100 chars>",
      "risk_level":  "<safe|low|medium|high>"
    }
  ],
  "requires_human": <true|false>
}
"""

_SYSTEM_TEMPLATE = """\
You are DockHeal's diagnostic engine. Your ONLY function is Docker container incident Root Cause Analysis (RCA).

═══ ROLE CONSTRAINTS ═══
- Base EVERY claim on the operational context below. Cite the specific field name in your evidence_found block.
- Do NOT speculate about causes absent from the telemetry.
- Do NOT suggest actions for tools not listed in available_tools.
- Always populate long_term_prevention, even if recovery succeeded.
- If confidence_score < 0.5: set requires_human=true, set proposed_actions=[].
- Set rca_version to 1 for initial analysis. If this is a re-evaluation or deep loop, increment it if provided in context.
- Output ONLY the JSON schema. Zero prose outside the JSON block.

═══ AVAILABLE TOOLS ═══
{tools_json}

═══ OPERATIONAL CONTEXT ═══
{context_json}

═══ OUTPUT SCHEMA (strict — output only this JSON, nothing else) ═══
{schema}
"""


def _trim_packet(packet: dict) -> dict:
    """
    Return a copy of the packet trimmed to fit within the character budget.
    Removes/truncates least-important fields first.
    """
    import copy
    p = copy.deepcopy(packet)

    # Remove fields the AI must not see
    p.pop("schema_version", None)
    p.pop("generated_at", None)
    # Remove env_vars entirely from prompt context
    if "container_state" in p:
        p["container_state"].pop("env_vars", None)

    # Trim raw_tail first (biggest, lowest density)
    if "logs" in p:
        p["logs"].pop("raw_tail", None)

    # Trim event timeline to 10 events
    if "recent_events" in p and "timeline" in p["recent_events"]:
        p["recent_events"]["timeline"] = p["recent_events"]["timeline"][:10]

    # Trim peer summaries to 5
    if "dependency_context" in p and "peer_summaries" in p["dependency_context"]:
        p["dependency_context"]["peer_summaries"] = p["dependency_context"]["peer_summaries"][:5]

    # If still over budget, trim error signals
    context_str = json.dumps(p)
    if len(context_str) > _CHAR_BUDGET:
        if "logs" in p and "signals" in p["logs"]:
            sigs = p["logs"]["signals"]
            sigs["errors"]   = sigs.get("errors", [])[:5]
            sigs["warnings"] = sigs.get("warnings", [])[:3]

    return p


def build_system_prompt(packet: dict) -> str:
    """
    Build the Mistral system message from an OperationalContext packet.

    Returns:
        A string ready to be used as the system message.
    """
    trimmed   = _trim_packet(packet)
    tools     = get_tool_schema_for_prompt()

    context_json = json.dumps(trimmed, indent=2, default=str)
    tools_json   = json.dumps(tools, indent=2)

    return _SYSTEM_TEMPLATE.format(
        tools_json   = tools_json,
        context_json = context_json,
        schema       = _OUTPUT_SCHEMA,
    )


def build_user_message(container_name: str) -> str:
    """Single user turn — brief, directive."""
    return f'Diagnose the incident for container: "{container_name}". Output the JSON schema.'
