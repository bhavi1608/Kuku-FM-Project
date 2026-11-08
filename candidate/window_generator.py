
"""Generate diverse, timestamp-grounded promo candidates."""
from __future__ import annotations

from typing import Any

MIN_SECONDS = 20.0
MAX_SECONDS = 60.0


def _event_importance(event: dict[str, Any]) -> float:
    """Estimate whether an event may contribute to a compelling promo."""
    kind = str(event.get("event_type", "")).upper()
    content = str(event.get("content", "")).lower()
    emotion = str(
        event.get("emotion", event.get("tone", ""))
    ).lower()

    score = 1.0

    # Give meaningful screenplay events a base priority.
    if "DIALOGUE" in kind or "SPEECH" in kind:
        score += 1.5
    elif "ACTION" in kind:
        score += 1.0
    elif "SOUND" in kind:
        score += 0.5
    elif "CAMERA" in kind:
        score += 0.2

    # Dramatic language is useful, but should not dominate selection.
    dramatic_terms = (
        "betray", "truth", "secret", "kill", "die", "marry",
        "leave", "love", "please", "promise", "threat",
        "never", "why", "no", "help", "stop", "wait",
        "revenge", "sorry", "choose", "believe"
    )

    if any(term in content for term in dramatic_terms):
        score += 0.6

    # Use emotional metadata when it exists.
    emotional_terms = (
        "angry", "fear", "sad", "cry", "shock",
        "surprise", "happy", "desperate", "tense"
    )

    if any(term in emotion for term in emotional_terms):
        score += 0.7

    return score


def _overlap_ratio(a: dict[str, Any], b: dict[str, Any]) -> float:
    """Calculate temporal intersection over union for two candidates."""
    intersection = max(
        0.0,
        min(a["end_seconds"], b["end_seconds"])
        - max(a["start_seconds"], b["start_seconds"])
    )

    union = max(a["end_seconds"], b["end_seconds"]) - min(
        a["start_seconds"], b["start_seconds"]
    )

    return intersection / union if union > 0 else 0.0


def _format_time(seconds: float) -> str:
    minutes = int(seconds // 60)
    remainder = seconds - minutes * 60
    return f"{minutes:02d}:{remainder:05.2f}"


def generate_candidates(
    parsed: dict[str, Any],
    max_per_episode: int = 160,
    overlap_threshold: float = 0.72,
) -> list[dict[str, Any]]:
    """
    Generate event-aligned 20–60 second candidates.

    Improvements:
    - Considers all valid event-boundary intervals.
    - Uses multiple event types and emotional metadata.
    - Avoids keeping many near-identical overlapping windows.
    - Preserves candidates from different scenes.
    - Applies the candidate limit across the whole episode.
    """

    all_candidates = []

    for episode in parsed.get("episodes", []):
        ep_id = episode["episode_id"]
        episode_candidates = []

        for scene in episode.get("scenes", []):
            events = scene.get("events", [])

            if not events:
                continue

            boundaries = sorted({
                round(float(event["start_seconds"]), 2)
                for event in events
            } | {
                round(float(event["end_seconds"]), 2)
                for event in events
            })

            for i, start in enumerate(boundaries):
                for end in boundaries[i + 1:]:
                    duration = round(end - start, 2)

                    if duration < MIN_SECONDS:
                        continue

                    if duration > MAX_SECONDS:
                        break

                    contained = [
                        event for event in events
                        if float(event["end_seconds"]) > start
                        and float(event["start_seconds"]) < end
                    ]

                    textual = [
                        event for event in contained
                        if str(event.get("content", "")).strip()
                    ]

                    if not textual:
                        continue

                    # A candidate should contain meaningful screenplay content.
                    priority = sum(
                        _event_importance(event) for event in textual
                    )

                    # Reward a sequence containing different event types.
                    event_types = {
                        str(event.get("event_type", "")).upper()
                        for event in textual
                    }
                    priority += 0.4 * len(event_types)

                    # Prefer a meaningful ending rather than a window
                    # that simply stops in the middle of an event.
                    ending_events = [
                        event for event in textual
                        if abs(float(event["end_seconds"]) - end) <= 2.0
                        or abs(float(event["start_seconds"]) - end) <= 2.0
                    ]

                    if ending_events:
                        priority += 1.0

                    # Prefer windows with a meaningful opening event.
                    opening_events = [
                        event for event in textual
                        if abs(float(event["start_seconds"]) - start) <= 3.0
                    ]

                    if opening_events:
                        priority += 0.8

                    priority += 0.10 * len(textual)

                    episode_candidates.append({
                        "candidate_id": "",
                        "episode_id": ep_id,
                        "scene_id": scene["scene_id"],
                        "start_seconds": start,
                        "end_seconds": end,
                        "start_time": _format_time(start),
                        "end_time": _format_time(end),
                        "duration_seconds": duration,
                        "event_ids": [
                            event["event_id"] for event in contained
                        ],
                        "event_excerpt": [
                            {
                                "event_id": event["event_id"],
                                "event_type": event["event_type"],
                                "start_time": event["start_time"],
                                "end_time": event["end_time"],
                                "content": str(
                                    event.get("content", "")
                                )[:500],
                            }
                            for event in textual[:30]
                        ],
                        "heuristic_priority": round(priority, 3),
                    })

        # First, rank candidates by heuristic priority.
        episode_candidates.sort(
            key=lambda candidate: candidate["heuristic_priority"],
            reverse=True,
        )

        # Then remove near-identical overlapping windows.
        selected = []

        for candidate in episode_candidates:
            duplicate = any(
                _overlap_ratio(candidate, existing) >= overlap_threshold
                and candidate["scene_id"] == existing["scene_id"]
                for existing in selected
            )

            if not duplicate:
                selected.append(candidate)

            if len(selected) >= max_per_episode:
                break

        all_candidates.extend(selected)

    # Stable IDs after all episode-level filtering.
    for index, candidate in enumerate(all_candidates, start=1):
        candidate["candidate_id"] = f"C{index:06d}"

    return all_candidates
