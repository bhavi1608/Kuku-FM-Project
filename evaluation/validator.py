"""Deterministic checks for LLM-evaluated continuous promo candidates."""
from __future__ import annotations
from typing import Any

def validate_promo(candidate: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "duration_valid": 20 <= candidate["duration_seconds"] <= 60,
        "timestamps_valid": candidate["end_seconds"] > candidate["start_seconds"],
        "source_grounded": bool(candidate.get("event_ids")),
        "hook_score_valid": 0 <= evaluation["hook_strength"] <= 10,
    }
    return {
        "valid": all(checks.values()),
        "checks": checks,
        "errors": [name for name, passed in checks.items() if not passed],
        "warnings": [],
    }
