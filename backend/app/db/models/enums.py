"""
DockHeal — shared enum definitions.

These Python enums map 1-to-1 with PostgreSQL native ENUM types created
by Alembic in the initial migration.  Import from here everywhere; never
hard-code string literals for state/type columns.
"""

import enum


# ---------------------------------------------------------------------------
# Severity / Priority
# ---------------------------------------------------------------------------

class SeverityLevel(str, enum.Enum):
    """Incident severity, mirroring PagerDuty-style P-levels."""
    P0 = "P0"   # Critical / service down
    P1 = "P1"   # High    / major degradation
    P2 = "P2"   # Medium  / partial degradation
    P3 = "P3"   # Low     / informational


# ---------------------------------------------------------------------------
# Investigation lifecycle
# ---------------------------------------------------------------------------

class LifecycleState(str, enum.Enum):
    """
    State machine for an Investigation record.

    New states:
        DETECTED, INVESTIGATING, RCA_IDENTIFIED, AWAITING_APPROVAL,
        RECOVERING, VALIDATING, MONITORING, RESOLVED, REJECTED, TIMED_OUT, ESCALATED
    """
    DETECTED          = "DETECTED"
    INVESTIGATING     = "INVESTIGATING"
    RCA_IDENTIFIED    = "RCA_IDENTIFIED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    RECOVERING        = "RECOVERING"
    VALIDATING        = "VALIDATING"
    MONITORING        = "MONITORING"
    RESOLVED          = "RESOLVED"
    REJECTED          = "REJECTED"
    TIMED_OUT         = "TIMED_OUT"
    ESCALATED         = "ESCALATED"
    PAUSED            = "PAUSED"


# ---------------------------------------------------------------------------
# Event source
# ---------------------------------------------------------------------------

class SourceType(str, enum.Enum):
    """Who/what generated a timeline event."""
    AI_AGENT = "AI_AGENT"
    HUMAN    = "HUMAN"
    SYSTEM   = "SYSTEM"


# ---------------------------------------------------------------------------
# Approval
# ---------------------------------------------------------------------------

class ActionType(str, enum.Enum):
    """Human decision on a proposed remediation."""
    APPROVE = "APPROVE"
    REJECT  = "REJECT"


# ---------------------------------------------------------------------------
# Recovery execution
# ---------------------------------------------------------------------------

class ExecutionStatus(str, enum.Enum):
    """Status of a recovery action execution."""
    PENDING     = "PENDING"
    RUNNING     = "RUNNING"
    SUCCESS     = "SUCCESS"
    FAILED      = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


# ---------------------------------------------------------------------------
# Container health
# ---------------------------------------------------------------------------

class ContainerStatus(str, enum.Enum):
    """Docker-reported container lifecycle status."""
    RUNNING    = "running"
    STOPPED    = "stopped"
    EXITED     = "exited"
    PAUSED     = "paused"
    RESTARTING = "restarting"
    DEAD       = "dead"
    CREATED    = "created"
    UNKNOWN    = "unknown"


class HealthStatus(str, enum.Enum):
    """Docker HEALTHCHECK result."""
    HEALTHY   = "healthy"
    UNHEALTHY = "unhealthy"
    STARTING  = "starting"
    NONE      = "none"


# ---------------------------------------------------------------------------
# Recovery classification
# ---------------------------------------------------------------------------

class RecoveryStatus(str, enum.Enum):
    """
    Characterises how permanent the applied fix is.

    * TEMPORARY   — workaround applied (e.g. restart); root cause not fixed
    * PERMANENT   — root cause eliminated; no further action expected
    * PARTIAL     — fix applied but risk of recurrence remains
    * UNKNOWN     — not yet determined
    """
    TEMPORARY = "TEMPORARY"
    PERMANENT = "PERMANENT"
    PARTIAL   = "PARTIAL"
    UNKNOWN   = "UNKNOWN"


# ---------------------------------------------------------------------------
# Sandbox
# ---------------------------------------------------------------------------

class SandboxStatus(str, enum.Enum):
    """Lifecycle of a sandbox investigation environment."""
    PENDING   = "PENDING"
    RUNNING   = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED    = "FAILED"
    CLEANED   = "CLEANED"


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

class NotificationStatus(str, enum.Enum):
    """
    Delivery status of an outbound notification.

    * PENDING    — queued, not yet sent
    * SENT       — successfully delivered to the channel
    * FAILED     — delivery attempt failed (retries may follow)
    * SUPPRESSED — intentionally not sent (e.g. duplicate, do-not-disturb)
    """
    PENDING    = "PENDING"
    SENT       = "SENT"
    FAILED     = "FAILED"
    SUPPRESSED = "SUPPRESSED"
