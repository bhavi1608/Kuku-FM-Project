"""Parser for timestamped Kuku FM screenplay text files.

The parser preserves source text and overlapping event intervals. It does not
infer video content or merge simultaneous screenplay tracks.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

TIME_RE = re.compile(r"^\d{2}:\d{2}(?:\.\d+)?$")
EPISODE_RE = re.compile(r"^EPISODE NUMBER:\s*(.+?)\s*$", re.I)
LOGLINE_RE = re.compile(r"^EPISODE LOGLINE:\s*(.*?)\s*$", re.I)
CONTINUITY_RE = re.compile(r"^CONTINUITY NOTES:\s*(.*?)\s*$", re.I)
SCENE_RE = re.compile(r"^SCENE\s+(\d+)\s*$", re.I)
SCENE_HEADING_RE = re.compile(r"^SCENE HEADING:\s*(.*?)\s*$", re.I)
SCENE_START_RE = re.compile(r"^SCENE START:\s*(.*?)\s*$", re.I)
SCENE_END_RE = re.compile(r"^SCENE END:\s*(.*?)\s*$", re.I)
EVENT_HEADER_RE = re.compile(r"^\*\*(.+?)\*\*\s*$")
EVENT_TIME_RE = re.compile(
    r"^Start:\s*\((\d{2}:\d{2}(?:\.\d+)?)\)\s*\|\s*End:\s*\((\d{2}:\d{2}(?:\.\d+)?)\)\s*$",
    re.I,
)

def timestamp_to_seconds(value: str) -> float:
    """Convert MM:SS[.fraction] to seconds; reject malformed timestamps."""
    if not TIME_RE.fullmatch(value.strip()):
        raise ValueError(f"Invalid timestamp: {value!r}")
    minutes, seconds = value.strip().split(":")
    return int(minutes) * 60 + float(seconds)

def normalize_label(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).rstrip(":").strip()

def _clean_content(lines: list[str]) -> str:
    # Preserve dialogue punctuation and line breaks while removing outer blanks.
    return "\n".join(lines).strip()

def parse_screenplay(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()

    episode_number = None
    logline = ""
    continuity_notes = ""
    scenes: list[dict[str, Any]] = []
    current_scene: dict[str, Any] | None = None
    i = 0

    def finish_scene(scene: dict[str, Any] | None) -> None:
        if scene is None:
            return
        scene["events"].sort(key=lambda e: (e["start_seconds"], e["end_seconds"], e["event_id"]))

    while i < len(lines):
        line = lines[i].strip()

        m = EPISODE_RE.match(line)
        if m:
            episode_number = m.group(1).strip()
            i += 1
            continue
        m = LOGLINE_RE.match(line)
        if m:
            logline = m.group(1).strip()
            i += 1
            continue
        m = CONTINUITY_RE.match(line)
        if m:
            continuity_notes = m.group(1).strip()
            i += 1
            continue

        m = SCENE_RE.match(line)
        if m:
            finish_scene(current_scene)
            current_scene = {
                "scene_id": int(m.group(1)),
                "heading": None,
                "start_time": None,
                "end_time": None,
                "start_seconds": None,
                "end_seconds": None,
                "events": [],
            }
            scenes.append(current_scene)
            i += 1
            continue

        if current_scene is not None:
            for pattern, key in (
                (SCENE_HEADING_RE, "heading"),
                (SCENE_START_RE, "start_time"),
                (SCENE_END_RE, "end_time"),
            ):
                m = pattern.match(line)
                if m:
                    current_scene[key] = m.group(1).strip()
                    if key == "start_time":
                        current_scene["start_seconds"] = timestamp_to_seconds(m.group(1))
                    elif key == "end_time":
                        current_scene["end_seconds"] = timestamp_to_seconds(m.group(1))
                    break
            else:
                header = EVENT_HEADER_RE.match(line)
                if header:
                    event_label = normalize_label(header.group(1))
                    # An event is accepted only when its explicit Start/End line follows.
                    j = i + 1
                    while j < len(lines) and not lines[j].strip():
                        j += 1
                    if j < len(lines):
                        tm = EVENT_TIME_RE.match(lines[j].strip())
                    else:
                        tm = None
                    if tm:
                        start_time, end_time = tm.groups()
                        start_s = timestamp_to_seconds(start_time)
                        end_s = timestamp_to_seconds(end_time)
                        content_lines: list[str] = []
                        k = j + 1
                        while k < len(lines):
                            candidate = lines[k].strip()
                            if (EVENT_HEADER_RE.match(candidate)
                                or SCENE_RE.match(candidate)
                                or candidate == "--- SCRIPT END ---"):
                                break
                            # Metadata markers are not event content.
                            if candidate in ("--- SCRIPT START ---", "Actions and dialogue:"):
                                k += 1
                                continue
                            content_lines.append(lines[k])
                            k += 1
                        event = {
                            "event_id": f"E{len(current_scene['events']) + 1:03d}",
                            "event_type": event_label,
                            "start_time": start_time,
                            "end_time": end_time,
                            "start_seconds": start_s,
                            "end_seconds": end_s,
                            "duration_seconds": round(end_s - start_s, 3),
                            "content": _clean_content(content_lines),
                            "source_file": path.name,
                        }
                        current_scene["events"].append(event)
                        i = k
                        continue
        i += 1

    finish_scene(current_scene)

    # Validate scene intervals and event intervals without altering source values.
    warnings: list[str] = []
    errors: list[str] = []
    for scene in scenes:
        if scene["start_seconds"] is None or scene["end_seconds"] is None:
            errors.append(f"Scene {scene['scene_id']} is missing a start or end timestamp.")
        elif scene["end_seconds"] < scene["start_seconds"]:
            errors.append(f"Scene {scene['scene_id']} ends before it starts.")
        for event in scene["events"]:
            if event["end_seconds"] < event["start_seconds"]:
                errors.append(f"{event['event_id']} in scene {scene['scene_id']} ends before it starts.")
            if scene["start_seconds"] is not None and event["start_seconds"] < scene["start_seconds"] - 0.001:
                warnings.append(f"{event['event_id']} starts before its scene boundary.")
            if scene["end_seconds"] is not None and event["end_seconds"] > scene["end_seconds"] + 0.001:
                warnings.append(f"{event['event_id']} ends after its scene boundary.")

    if not episode_number:
        errors.append("Episode number was not found.")
    if not scenes:
        errors.append("No scenes were parsed.")

    return {
        "episode_id": episode_number,
        "source_file": path.name,
        "logline": logline,
        "continuity_notes": continuity_notes,
        "duration_seconds": max(
            (s["end_seconds"] for s in scenes if s["end_seconds"] is not None),
            default=0.0,
        ),
        "scene_count": len(scenes),
        "event_count": sum(len(s["events"]) for s in scenes),
        "scenes": scenes,
        "parse_validation": {
            "valid": not errors,
            "errors": errors,
            "warnings": warnings,
        },
    }

def parse_directory(input_dir: str | Path, output_path: str | Path | None = None) -> dict[str, Any]:
    input_dir = Path(input_dir)
    files = sorted(input_dir.glob("*.txt"))
    episodes = [parse_screenplay(p) for p in files]
    result = {
        "schema_version": "1.0.0",
        "input_directory": str(input_dir),
        "episode_count": len(episodes),
        "scene_count": sum(ep["scene_count"] for ep in episodes),
        "event_count": sum(ep["event_count"] for ep in episodes),
        "episodes": episodes,
        "run_validation": {
            "all_episodes_valid": all(ep["parse_validation"]["valid"] for ep in episodes),
            "episodes_with_errors": [
                ep["episode_id"] for ep in episodes if not ep["parse_validation"]["valid"]
            ],
        },
    }
    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Parse timestamped Kuku FM screenplay files.")
    ap.add_argument("--input", required=True, help="Directory containing .txt episode files")
    ap.add_argument("--output", default="data/parsed_episodes.json")
    args = ap.parse_args()
    parsed = parse_directory(args.input, args.output)
    print(f"Parsed {parsed['episode_count']} episodes, {parsed['scene_count']} scenes, "
          f"{parsed['event_count']} events.")
    print(f"All episodes valid: {parsed['run_validation']['all_episodes_valid']}")
    print(f"JSON written to: {args.output}")
