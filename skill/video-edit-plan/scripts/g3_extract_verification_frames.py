#!/usr/bin/env python3
"""Extract start/middle/end frames for G3 visual verification before approval."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def fail(message: str) -> None:
    raise ValueError(message)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--source-pack", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    plan, evidence = load(args.plan), load(args.evidence)
    known = {item.get("assetId"): item for item in evidence.get("sourceEvidence", [])}
    frames: list[dict] = []
    for segment in plan.get("segments", []):
        asset = known.get(segment.get("assetId"))
        if not asset:
            fail(f"unknown assetId: {segment.get('assetId')}")
        relative = asset.get("relativePath")
        source = (args.source_pack / str(relative)).resolve()
        if not source.is_file() or args.source_pack.resolve() not in source.parents:
            fail(f"registered source missing: {relative}")
        start, end = segment.get("startMs"), segment.get("endMs")
        if not isinstance(start, int) or not isinstance(end, int) or end <= start:
            fail(f"invalid source range: {segment.get('segmentId')}")
        segment_dir = args.output_dir / segment["segmentId"]
        segment_dir.mkdir(parents=True, exist_ok=True)
        moments = (("start", start), ("middle", start + (end - start) // 2), ("end", end - 1))
        refs = []
        for label, ms in moments:
            output = segment_dir / f"{label}-{ms:010d}ms.jpg"
            subprocess.run(["ffmpeg", "-y", "-ss", f"{ms / 1000:.3f}", "-i", str(source), "-frames:v", "1", "-q:v", "2", str(output)], check=True, capture_output=True)
            refs.append({"label": label, "sourceMs": ms, "path": str(output)})
        frames.append({"segmentId": segment["segmentId"], "assetId": segment["assetId"], "sourceRange": {"startMs": start, "endMs": end}, "frames": refs})
    manifest = {"schemaVersion": "0.1", "node": "G3", "purpose": "visual-verification-frames", "planRef": str(args.plan), "segments": frames}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / "G3-visual-verification-frames.json"
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "manifest": str(output), "segments": len(frames)}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(json.dumps({"status": "invalid", "error": str(error)}, ensure_ascii=True))
        raise SystemExit(2)
