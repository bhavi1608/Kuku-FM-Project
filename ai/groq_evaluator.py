"""Groq-based qualitative promo evaluator.

Requires GROQ_API_KEY in the environment. The LLM scores candidate windows;
Python retains control of timestamps and validation.
"""
from __future__ import annotations
import json
import os
from typing import Any

from groq import Groq

DEFAULT_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

SYSTEM_PROMPT = """You are an expert short-form microdrama promo editor.
Evaluate only the supplied screenplay candidate. Do not invent dialogue, events,
characters, timestamps, or visual details. The candidate timestamps are fixed.
A promo's purpose is to make a viewer curious enough to start the series; it
does not need to explain the entire backstory. The opening should hook within
the first 3 seconds. The ending should create an unresolved question, reveal,
threat, twist, or consequential decision. Immediate comprehensibility means
the viewer can follow this moment, not understand the entire series.

Return ONLY valid JSON with these keys:
hook_strength, curiosity, immediate_comprehensibility, emotional_intensity,
narrative_progression, hook_explanation, cliffhanger_explanation,
curiosity_question, narrative_summary, why_it_works.
Each score must be a number from 0 to 10. Keep explanations concise.
"""

def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text[:-3]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Groq response did not contain a JSON object.")
    return json.loads(text[start:end + 1])

def evaluate_candidate(candidate: dict[str, Any], client: Groq | None = None,
                       model: str = DEFAULT_MODEL) -> dict[str, Any]:
    client = client or Groq(api_key=os.environ["GROQ_API_KEY"])
    user_payload = {
        "episode_id": candidate["episode_id"],
        "scene_id": candidate["scene_id"],
        "fixed_start_time": candidate["start_time"],
        "fixed_end_time": candidate["end_time"],
        "fixed_duration_seconds": candidate["duration_seconds"],
        "events": candidate["event_excerpt"],
        "instruction": "Evaluate this exact interval. Do not alter its boundaries."
    }
    completion = client.chat.completions.create(
        model=model,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
    )
    evaluation = _extract_json(completion.choices[0].message.content or "")
    required = [
        "hook_strength", "curiosity", "immediate_comprehensibility",
        "emotional_intensity", "narrative_progression",
    ]
    for key in required:
        value = float(evaluation[key])
        if not 0 <= value <= 10:
            raise ValueError(f"Invalid {key}: expected 0-10, got {value}")
        evaluation[key] = value
    return evaluation

def weighted_score(scores: dict[str, Any]) -> float:
    return round(
        0.25 * float(scores["hook_strength"])
        + 0.30 * float(scores["curiosity"])
        + 0.15 * float(scores["immediate_comprehensibility"])
        + 0.15 * float(scores["emotional_intensity"])
        + 0.15 * float(scores["narrative_progression"]),
        3,
    )
