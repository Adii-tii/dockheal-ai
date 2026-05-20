"""
Log collector — fetches recent stdout/stderr lines from a container
and classifies them into error signals for the AI context packet.

Design decisions:
- Tail last 100 lines (configurable) to avoid token explosion.
- Classify lines into: errors, warnings, stack_traces, crash_signals.
- Returns both raw_tail (for AI to read literally) and signals (structured).
"""

import re
import docker

try:
    client = docker.from_env()
except Exception as e:
    print(f"[LOG_COLLECTOR] Docker unavailable: {e}")
    client = None

# ── Pattern catalogue ──────────────────────────────────────────────────────────
_ERROR_PATTERNS = re.compile(
    r"(error|exception|fatal|critical|panic|traceback|oom|killed|segfault|"
    r"connection refused|no such file|permission denied|timeout|abort)",
    re.IGNORECASE,
)
_WARN_PATTERNS = re.compile(
    r"(warn(?:ing)?|deprecated|retry|retrying|reconnect|slow|degraded)",
    re.IGNORECASE,
)
_STACK_PATTERNS = re.compile(
    r"(Traceback|at\s+[\w\.]+\([\w\.]+:\d+\)|goroutine \d+|#\d+\s+0x)",
    re.IGNORECASE,
)
_CRASH_SIGNALS = re.compile(
    r"(exited with code [^0]\d*|signal: killed|OOMKilled|out of memory)",
    re.IGNORECASE,
)


def _classify(lines: list[str]) -> dict:
    errors, warnings, stack_frames, crash_signals = [], [], [], []

    for line in lines:
        if _CRASH_SIGNALS.search(line):
            crash_signals.append(line.strip())
        if _STACK_PATTERNS.search(line):
            stack_frames.append(line.strip())
        if _ERROR_PATTERNS.search(line):
            errors.append(line.strip())
        elif _WARN_PATTERNS.search(line):
            warnings.append(line.strip())

    return {
        "errors":        errors[:20],       # cap to avoid token overload
        "warnings":      warnings[:10],
        "stack_traces":  stack_frames[:10],
        "crash_signals": crash_signals[:5],
    }


def collect_logs(container_name: str, tail: int = 100) -> dict:
    """
    Returns:
        raw_tail       – last `tail` log lines as a list of strings
        signals        – classified error/warn/stack/crash entries
        log_available  – False if container not found or logs inaccessible
    """
    if not client:
        return {"log_available": False, "raw_tail": [], "signals": {}}

    try:
        container = client.containers.get(container_name)
        raw: bytes = container.logs(tail=tail, timestamps=True)
        lines = raw.decode("utf-8", errors="replace").splitlines()

        return {
            "log_available": True,
            "raw_tail": lines,
            "signals": _classify(lines),
        }

    except docker.errors.NotFound:
        return {"log_available": False, "raw_tail": [], "signals": {}}
    except Exception as e:
        return {
            "log_available": False,
            "raw_tail": [],
            "signals": {},
            "error": str(e),
        }
