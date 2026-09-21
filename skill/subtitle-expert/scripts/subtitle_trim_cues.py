#!/usr/bin/env python3
"""Trim subtitle cues that collide with chapter-card intervals (hide-under-card rule).

Subtitle presentation logic lives here, not in G4: a chapter card must never compete
with the narration text layer (demo-quality-patch §4). G4's assemble passes the frozen
approved ASS plus the card ranges and burns in ONLY the derived file this script writes;
the source ASS is never modified.

Handshake (plugin standard): explicit CLI args in, derived .ass + JSON report out.
Report field `trimmedCues` is what G4 records as `subtitleCuesTrimmed`.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ASS_TIME = re.compile(r"(\d+):(\d{2}):(\d{2})\.(\d{2})")
MIN_PIECE_MS = 40  # fragments shorter than this are dropped, not burned as flash cues


def fail(message: str) -> None:
    print(json.dumps({"status": "invalid", "error": message}, ensure_ascii=False))
    raise SystemExit(2)


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def parse_ass_ms(value: str) -> int:
    match = ASS_TIME.fullmatch(value.strip())
    if not match:
        fail(f"unparsable ASS timestamp: {value!r}")
    hours, minutes, seconds, centis = (int(part) for part in match.groups())
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + centis * 10


def format_ass_ms(milliseconds: int) -> str:
    hours, rem = divmod(milliseconds, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{millis // 10:02d}"


def trim_ass_cues(text: str, card_ranges: list[tuple[int, int]]) -> tuple[str, int]:
    """Remove chapter-card intervals from every subtitle cue; returns (derived, trimmed count)."""
    lines, fmt, trimmed = [], None, 0
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("Format:") and {"Start", "End", "Text"} <= {f.strip() for f in line[7:].split(",")}:
            fmt = [f.strip() for f in line[7:].split(",")]
            lines.append(raw)
            continue
        if fmt and line.startswith("Dialogue:"):
            values = line[9:].split(",", len(fmt) - 1)
            event = dict(zip(fmt, values))
            start, end = parse_ass_ms(event["Start"]), parse_ass_ms(event["End"])
            pieces = [[start, end]]
            for card_start, card_end in card_ranges:
                kept = []
                for piece_start, piece_end in pieces:
                    if card_end <= piece_start or card_start >= piece_end:
                        kept.append([piece_start, piece_end])
                        continue
                    if card_start > piece_start:
                        kept.append([piece_start, min(card_start, piece_end)])
                    if card_end < piece_end:
                        kept.append([max(card_end, piece_start), piece_end])
                pieces = kept
            if pieces != [[start, end]]:
                trimmed += 1
            for piece_start, piece_end in pieces:
                if piece_end - piece_start < MIN_PIECE_MS:
                    continue
                event["Start"], event["End"] = format_ass_ms(piece_start), format_ass_ms(piece_end)
                lines.append("Dialogue: " + ",".join(event[field] for field in fmt))
            continue
        lines.append(raw)
    return "\n".join(lines) + "\n", trimmed


def parse_card_range(value: str) -> tuple[int, int]:
    try:
        start_text, end_text = value.split(":", 1)
        start, end = int(start_text), int(end_text)
    except ValueError:
        fail(f"--card-range must be START_MS:END_MS, got {value!r}")
    if start < 0 or end <= start:
        fail(f"--card-range must satisfy 0 <= start < end, got {value!r}")
    return start, end


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ass", required=True, type=Path, help="approved subtitle ASS (read-only)")
    parser.add_argument("--out", required=True, type=Path, help="derived ASS path (this is what G4 burns)")
    parser.add_argument("--card-range", action="append", required=True,
                        help="chapter-card interval START_MS:END_MS, repeatable")
    args = parser.parse_args()

    if not args.ass.is_file():
        fail(f"subtitle ASS not found: {args.ass}")
    card_ranges = [parse_card_range(item) for item in args.card_range]
    source = args.ass.read_text(encoding="utf-8-sig")
    derived, trimmed = trim_ass_cues(source, card_ranges)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(derived, encoding="utf-8")
    if not args.out.is_file() or args.out.stat().st_size == 0:
        fail(f"derived ASS did not land on disk: {args.out}")
    print(json.dumps({"status": "completed", "skill": "subtitle-expert", "purpose": "subtitle_trim_cues",
                      "generatedAt": now(), "sourceAss": str(args.ass.resolve()), "out": str(args.out.resolve()),
                      "cardRanges": [[start, end] for start, end in card_ranges],
                      "trimmedCues": trimmed,
                      "sourceUntouched": True}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
