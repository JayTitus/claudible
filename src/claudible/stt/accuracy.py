"""STT accuracy logging — tracks correction changes and latency."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from claudible.paths import STT_ACCURACY_LOG

log = logging.getLogger(__name__)


@dataclass
class CorrectionEntry:
    timestamp: float
    raw: str
    corrected: str
    latency_ms: float
    model: str
    was_changed: bool


def log_correction(
    raw: str,
    corrected: str,
    latency_ms: float,
    model: str,
    was_changed: bool,
) -> None:
    """Append a correction entry to the JSONL log."""
    entry = CorrectionEntry(
        timestamp=time.time(),
        raw=raw,
        corrected=corrected,
        latency_ms=round(latency_ms, 1),
        model=model,
        was_changed=was_changed,
    )
    try:
        STT_ACCURACY_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(STT_ACCURACY_LOG, "a") as f:
            f.write(json.dumps(asdict(entry)) + "\n")
    except OSError:
        log.debug("Failed to write accuracy log", exc_info=True)


def read_log(limit: int = 0) -> list[CorrectionEntry]:
    """Read correction entries from the log. Returns newest first."""
    if not STT_ACCURACY_LOG.exists():
        return []
    entries = []
    try:
        with open(STT_ACCURACY_LOG) as f:
            for line in f:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    entries.append(CorrectionEntry(**data))
    except (OSError, json.JSONDecodeError):
        log.debug("Failed to read accuracy log", exc_info=True)
    entries.reverse()
    if limit > 0:
        entries = entries[:limit]
    return entries


def compute_stats(entries: list[CorrectionEntry]) -> dict:
    """Compute accuracy statistics from log entries."""
    if not entries:
        return {
            "total": 0,
            "changed": 0,
            "change_rate": 0.0,
            "avg_latency_ms": 0.0,
            "p50_latency_ms": 0.0,
            "p95_latency_ms": 0.0,
        }

    total = len(entries)
    changed = sum(1 for e in entries if e.was_changed)
    latencies = sorted(e.latency_ms for e in entries)

    def percentile(data: list[float], p: float) -> float:
        idx = int(len(data) * p / 100)
        idx = min(idx, len(data) - 1)
        return data[idx]

    return {
        "total": total,
        "changed": changed,
        "change_rate": round(changed / total * 100, 1) if total else 0.0,
        "avg_latency_ms": round(sum(latencies) / total, 1),
        "p50_latency_ms": round(percentile(latencies, 50), 1),
        "p95_latency_ms": round(percentile(latencies, 95), 1),
    }


def clear_log() -> None:
    """Delete the accuracy log file."""
    if STT_ACCURACY_LOG.exists():
        STT_ACCURACY_LOG.unlink()
