#!/usr/bin/env python3
"""Extract timecoded G3 keyframes before multimodal visual analysis."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def fail(message: str) -> None:
    raise ValueError(message)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def extract_frame(source: Path, requested_ms: int, floor_ms: int, output: Path) -> int:
    """Probe one keyframe; ffmpeg can exit 0 without writing near the container end, so step back.

    Returns the actual probed ms; raises when no probe in the fallback window produced a file.
    """
    for step in range(0, 600, 100):
        probe_ms = max(floor_ms, requested_ms - step)
        subprocess.run([
            "ffmpeg", "-y", "-ss", f"{probe_ms / 1000:.3f}", "-i", str(source),
            "-frames:v", "1", "-q:v", "2", str(output),
        ], check=True, capture_output=True)
        if output.is_file() and output.stat().st_size > 0:
            return probe_ms
        output.unlink(missing_ok=True)
    fail(f"ffmpeg exited without producing keyframe file for {output.name} (probed {requested_ms}ms back to {max(floor_ms, requested_ms - 500)}ms)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--source-pack", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--interval-ms", type=int, default=15_000)
    args = parser.parse_args()
    if args.interval_ms <= 0:
        fail("interval-ms must be positive")
    evidence = load(args.evidence)
    entry = next((item for item in evidence.get("sourceEvidence", []) if item.get("assetId") == args.asset_id), None)
    if not entry:
        fail(f"unknown assetId: {args.asset_id}")
    relative = entry.get("relativePath")
    if not isinstance(relative, str) or not relative.strip():
        fail(f"source evidence for {args.asset_id} requires relativePath")
    source_pack = args.source_pack.resolve()
    source = (source_pack / str(relative)).resolve()
    if not source.is_file() or source_pack not in source.parents:
        fail(f"registered source missing or outside source pack: {relative}")
    actual_hash = sha256(source)
    if actual_hash != str(entry.get("sha256", "")).upper():
        fail(f"source SHA-256 mismatch for {args.asset_id}")
    duration_ms = int(entry.get("sourceProbe", {}).get("durationMs", 0))
    if duration_ms <= 0:
        fail("source evidence requires positive durationMs")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = args.output_dir / "关键帧"
    frames_dir.mkdir(parents=True, exist_ok=True)
    moments = list(range(0, duration_ms, args.interval_ms))
    # Avoid requesting the exact final container timestamp; it can be beyond the decodable frame boundary.
    final_probe_ms = max(0, duration_ms - 1000)
    if moments[-1] != final_probe_ms:
        moments.append(final_probe_ms)
    frames = []
    for index, source_ms in enumerate(moments, start=1):
        output = frames_dir / f"frame-{index:03d}-{source_ms:010d}ms.jpg"
        probed_ms = extract_frame(source, source_ms, 0, output)
        frames.append({
            "frameId": f"vf-{index:03d}",
            "requestedSourceMs": source_ms,
            "sourceMs": probed_ms,
            "path": str(output),
            "analysisStatus": "pending",
        })
    manifest = {
        "schemaVersion": "0.1",
        "projectId": evidence.get("projectId"),
        "node": "G3",
        "status": "keyframes_ready",
        "analysisScope": "full_source_interval_15000ms",
        "sourcePackRef": str(source_pack / "material-pack.json"),
        "provider": None,
        "model": None,
        "promptVersion": None,
        "targetAssets": [{
            "assetId": args.asset_id,
            "sha256": actual_hash,
            "sourceRange": {"startMs": 0, "endMs": duration_ms},
            "keyframes": frames,
        }],
        "failurePolicy": "pending_or_failed_frames_cannot_be_marked_completed",
    }
    output = args.output_dir / "G3-目标素材视觉分析-v0.1.json"
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "keyframes_ready", "manifest": str(output), "frames": len(frames)}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(json.dumps({"status": "invalid", "error": str(error)}, ensure_ascii=True))
        raise SystemExit(2)
