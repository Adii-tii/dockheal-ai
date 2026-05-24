"""
@mcp_tool decorator — parameter whitelist, audit logging, exception wrapping.

Every tool function must be decorated with @mcp_tool before registration.
The decorator enforces:
  1. Parameter whitelist — only allowed_params keys accepted from AI calls.
  2. Audit entry written BEFORE execution (so we log attempted calls even if they fail).
  3. Execution timing recorded in the audit entry.
  4. All exceptions caught — tools never throw, they return ToolResult(success=False).
"""

import time
import functools
from datetime import datetime, timezone
from typing import Callable, Literal

from app.runtime.state import append_audit


# ── ToolResult schema ──────────────────────────────────────────────────────────
class ToolResult:
    def __init__(
        self,
        success: bool,
        output: str,
        side_effects: list[str] | None = None,
    ):
        self.success = success
        self.output = output
        self.side_effects = side_effects or []

    def to_dict(self) -> dict:
        return {
            "success":      self.success,
            "output":       self.output,
            "side_effects": self.side_effects,
        }


# ── Tool metadata registry (populated by decorator) ───────────────────────────
TOOL_METADATA: dict[str, dict] = {}


def log_failed_tool(name: str, parameters: dict, investigation_id: str, actor: str, error_msg: str) -> None:
    import os
    import json
    from datetime import datetime, timezone
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    log_dir = os.path.join(base_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    file_path = os.path.join(log_dir, "dead_letter_tools.log")
    
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "investigation_id": investigation_id,
        "actor": actor,
        "tool": name,
        "parameters": parameters,
        "error": error_msg
    }
    try:
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        import sys
        print(f"[DEAD_LETTER] Failed to write tool dead letter: {e}", file=sys.stderr)


def mcp_tool(
    name: str,
    description: str,
    allowed_params: list[str],
    risk_level: Literal["safe", "low", "medium", "high"],
    phase: int = 1,   # phase=2 tools are registered but hard-blocked by guardrails
):
    """
    Decorator factory for MCP tools.

    Args:
        name:           Unique tool name (must match TOOL_REGISTRY key).
        description:    Short description used in prompt schema injection.
        allowed_params: Whitelist of parameter names the AI may pass.
        risk_level:     "safe" | "low" | "medium" | "high"
        phase:          1 = auto-execute allowed, 2 = hard-blocked in Phase 1
    """
    def decorator(fn: Callable) -> Callable:
        # Register metadata
        TOOL_METADATA[name] = {
            "name":           name,
            "description":    description,
            "allowed_params": allowed_params,
            "risk_level":     risk_level,
            "phase":          phase,
        }

        @functools.wraps(fn)
        def wrapper(
            investigation_id: str = "manual",
            actor: str = "ai_auto",
            **kwargs
        ) -> dict:
            # ── Validate parameters ────────────────────────────────────────────
            illegal = set(kwargs.keys()) - set(allowed_params)
            if illegal:
                result = ToolResult(
                    success=False,
                    output=f"Rejected: illegal parameters {illegal}. Allowed: {allowed_params}",
                )
                log_failed_tool(name, kwargs, investigation_id, actor, result.output)
                return result.to_dict()

            # ── Audit: pre-execution entry ─────────────────────────────────────
            audit_entry: dict = {
                "ts":               datetime.now(timezone.utc).isoformat(),
                "investigation_id": investigation_id,
                "tool":             name,
                "parameters":       kwargs,
                "risk_level":       risk_level,
                "actor":            actor,
                "result":           None,    # filled after execution
                "duration_ms":      None,
            }
            append_audit(audit_entry)

            # ── Execute ────────────────────────────────────────────────────────
            start = time.perf_counter()
            import inspect
            sig = inspect.signature(fn)
            extra_args = {}
            if "investigation_id" in sig.parameters:
                extra_args["investigation_id"] = investigation_id
            if "actor" in sig.parameters:
                extra_args["actor"] = actor

            try:
                result: ToolResult = fn(**kwargs, **extra_args)
                if not result.success:
                    log_failed_tool(name, kwargs, investigation_id, actor, result.output)
            except Exception as e:
                error_msg = f"Tool raised exception: {e}"
                result = ToolResult(success=False, output=error_msg)
                log_failed_tool(name, kwargs, investigation_id, actor, error_msg)

            elapsed_ms = int((time.perf_counter() - start) * 1000)

            # ── Audit: update with result ──────────────────────────────────────
            audit_entry["result"]      = result.to_dict()
            audit_entry["duration_ms"] = elapsed_ms

            return result.to_dict()

        wrapper._mcp_name       = name
        wrapper._mcp_risk       = risk_level
        wrapper._mcp_phase      = phase
        wrapper._mcp_params     = allowed_params
        return wrapper

    return decorator
