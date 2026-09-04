#!/usr/bin/env python3
"""Convert local transcript JSON into reviewable and validated artifacts.

Errors are emitted as structured JSON on stdout so downstream agents can
parse them. Exit codes: 0 success, 2 invalid input or blocked output
boundary, 1 unexpected failure.
"""

import argparse
import json
from pathlib import Path


def emit(payload: dict) -> None:
    # ensure_ascii keeps stdout console-encoding safe on Windows (GBK consoles).
    print(json.dumps(payload, ensure_ascii=True))


def is_plain_int(value) -> bool:
    # bool is a subclass of int in Python; True/False must not pass as timestamps.
    return isinstance(value, int) and not isinstance(value, bool)


def srt_timestamp(milliseconds: int) -> str:
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def validate_segments(segments) -> list[str]:
    if not isinstance(segments, list) or not segments:
        return ["Transcript requires a non-empty segments list"]
    errors: list[str] = []
    seen_ids: set[str] = set()
    previous_end = 0
    for index, segment in enumerate(segments, start=1):
        label = f"segment {index}"
        if not isinstance(segment, dict):
            errors.append(f"{label} must be an object")
            continue
        segment_id = segment.get("segmentId")
        if not isinstance(segment_id, str) or not segment_id.strip():
            errors.append(f"{label} requires a non-empty string segmentId")
        elif segment_id in seen_ids:
            errors.append(f"{label} repeats segmentId '{segment_id}'")
        else:
            seen_ids.add(segment_id)
        start_ms = segment.get("startMs")
        end_ms = segment.get("endMs")
        if not is_plain_int(start_ms) or not is_plain_int(end_ms):
            errors.append(f"{label} requires integer startMs/endMs; booleans are not allowed")
            continue
        if start_ms < 0:
            errors.append(f"{label} has negative startMs")
            continue
        if start_ms < previous_end:
            errors.append(f"{label} has non-monotonic timestamps")
            continue
        if end_ms <= start_ms:
            errors.append(f"{label} has endMs <= startMs")
            continue
        previous_end = end_ms
        if not isinstance(segment.get("text", ""), str):
            errors.append(f"{label} requires text to be a string")
    return errors


def output_inside_pack(output_dir: Path, pack: Path) -> bool:
    try:
        output_dir.resolve().relative_to(pack.resolve())
    except ValueError:
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Write SRT, TXT, and validation manifest from local transcript JSON"
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--source-pack",
        type=Path,
        default=None,
        help="Material pack root; artifacts must stay outside it",
    )
    args = parser.parse_args()

    if args.source_pack is not None and output_inside_pack(args.output_dir, args.source_pack):
        emit(
            {
                "status": "blocked",
                "blockers": [
                    {
                        "type": "output_inside_material_pack",
                        "detail": f"output-dir {args.output_dir} resolves inside {args.source_pack}",
                    }
                ],
            }
        )
        return 2

    try:
        source = json.loads(args.input.read_text(encoding="utf-8"))
    except FileNotFoundError:
        emit({"status": "invalid", "errors": [{"field": "input", "rule": "file not found", "detail": str(args.input)}]})
        return 2
    except json.JSONDecodeError as error:
        emit({"status": "invalid", "errors": [{"field": "input", "rule": "not valid JSON", "detail": str(error)}]})
        return 2

    errors = validate_segments(source.get("segments"))
    if errors:
        emit({"status": "invalid", "errors": [{"field": "segments", "rule": message} for message in errors]})
        return 2

    segments = source["segments"]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    srt_lines: list[str] = []
    txt_lines: list[str] = []
    for index, segment in enumerate(segments, start=1):
        text = segment["text"].strip()
        srt_lines.extend(
            [str(index), f"{srt_timestamp(segment['startMs'])} --> {srt_timestamp(segment['endMs'])}", text, ""]
        )
        txt_lines.append(f"[{segment['startMs']:09d}-{segment['endMs']:09d}] {text}")

    srt_path = args.output_dir / "transcript.srt"
    txt_path = args.output_dir / "transcript.txt"
    manifest_path = args.output_dir / "manifest.json"
    srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
    txt_path.write_text("\n".join(txt_lines) + "\n", encoding="utf-8")
    manifest = {
        "schemaVersion": "0.1",
        "status": "completed",
        "input": str(args.input),
        "artifacts": {"srt": srt_path.name, "txt": txt_path.name},
        "segments": len(segments),
        "validation": {
            "passed": True,
            "timestampsMonotonic": True,
            "timestampsNonOverlapping": True,
            "txtMatchesSrt": True,
            "lastTimestampMs": segments[-1]["endMs"],
        },
        "warning": "Machine transcription draft. Verify names, specialist terms, and factual claims before use.",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    emit({"status": "completed", "segments": len(segments), "outputDir": str(args.output_dir)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
