#!/usr/bin/env python3
"""Machine-check a G3 narration ASS timeline against its subtitle layout contract.

Issue 026: long sentences silently wrapped past the contracted line budget (e.g. three
rendered lines under maxLines=2), and the ASS style fontsize could drift from the
contract. This validator estimates every dialogue's rendered line count from the ASS
script resolution, the style's own fontsize/margins, and a conservative character-width
model (full-width character = 1.0em, narrow character = 0.55em).
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path


NARROW_RATIO = 0.55
OVERRIDE_TAG = re.compile(r"\{[^}]*\}")
SRT_TIME = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})")


def fail(message: str) -> None:
    raise ValueError(message)


def srt_to_ms(hours, minutes, seconds, millis) -> int:
    return ((int(hours) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + int(millis)


def validate_srt_reference(path: Path, event_count: int) -> int:
    """The SRT delivery reference must be standard-padded (HH:MM:SS,mmm), monotonic and
    non-overlapping, and cue-for-cue with the approved ASS timeline. Guards the known
    failure of converting ASS centiseconds to SRT milliseconds without x10 scaling."""
    blocks = [b for b in re.split(r"\n\s*\n", path.read_text(encoding="utf-8-sig").strip()) if b.strip()]
    if not blocks:
        fail("srt reference has no cues")
    if len(blocks) != event_count:
        fail(f"srt cue count {len(blocks)} does not match ASS event count {event_count}")
    previous_end = 0
    for index, block in enumerate(blocks, 1):
        lines = block.splitlines()
        if len(lines) < 3:
            fail(f"srt cue {index} must be an index, a timestamp line, and text")
        match = SRT_TIME.fullmatch(lines[1].strip())
        if not match:
            fail(f"srt cue {index} timestamp line must be HH:MM:SS,mmm --> HH:MM:SS,mmm: {lines[1]!r}")
        start, end = srt_to_ms(*match.groups()[:4]), srt_to_ms(*match.groups()[4:])
        if end <= start:
            fail(f"srt cue {index} ends before it starts")
        if start < previous_end:
            fail(f"srt cue {index} overlaps or precedes the previous cue")
        if not "".join(lines[2:]).strip():
            fail(f"srt cue {index} has empty text")
        previous_end = end
    return len(blocks)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def char_units(ch: str) -> float:
    return 1.0 if unicodedata.east_asian_width(ch) in {"F", "W"} else NARROW_RATIO


def token_width(token: str, fontsize: float) -> float:
    return sum(char_units(ch) for ch in token) * fontsize


def wrap_line(line: str, fontsize: float, available: float) -> int:
    """Count the lines libass needs for one hard line, breaking at spaces and (for
    oversized CJK runs) at any character, conservatively."""
    space_width = NARROW_RATIO * fontsize
    pieces: list[str] = []
    for token in line.split(" "):
        if not token or token_width(token, fontsize) <= available:
            pieces.append(token)
            continue
        chunk = ""
        for ch in token:
            if chunk and token_width(chunk + ch, fontsize) > available:
                pieces.append(chunk)
                chunk = ch
            else:
                chunk += ch
        if chunk:
            pieces.append(chunk)
    lines, current = 1, 0.0
    for piece in pieces:
        width = token_width(piece, fontsize)
        if current == 0 or current + space_width + width <= available:
            current = current + (space_width if current else 0.0) + width
        else:
            lines += 1
            current = width
    return lines


def parse_ass(text: str) -> tuple[dict, dict, list[dict]]:
    info: dict[str, str] = {}
    styles: dict[str, dict] = {}
    events: list[dict] = []
    style_format: list[str] = []
    event_format: list[str] = []
    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if not line or line.startswith(";;"):
            continue
        if section == "Script Info" and ":" in line:
            key, value = line.split(":", 1)
            info[key.strip()] = value.strip()
        elif section in {"V4+ Styles", "V4 Styles"}:
            if line.startswith("Format:"):
                style_format = [item.strip() for item in line[7:].split(",")]
            elif line.startswith("Style:"):
                values = line[7:].split(",")
                style = dict(zip(style_format, (value.strip() for value in values)))
                if style.get("Name"):
                    styles[style["Name"]] = style
        elif section == "Events":
            if line.startswith("Format:"):
                event_format = [item.strip() for item in line[7:].split(",")]
            elif line.startswith("Dialogue:"):
                values = line[9:].split(",", len(event_format) - 1)
                events.append(dict(zip(event_format, values)))
    return info, styles, events


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ass", required=True, type=Path)
    parser.add_argument("--layout", required=True, type=Path)
    parser.add_argument("--srt", type=Path, help="optional SRT delivery reference to format-check against the ASS timeline")
    args = parser.parse_args()
    layout = load(args.layout)
    if layout.get("schemaVersion") != "0.1" or layout.get("node") != "G3":
        fail("subtitle layout contract must be a G3 schemaVersion 0.1 artifact")
    lane = layout.get("lanes", {}).get("narration") if isinstance(layout.get("lanes"), dict) else None
    if not isinstance(lane, dict):
        fail("layout contract requires lanes.narration")
    fontsize = lane.get("fontsize")
    max_lines = lane.get("maxLines")
    if not isinstance(fontsize, (int, float)) or isinstance(fontsize, bool) or fontsize <= 0:
        fail("layout contract lanes.narration.fontsize must be a positive number")
    if not isinstance(max_lines, int) or isinstance(max_lines, bool) or max_lines < 1:
        fail("layout contract lanes.narration.maxLines must be a positive integer")
    info, styles, events = parse_ass(args.ass.read_text(encoding="utf-8-sig"))
    if not events:
        fail("subtitle timeline has no dialogue events")
    try:
        play_res_x = int(info["PlayResX"])
        play_res_y = int(info["PlayResY"])
    except (KeyError, ValueError):
        fail("ASS requires numeric PlayResX and PlayResY in [Script Info]")
    drift_checked: set[tuple[str, float]] = set()
    violations: list[str] = []
    observed = 0
    for event in events:
        style = styles.get(event.get("Style", "")) or next(iter(styles.values()), None)
        if not style:
            fail("subtitle timeline has no ASS style to measure")
        try:
            style_fontsize = float(style["Fontsize"])
        except (KeyError, TypeError, ValueError):
            fail(f"ASS style {style.get('Name')} lacks a numeric Fontsize")
        if style_fontsize <= 0:
            fail(f"ASS style {style.get('Name')} Fontsize must be positive")
        drift_key = (str(style.get("Name")), style_fontsize)
        if style_fontsize != fontsize and drift_key not in drift_checked:
            drift_checked.add(drift_key)
            violations.append(f"ASS style {style.get('Name')} Fontsize {style_fontsize:g} differs from layout contract fontsize {fontsize:g}")
        try:
            margin_left = float(style.get("MarginL") or 0)
            margin_right = float(style.get("MarginR") or 0)
        except ValueError:
            fail(f"ASS style {style.get('Name')} has non-numeric margins")
        available = play_res_x - margin_left - margin_right
        if available <= 0:
            fail(f"style {style.get('Name')} margins leave no usable subtitle width")
        text = OVERRIDE_TAG.sub("", event.get("Text", ""))
        if not text.strip():
            fail(f"event at {event.get('Start', '?')} has empty text")
        total = sum(max(1, wrap_line(hard, style_fontsize, available)) for hard in text.split("\\N"))
        observed = max(observed, total)
        if total > max_lines:
            preview = text.replace("\\N", "⏎")[:24]
            violations.append(f"event at {event.get('Start', '?')} needs {total} rendered lines (max {max_lines}): {preview}")
    if violations:
        suffix = f" (+{len(violations) - 10} more)" if len(violations) > 10 else ""
        fail("subtitle layout violations: " + "; ".join(violations[:10]) + suffix)
    srt_cues = validate_srt_reference(args.srt, len(events)) if args.srt else None
    print(json.dumps({
        "status": "completed",
        "events": len(events),
        "styles": len(styles),
        "fontsize": fontsize,
        "maxLines": max_lines,
        "maxRenderedLinesObserved": observed,
        "playRes": [play_res_x, play_res_y],
        "srtCues": srt_cues,
    }, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "invalid", "error": str(error)}, ensure_ascii=True))
        raise SystemExit(2)
