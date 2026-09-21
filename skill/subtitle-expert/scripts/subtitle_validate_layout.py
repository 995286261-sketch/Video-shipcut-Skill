#!/usr/bin/env python3
"""Machine-check a G3 narration ASS timeline against its subtitle layout contract.

Owned by subtitle-expert (字幕领域专员，用户 2026-09-21 拍板自 video-edit-plan 剥出，
原名 validate_g3_subtitle_layout.py)。G3 只调用并消费结果；布局合同形状与渲染器能力档
见 references/layout-contract.md。

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
ASS_TIME = re.compile(r"(\d+):(\d{2}):(\d{2})\.(\d{2})")
PUNCTUATION = "。！？；，、：：“”‘’\"'（）()《》…—·-~～\\N \t\r"


def fail(message: str) -> None:
    raise ValueError(message)


def ass_to_ms(value: str) -> int:
    match = ASS_TIME.fullmatch(value.strip())
    if not match:
        fail(f"unparsable ASS timestamp: {value!r}")
    hours, minutes, seconds, centis = (int(part) for part in match.groups())
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + centis * 10


def srt_to_ms(hours, minutes, seconds, millis) -> int:
    return ((int(hours) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + int(millis)


def normalize_text(text: str) -> str:
    """Compare cue identity with line breaks and punctuation ignored: the same caption
    may legitimately drop sentence-final punctuation across ASS→SRT or vs the script."""
    return "".join(ch for ch in text if ch not in PUNCTUATION)


def validate_srt_reference(path: Path, events: list[dict]) -> int:
    """The SRT delivery copy must be standard-padded (HH:MM:SS,mmm) AND cue-for-cue
    identical to the approved ASS timeline: same count, same start/end in milliseconds,
    same text (punctuation/break-insensitive). The old check only verified count and
    monotonicity, so a uniform 10× timebase slip (issue ㊍) could still pass; matching
    ASS times explicitly is what makes '同源派生' machine-enforced."""
    blocks = [b for b in re.split(r"\n\s*\n", path.read_text(encoding="utf-8-sig").strip()) if b.strip()]
    if not blocks:
        fail("srt reference has no cues")
    if len(blocks) != len(events):
        fail(f"srt cue count {len(blocks)} does not match ASS event count {len(events)}")
    for index, (block, event) in enumerate(zip(blocks, events), 1):
        lines = block.splitlines()
        if len(lines) < 3:
            fail(f"srt cue {index} must be an index, a timestamp line, and text")
        match = SRT_TIME.fullmatch(lines[1].strip())
        if not match:
            fail(f"srt cue {index} timestamp line must be HH:MM:SS,mmm --> HH:MM:SS,mmm: {lines[1]!r}")
        start, end = srt_to_ms(*match.groups()[:4]), srt_to_ms(*match.groups()[4:])
        if end <= start:
            fail(f"srt cue {index} ends before it starts")
        ass_start, ass_end = ass_to_ms(event["Start"]), ass_to_ms(event["End"])
        if (start, end) != (ass_start, ass_end):
            fail(f"srt cue {index} times {start}-{end}ms do not match ASS event times {ass_start}-{ass_end}ms — the delivery copy must be derived from the approved timeline, not re-timed (㊍)")
        ass_text = normalize_text(OVERRIDE_TAG.sub("", event.get("Text", "")))
        srt_text = normalize_text("".join(lines[2:]))
        if not srt_text:
            fail(f"srt cue {index} has empty text")
        if srt_text != ass_text:
            fail(f"srt cue {index} text does not match the ASS event (normalized): {lines[2].strip()[:24]!r}")
    return len(blocks)


def check_event_overlap(events: list[dict]) -> list[str]:
    """Narration lanes are a single text layer: two events sharing wall-clock time is
    how 'emphasis split into its own layer' (rule 3) shows up mechanically (layout-contract)."""
    problems: list[str] = []
    timed = sorted(events, key=lambda item: ass_to_ms(item["Start"]))
    for previous, current in zip(timed, timed[1:]):
        if ass_to_ms(current["Start"]) < ass_to_ms(previous["End"]):
            problems.append(f"events at {previous.get('Start')} and {current.get('Start')} overlap in time — emphasis must stay inside one block's rich-text tags, not a parallel layer (rule 3)")
    return problems


def check_narration_source(path: Path, events: list[dict]) -> int:
    """Rule 1 (一条口播一排版块) machine-enforced against the authoritative layer: the
    G2 口播句子 JSON ([{sentenceId,text}, ...] — one approved narration block per row)
    must line up with the ASS timeline event for event, text identical modulo
    punctuation and \\N (002 实测形态: a block may contain several 。clauses and one
    visual break mid-sentence). Guards silent divergence when narration is amended but
    the timeline is not regenerated."""
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict):
        data = data.get("sentences") or data.get("units") or []
    if not isinstance(data, list):
        fail("--source must be the G2 口播句子 JSON (a list of narration blocks, each with text)")
    blocks = []
    for item in data:
        text = item.get("text") if isinstance(item, dict) else item
        normalized = normalize_text(str(text or ""))
        if normalized:
            blocks.append(normalized)
    if len(blocks) != len(events):
        fail(f"narration source has {len(blocks)} blocks but the timeline has {len(events)} events — one narration block must be exactly one layout block (rule 1)")
    for index, (block, event) in enumerate(zip(blocks, events), 1):
        cue_text = normalize_text(OVERRIDE_TAG.sub("", event.get("Text", "")))
        if cue_text != block:
            fail(f"event {index} text does not match narration block {index} (normalized): {cue_text[:24]!r} vs {block[:24]!r} — subtitles carry the approved narration verbatim")
    return len(blocks)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def char_units(ch: str) -> float:
    return 1.0 if unicodedata.east_asian_width(ch) in {"F", "W"} else NARROW_RATIO


def token_width(token: str, fontsize: float) -> float:
    return sum(char_units(ch) for ch in token) * fontsize


def wrap_line(line: str, fontsize: float, available: float, allow_char_break: bool) -> tuple[int, bool]:
    """Count the lines the renderer needs for one hard line, and report overflow.

    Issue 002-⑧: the old model assumed any CJK character could break, but local libass
    builds do NOT auto-wrap CJK runs — a validator green light did not guarantee a
    correct render. With allow_char_break=False (the conservative default) spaces are
    the only legal break points, and a single token wider than the available width is
    reported as overflow: that renderer will clip it instead of wrapping."""
    space_width = NARROW_RATIO * fontsize
    pieces: list[str] = []
    overflow = False
    for token in line.split(" "):
        if not token or token_width(token, fontsize) <= available:
            pieces.append(token)
            continue
        if not allow_char_break:
            overflow = True
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
    return lines, overflow


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
    parser.add_argument("--srt", type=Path, help="optional SRT delivery copy to check cue-for-cue against the ASS timeline")
    parser.add_argument("--source", type=Path, help="optional G2 口播句子 JSON (authoritative narration blocks) to enforce one-block-per-event (rule 1)")
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
    # Renderer capability profile (issue 002-⑧): absent means conservative — assume the
    # renderer cannot auto-wrap CJK, so explicit line breaks are mandatory for long runs.
    auto_wrap = lane.get("autoWrap", False)
    if not isinstance(auto_wrap, bool):
        fail("layout contract lanes.narration.autoWrap must be a boolean when present")
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
        total, overflowed = 0, False
        for hard in text.split("\\N"):
            hard_lines, hard_overflow = wrap_line(hard, style_fontsize, available, auto_wrap)
            total += max(1, hard_lines)
            overflowed = overflowed or hard_overflow
        if overflowed and not auto_wrap:
            preview = text.replace("\\N", "⏎")[:24]
            violations.append(f"event at {event.get('Start', '?')} has an unbreakable run wider than the render width; this renderer does not auto-wrap CJK — split with explicit \\N: {preview}")
        observed = max(observed, total)
        if total > max_lines:
            preview = text.replace("\\N", "⏎")[:24]
            violations.append(f"event at {event.get('Start', '?')} needs {total} rendered lines (max {max_lines}): {preview}")
    if any("Start" not in event or "End" not in event for event in events):
        fail("ASS events must carry Start and End fields in [Events] Format")
    violations.extend(check_event_overlap(events))
    if violations:
        suffix = f" (+{len(violations) - 10} more)" if len(violations) > 10 else ""
        fail("subtitle layout violations: " + "; ".join(violations[:10]) + suffix)
    srt_cues = validate_srt_reference(args.srt, events) if args.srt else None
    source_sentences = check_narration_source(args.source, events) if args.source else None
    print(json.dumps({
        "status": "completed",
        "events": len(events),
        "styles": len(styles),
        "fontsize": fontsize,
        "maxLines": max_lines,
        "autoWrap": auto_wrap,
        "maxRenderedLinesObserved": observed,
        "playRes": [play_res_x, play_res_y],
        "srtCues": srt_cues,
        "sourceSentences": source_sentences,
    }, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "invalid", "error": str(error)}, ensure_ascii=True))
        raise SystemExit(2)
