#!/usr/bin/env python3
"""Derive the delivery SRT from an approved ASS timeline (single mechanical path).

ASS is the style master burned into the picture (G3 approved timeline, G4 burns it);
SRT is the delivery copy — same data, stripped of styling, for platforms/players
(layout-contract generation rule 2). Rule 2 was already written law after incident ㊍
(a 10× timebase slip shipped in a delivery bundle); this tool makes the derivation
mechanical so hand-transcription — and with it the whole class of timebase slips —
retires (banshee-001 issue ⑭ sub-item 4).

Conversion is pure integer arithmetic: ASS centiseconds ×10 = SRT milliseconds,
zero-padded; `\\N` and `\\n` become real line breaks; `{...}` override tags are
stripped; cue order follows [Events] write order (same order `--srt` pair-checks).

Handshake (plugin standard): explicit CLI args in, derived .srt + JSON report out.
Exit codes: 0=completed, 2=invalid input, 1=runtime failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ASS_TIME = re.compile(r"^(\d+):(\d{2}):(\d{2})\.(\d{2})$")
OVERRIDE_TAG = re.compile(r"\{[^{}]*\}")


def fail(message: str) -> None:
    print(json.dumps({"status": "invalid", "error": message}, ensure_ascii=False))
    raise SystemExit(2)


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def ass_ms(text: str, context: str) -> int:
    match = ASS_TIME.match(text.strip())
    if not match:
        fail(f"cannot parse ASS time {text!r} ({context}); expected H:MM:SS.cc")
    hours, minutes, seconds, centis = (int(group) for group in match.groups())
    return ((hours * 3600 + minutes * 60 + seconds) * 100 + centis) * 10


def srt_time(ms: int) -> str:
    hours, rest = divmod(ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    seconds, millis = divmod(rest, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def cue_text(text: str, context: str) -> str:
    cleaned = OVERRIDE_TAG.sub("", text)
    cleaned = cleaned.replace("\\N", "\n").replace("\\n", "\n")
    if not cleaned.strip():
        fail(f"Dialogue event has no visible text after stripping tags ({context})")
    return cleaned


def parse_events(ass_text: str) -> list[tuple[int, int, str]]:
    if "[Events]" not in ass_text:
        fail("input has no [Events] section; this must be an ASS subtitle timeline")
    cues: list[tuple[int, int, str]] = []
    for lineno, line in enumerate(ass_text.splitlines(), start=1):
        if not line.startswith("Dialogue:"):
            continue  # Comment/Format lines carry no delivery text
        fields = line[len("Dialogue:"):].split(",", 9)
        if len(fields) < 10:
            fail(f"line {lineno}: Dialogue event has fewer than 10 comma-separated fields")
        start_ms = ass_ms(fields[1], f"line {lineno} start")
        end_ms = ass_ms(fields[2], f"line {lineno} end")
        if start_ms >= end_ms:
            fail(f"line {lineno}: start {start_ms}ms >= end {end_ms}ms")
        cues.append((start_ms, end_ms, cue_text(fields[9], f"line {lineno}")))
    if not cues:
        fail("no Dialogue events found in [Events]; nothing to deliver")
    return cues


def build_srt(cues: list[tuple[int, int, str]]) -> str:
    blocks = [
        f"{index}\n{srt_time(start)} --> {srt_time(end)}\n{text}"
        for index, (start, end, text) in enumerate(cues, start=1)
    ]
    return "\n\n".join(blocks) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--ass", required=True, type=Path,
                        help="approved ASS subtitle timeline (G3 权威母版; never modified)")
    parser.add_argument("--out", type=Path,
                        help="derived SRT path (default: next to the ASS with the same stem, "
                             "e.g. G3-字幕时间轴-v0.2.ass -> G3-字幕时间轴-v0.2.srt)")
    args = parser.parse_args(argv)

    if not args.ass.is_file():
        fail(f"ASS timeline not found: {args.ass}")
    try:
        ass_text = args.ass.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as error:
        fail(f"cannot read ASS timeline: {error}")

    cues = parse_events(ass_text)
    srt_text = build_srt(cues)

    out = args.out if args.out else args.ass.with_suffix(".srt")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(srt_text)
    if not out.is_file() or out.stat().st_size == 0:
        fail(f"derived SRT did not land on disk: {out}")

    print(json.dumps({
        "status": "completed",
        "srt": str(out),
        "cues": len(cues),
        "sourceAss": str(args.ass),
        "sourceSha256": hashlib.sha256(args.ass.read_bytes()).hexdigest().upper(),
        "convertedAt": now(),
        "note": ("SRT 时基=ASS 百分秒 ×10 零填充、\\N 转真实换行（layout-contract 生成规则 2 机械执行，"
                 "㊍ 根治；手写通道退役，⑭小4）；交付 SRT 只许由本工具从批准 ASS 派生"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
