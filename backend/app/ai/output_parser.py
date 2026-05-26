"""
Output parser — extracts and validates the StructuredAIOutput from raw Mistral response.

Strategy:
  1. Extract JSON block from raw text (handles markdown code fences).
  2. Validate against schema with Pydantic.
  3. Apply confidence threshold rules.
  4. On parse failure → 1 retry with error correction turn.
  5. On second failure → safe fallback output (requires_human=True, no actions).

Hard limits:
  - Max 2 Mistral API calls per investigation (1 initial + 1 retry).
  - No infinite loops.
  - Confidence < 0.5 → proposed_actions cleared regardless of what AI returned.
"""

import json
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ── Pydantic schema ────────────────────────────────────────────────────────────

class MCPToolCallSchema(BaseModel):
    tool:       str
    parameters: dict
    rationale:  str   = Field(max_length=150)
    risk_level: Literal["safe", "low", "medium", "high"]

    @field_validator("tool")
    @classmethod
    def tool_must_be_registered(cls, v: str) -> str:
        from app.ai.tools.registry import TOOL_REGISTRY
        if v not in TOOL_REGISTRY:
            raise ValueError(f"Tool '{v}' is not in TOOL_REGISTRY")
        return v

    @field_validator("parameters")
    @classmethod
    def validate_params_whitelist(cls, v: dict, info) -> dict:
        from app.ai.tools.decorator import TOOL_METADATA
        tool_name = info.data.get("tool", "")
        allowed   = TOOL_METADATA.get(tool_name, {}).get("allowed_params", [])
        if allowed:
            illegal = set(v.keys()) - set(allowed)
            if illegal:
                raise ValueError(f"Illegal params {illegal} for tool '{tool_name}'")
        return v


class RCAReportSchema(BaseModel):
    rca_version:          int = Field(default=1)
    incident_summary:     str = Field(default="", max_length=250)
    impact_assessment:    str = Field(default="", max_length=250)
    what_failed:          str = Field(default="", max_length=250)
    evidence_found:       str = Field(default="", max_length=250)
    why_it_happened:      str = Field(default="", max_length=250)
    contributing_factors: str = Field(default="", max_length=250)
    action_proposed:      str = Field(default="", max_length=250)
    recovery_status:      str = Field(default="", max_length=250)
    long_term_prevention: str = Field(default="", max_length=250)
    confidence_score:     float = Field(default=1.0)
    ai_reasoning_summary: str = Field(default="", max_length=250)


class StructuredAIOutput(BaseModel):
    investigation_id:   str
    container:          str
    reason_for_restart: str = Field(default="")
    root_cause:         str   = Field(default="", max_length=250)
    confidence:         float = Field(default=1.0, ge=0.0, le=1.0)
    evidence_citations: list[str] = Field(default_factory=list)
    proposed_actions:   list[MCPToolCallSchema] = Field(default_factory=list)
    preventive_recommendations: list[str] = Field(default_factory=list)
    requires_human:     bool = Field(default=True)
    rca_report:         RCAReportSchema | None = None

    @field_validator("proposed_actions")
    @classmethod
    def cap_actions(cls, v: list) -> list:
        return v[:3]   # AI may not propose more than 3 actions at once


# ── Extraction ────────────────────────────────────────────────────────────────

_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_BARE_JSON   = re.compile(r"(\{.*\})", re.DOTALL)


def _extract_json(text: str) -> tuple[dict | None, str | None]:
    """Pull the first JSON object from raw text. Returns (parsed_dict, error_msg)."""
    # Try fenced block first
    m = _JSON_FENCE.search(text)
    if m:
        try:
            return json.loads(m.group(1)), None
        except json.JSONDecodeError as de:
            return None, f"JSONDecodeError in fenced block: {de}"
    # Try bare JSON
    m = _BARE_JSON.search(text)
    if m:
        try:
            return json.loads(m.group(1)), None
        except json.JSONDecodeError as de:
            return None, f"JSONDecodeError in bare JSON: {de}"
    return None, "no JSON block found in response"


# ── Confidence enforcement ─────────────────────────────────────────────────────

def _apply_confidence_rules(output: StructuredAIOutput) -> StructuredAIOutput:
    """
    Enforce confidence threshold rules from the plan:
      >= 0.75 → proceed normally
      0.50-0.74 → proceed, frontend warned
      < 0.50 → force requires_human=True, clear proposed_actions
    """
    if output.confidence < 0.50:
        output = output.model_copy(update={
            "requires_human":  True,
            "proposed_actions": [],
        })
    return output


# ── Safe fallback ──────────────────────────────────────────────────────────────

def _fallback(investigation_id: str, container: str, reason: str) -> dict:
    """Used when parsing fails twice. Escalates to human with zero actions."""
    return {
        "investigation_id":  investigation_id,
        "container":         container,
        "reason_for_restart": "",
        "root_cause":        f"AI output could not be parsed — {reason}",
        "confidence":        0.0,
        "evidence_citations": [],
        "proposed_actions":  [],
        "preventive_recommendations": [],
        "requires_human":    True,
        "_parse_error":      reason,
    }


# ── Public API ─────────────────────────────────────────────────────────────────

def parse_output(
    raw_text: str,
    investigation_id: str,
    container: str,
) -> dict:
    """
    Parse and validate Mistral's raw response.

    Returns a validated StructuredAIOutput dict, or a fallback dict if
    parsing fails (already sets requires_human=True).

    Note: retry logic (building a corrective user turn and calling Mistral again)
    is handled in investigator.py. This function only parses — it does not call Mistral.
    """
    raw_json, err_msg = _extract_json(raw_text)

    if raw_json is None:
        return _fallback(investigation_id, container, err_msg or "no JSON block found in response")

    # Inject identifiers if AI omitted them (common)
    raw_json.setdefault("investigation_id", investigation_id)
    raw_json.setdefault("container", container)

    try:
        output = StructuredAIOutput.model_validate(raw_json)
        output = _apply_confidence_rules(output)
        return output.model_dump()
    except Exception as e:
        return _fallback(investigation_id, container, str(e))


def build_correction_turn(parse_error: str) -> str:
    """
    Build the corrective user turn for the retry call.
    Tells Mistral exactly what was wrong.
    """
    return (
        f"Your previous response could not be parsed. Error: {parse_error}\n"
        f"Output ONLY a valid JSON object matching the schema. No markdown, no prose."
    )
