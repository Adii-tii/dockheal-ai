import time
import threading
import asyncio

from app.services.health_engine import detect_incidents
from app.services.recovery import attempt_deterministic_restart
from app.runtime.state import (
    active_incidents,
    manually_stopped,
    context_store,
    investigation_states,
    get_investigation_lock,
    remediation_timestamps,
    COOLDOWN_SECONDS,
)
from app.web_sockets.manager import manager
from app.context.aggregator import build_investigation_packet
from app.ai.investigator import investigate


def _should_skip_investigation(container_name: str, investigation_id: str) -> tuple[bool, str]:
    """
    Returns (True, reason) if this investigation should be skipped.
    Enforces: duplicate prevention, cooldown, active investigation guard.
    """
    from datetime import datetime, timezone

    # Already being investigated right now
    for inv_id, state_data in investigation_states.items():
        if (state_data.get("container") == container_name
                and state_data.get("state") in ("INVESTIGATING", "VALIDATING", "EXECUTING")):
            return True, f"already in state {state_data['state']}"

    # Cooldown window
    last = remediation_timestamps.get(container_name)
    if last:
        age = (datetime.now(timezone.utc) - last).total_seconds()
        if age < COOLDOWN_SECONDS:
            return True, f"cooldown active ({int(COOLDOWN_SECONDS - age)}s remaining)"

    return False, ""





def start_monitor_loop():
    try:
        loop_to_use = asyncio.get_event_loop()
    except RuntimeError:
        loop_to_use = asyncio.new_event_loop()
        asyncio.set_event_loop(loop_to_use)

    def loop(event_loop):
        while True:
            incidents = detect_incidents()
            for incident in incidents:
                container_name = incident["container"]

                if container_name in manually_stopped:
                    continue

                # Per-container lock — prevents race conditions
                lock = get_investigation_lock(container_name)
                if not lock.acquire(blocking=False):
                    print(f"[MONITOR] Lock held for {container_name} — skipping")
                    continue

                try:
                    _handle_incident(incident, container_name, event_loop)
                finally:
                    lock.release()

            time.sleep(30)

    thread = threading.Thread(target=loop, args=(loop_to_use,), daemon=True)
    thread.start()


def _handle_incident(incident: dict, container_name: str, event_loop):
    # ── Build investigation packet ─────────────────────────────────────────────
    print(f"[CONTEXT] Building packet for {container_name}")
    try:
        packet = build_investigation_packet(container_name, incident)
        context_store[container_name] = packet
        investigation_id = packet["investigation_id"]
        score = packet["assessment"]["severity_score"]
        print(f"[CONTEXT] Ready — score={score}, id={investigation_id}")
    except Exception as e:
        print(f"[CONTEXT] Failed for {container_name}: {e}")
        return

    # ── Duplicate / cooldown guard ─────────────────────────────────────────────
    skip, reason = _should_skip_investigation(container_name, investigation_id)
    if skip:
        print(f"[MONITOR] Skipping {container_name}: {reason}")
        return

    # ── Mark as DETECTED ──────────────────────────────────────────────────────
    investigation_states[investigation_id] = {
        "state":     "DETECTED",
        "container": container_name,
    }

    # ── Broadcast INCIDENT (with context) ─────────────────────────────────────
    if event_loop and event_loop.is_running():
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({
                "type":             "INCIDENT",
                "incident":         incident,
                "context":          packet,
                "investigation_id": investigation_id,
            }),
            event_loop,
        )

    # ── Deterministic Recovery Attempt ─────────────────────────────────────────
    print(f"[MONITOR] Attempting recovery for {container_name} (score={score})")
    recovery = attempt_deterministic_restart(container_name, incident, investigation_id)
    
    if event_loop and event_loop.is_running():
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({
                "type":             "RECOVERY_ATTEMPT",
                "container":        container_name,
                "result":           recovery.to_dict(),
                "investigation_id": investigation_id,
            }),
            event_loop,
        )

    # Attach restart result to packet so AI knows what happened
    packet["recovery_attempt"] = recovery.to_dict()

    if recovery.success:
        active_incidents.discard(container_name)
    else:
        active_incidents.add(container_name)

    # ── ALWAYS run AI investigation in parallel ────────────────────────────────
    print(f"[AI] Invoking AI investigation for {container_name} (score={score})")
    
    if event_loop and event_loop.is_running():
        async def run_ai():
            async def broadcast(msg: dict):
                await manager.broadcast(msg)
            try:
                await investigate(packet, broadcast)
            except Exception as e:
                print(f"[AI] Investigation failed for {container_name}: {e}")
                investigation_states[investigation_id]["state"] = "ESCALATED"

        asyncio.run_coroutine_threadsafe(run_ai(), event_loop)