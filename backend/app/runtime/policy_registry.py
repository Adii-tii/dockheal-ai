"""
PolicyRegistry — live, mutable runtime policy configuration.

Single source of truth for all guardrail thresholds.
All subsystems (guardrails, recovery, monitor loop) import POLICIES from here.
The /policies API endpoint reads from and writes to this object.

Deterministic severity overrides are also defined here so they
cannot be altered by AI hallucination.
"""

import os
from dataclasses import dataclass, field, asdict


@dataclass
class PolicyRegistry:
    # ── Cooldown / retry ─────────────────────────────────────────────────────────
    cooldown_seconds:    int  = 300    # min seconds between remediations on same container
    max_retries:         int  = 3      # hard-stop after this many attempts per window
    packet_max_age_secs: int  = 60     # reject stale context before non-safe tool exec

    # ── Blocked Tools ────────────────────────────────────────────────────────────
    blocked_tools:       list[str] = field(default_factory=list)

    # ── Severity gate (AI output is capped — AI cannot exceed this) ───────────────
    severity_gate:       int  = 80     # auto-escalate to human above this score

    # ── Deterministic severity overrides (cannot be owned by AI) ─────────────────
    # These are applied BEFORE AI is consulted. AI can only augment, not lower.
    oom_severity:             int  = 85   # OOMKilled always at least this score
    crash_loop_severity:      int  = 75   # frequent_dies always at least this score
    repeated_restart_severity: int = 60   # restart_count >= RESTART_CRIT always at least this

    # ── OOM guard ─────────────────────────────────────────────────────────────────
    oom_block_restart:   bool = True   # block restart when OOM is detected

    # ── Deep investigation loop ───────────────────────────────────────────────────
    max_deep_iterations: int  = 5

    # ── Recovery verification ─────────────────────────────────────────────────────
    recovery_poll_interval_secs: float = 2.0   # how often to poll post-restart
    recovery_timeout_secs:       int   = 30    # give up verifying after this long

    def load_from_env(self) -> "PolicyRegistry":
        """Override any field from environment variables (prefixed DOCKHEAL_)."""
        mapping = {
            "DOCKHEAL_COOLDOWN_SECONDS":             ("cooldown_seconds",             int),
            "DOCKHEAL_MAX_RETRIES":                  ("max_retries",                  int),
            "DOCKHEAL_PACKET_MAX_AGE_SECS":          ("packet_max_age_secs",          int),
            "DOCKHEAL_SEVERITY_GATE":                ("severity_gate",                int),
            "DOCKHEAL_OOM_SEVERITY":                 ("oom_severity",                 int),
            "DOCKHEAL_CRASH_LOOP_SEVERITY":          ("crash_loop_severity",          int),
            "DOCKHEAL_REPEATED_RESTART_SEVERITY":    ("repeated_restart_severity",    int),
            "DOCKHEAL_OOM_BLOCK_RESTART":            ("oom_block_restart",            bool),
            "DOCKHEAL_MAX_DEEP_ITERATIONS":          ("max_deep_iterations",          int),
            "DOCKHEAL_RECOVERY_POLL_INTERVAL_SECS":  ("recovery_poll_interval_secs",  float),
            "DOCKHEAL_RECOVERY_TIMEOUT_SECS":        ("recovery_timeout_secs",        int),
        }
        for env_key, (attr, cast) in mapping.items():
            val = os.getenv(env_key)
            if val is not None:
                try:
                    if cast is bool:
                        setattr(self, attr, val.lower() in ("1", "true", "yes"))
                    else:
                        setattr(self, attr, cast(val))
                except (ValueError, TypeError):
                    pass
        return self

    def update(self, **kwargs) -> None:
        """Update policy values at runtime (e.g. from a future settings API)."""
        for k, v in kwargs.items():
            if hasattr(self, k):
                orig_val = getattr(self, k)
                try:
                    if isinstance(orig_val, bool):
                        if isinstance(v, str):
                            setattr(self, k, v.lower() in ("true", "1", "yes", "on"))
                        else:
                            setattr(self, k, bool(v))
                    elif isinstance(orig_val, int):
                        setattr(self, k, int(v))
                    elif isinstance(orig_val, float):
                        setattr(self, k, float(v))
                    else:
                        setattr(self, k, v)
                except (ValueError, TypeError):
                    pass

    def as_dict(self) -> dict:
        return asdict(self)

    def apply_deterministic_severity(
        self,
        base_score: int,
        oom: bool,
        frequent_dies: bool,
        high_restart_count: bool,
    ) -> int:
        """
        Floor the severity score to deterministic minimums.

        AI may augment severity ABOVE these floors, but can never
        produce a score BELOW them for known-critical conditions.
        """
        floor = base_score
        if oom:
            floor = max(floor, self.oom_severity)
        if frequent_dies:
            floor = max(floor, self.crash_loop_severity)
        if high_restart_count:
            floor = max(floor, self.repeated_restart_severity)
        return min(floor, 100)


# ── Singleton ──────────────────────────────────────────────────────────────────
POLICIES = PolicyRegistry().load_from_env()
