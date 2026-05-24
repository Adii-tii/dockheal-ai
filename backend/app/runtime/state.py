# Containers intentionally stopped by users
manually_stopped: set = set()

# Active incidents to avoid duplicates
active_incidents: set = set()

# Most-recent investigation packet per container (keyed by name)
context_store: dict = {}

# ── Investigation lifecycle ────────────────────────────────────────────────────
# keyed by investigation_id → InvestigationState dict
investigation_states: dict = {}

# Active investigation asyncio Tasks (keyed by investigation_id → asyncio.Task)
active_tasks: dict = {}

# Keyed by investigation_id → "paused" | "stopped"
cancellation_reasons: dict = {}

# Approval state sync: keyed by investigation_id → asyncio.Event
approval_events: dict = {}

# Approval results: keyed by investigation_id → {"status": "approved" | "rejected", "user": str, "timestamp": str}
approval_results: dict = {}

# Per-container lock to prevent race conditions on concurrent incident triggers
# keyed by container_name → threading.Lock
import threading
investigation_locks: dict = {}

def get_investigation_lock(container_name: str) -> threading.Lock:
    """Get-or-create a per-container threading lock."""
    if container_name not in investigation_locks:
        investigation_locks[container_name] = threading.Lock()
    return investigation_locks[container_name]

# ── Remediation state ─────────────────────────────────────────────────────────
from datetime import datetime

# container_name → datetime of last executed remediation action
remediation_timestamps: dict[str, datetime] = {}

# container_name → number of remediation attempts in current incident window
remediation_retry_counts: dict[str, int] = {}

# Containers explicitly held by an operator (blocks all autonomous action)
operator_lock: set = set()

# ── Audit log ─────────────────────────────────────────────────────────────────
# In-memory, last 1000 entries. Future: persist to append-only file.
audit_log: list[dict] = []
MAX_AUDIT_LOG = 1000

def append_audit(entry: dict) -> None:
    """Append to audit log, evicting oldest if at capacity."""
    audit_log.append(entry)
    if len(audit_log) > MAX_AUDIT_LOG:
        audit_log.pop(0)

# ── Policy constants — delegated to PolicyRegistry ───────────────────────────
# Kept here as re-exports so existing import sites don't break.
from app.runtime.policy_registry import POLICIES
COOLDOWN_SECONDS    = POLICIES.cooldown_seconds
MAX_RETRIES         = POLICIES.max_retries
PACKET_MAX_AGE_SECS = POLICIES.packet_max_age_secs

# ── Worker status ─────────────────────────────────────────────────────────────
worker_statuses: dict[str, str] = {
    "api": "healthy",
    "monitor": "healthy",
    "ai_worker": "healthy",
    "notifications": "healthy",
}