#!/usr/bin/env python3
"""Standalone SRT QA for a finished reference subtitle file (no ASS pairing needed).

The full ASS↔SRT alignment check (cue-count match against the approved timeline) is
`subtitle_validate_layout.py --srt`, run at G3. This checker covers the delivery-side
question G5 asks without an ASS at hand: is this .srt a well-formed, monotonic,
non-overlapping caption file? SRT timebase incidents (issue ㊍: a 10× scaling slip
shipped in a delivery bundle) are caught here as well as at G3 — G5 no longer carries
its own private timestamp regex.

Handshake (plugin standard): CLI in, JSON report out; the agent files the report inside
the delivery bundle as `subtitle-srt-check.json` and G5 validates the handshake
(status=passed AND the recorded sha256 still matches the bundle's subtitles.srt —
same freshness pattern as G0's BGM registration receipt).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SRT_TIME = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})")


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def emit(status: str, payload: dict) -> int:
    print(json.dumps({"status": status, "skill": "subtitle-expert", "purpose": "subtitle_check_srt",
                      "generatedAt": now(), **payload}, ensure_ascii=False))
    return 0 if status == "passed" else (1 if status == "failed" else 2)


def to_ms(hours: str, minutes: str, seconds: str, millis: str) -> int:
    return ((int(hours) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + int(millis)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def check_srt(text: str) -> tuple[list[dict], list[str]]:
    cues, errors = [], []
    blocks = [block for block in re.split(r"\r?\n\s*\r?\n", text.strip()) if block.strip()]
    for index, block in enumerate(blocks, start=1):
        lines = [line.strip() for line in block.splitlines()]
        if len(lines) < 3:
            errors.append(f"cue {index}: expected an index, a timestamp line, and text")
            continue
        if lines[0] != str(index):
            errors.append(f"cue {index}: index line is {lines[0]!r}, expected {index!r}")
        match = SRT_TIME.fullmatch(lines[1])
        if not match:
            errors.append(f"cue {index}: timestamp line must be HH:MM:SS,mmm --> HH:MM:SS,mmm: {lines[1]!r}")
            continue
        start, end = to_ms(*match.groups()[:4]), to_ms(*match.groups()[4:])
        if end <= start:
            errors.append(f"cue {index}: ends at or before it starts")
        if cues and start < cues[-1]["endMs"]:
            errors.append(f"cue {index}: overlaps or precedes the previous cue")
        if not "\n".join(lines[2:]).strip():
            errors.append(f"cue {index}: empty text")
        cues.append({"index": index, "startMs": start, "endMs": end})
    return cues, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("srt", type=Path)
    args = parser.parse_args()
    if not args.srt.is_file():
        return emit("invalid", {"file": str(args.srt), "error": "SRT file not found"})
    text = args.srt.read_text(encoding="utf-8-sig")
    if not text.strip():
        return emit("invalid", {"file": str(args.srt), "error": "SRT file is empty"})
    cues, errors = check_srt(text)
    identity = {"file": str(args.srt.resolve()), "sha256": sha256(args.srt)}
    if not cues:
        return emit("invalid", {**identity, "error": "SRT contains no parseable cues"})
    if errors:
        return emit("failed", {**identity, "cues": len(cues), "errors": errors})
    return emit("passed", {**identity, "cues": len(cues), "lastEndMs": cues[-1]["endMs"], "errors": []})


if __name__ == "__main__":
    sys.exit(main())
