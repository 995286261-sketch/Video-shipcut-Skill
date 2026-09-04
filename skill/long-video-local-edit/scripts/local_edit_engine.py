#!/usr/bin/env python3
"""Deterministic local media engine for the long-video-local-edit skill."""

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


class EngineError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise EngineError(f"JSON file not found: {path}") from error
    except json.JSONDecodeError as error:
        raise EngineError(f"Invalid JSON in {path}: {error}") from error


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def media_binary(name: str) -> str:
    home = os.environ.get("P0C_FFMPEG_HOME")
    if home:
        for candidate in (Path(home) / f"{name}.exe", Path(home) / "bin" / f"{name}.exe"):
            if candidate.is_file():
                return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    raise EngineError(
        f"{name} was not found. Set P0C_FFMPEG_HOME or add the FFmpeg bin directory to PATH."
    )


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "no tool output"
        raise EngineError(f"Media command failed: {detail}")
    return result


def resolve_source(source_value: str, project_root: Path) -> Path:
    candidate = Path(source_value)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    candidate = candidate.resolve()
    if not candidate.is_file():
        raise EngineError(f"Source asset is not a readable file: {candidate}")
    return candidate


def parse_fraction(value: str | None) -> float | None:
    if not value or value == "0/0":
        return None
    numerator, denominator = value.split("/", maxsplit=1)
    if float(denominator) == 0:
        return None
    return float(numerator) / float(denominator)


def ffprobe(path: Path) -> dict[str, Any]:
    command = [
        media_binary("ffprobe"),
        "-v",
        "error",
        "-show_entries",
        "format=duration,size,bit_rate:stream=index,codec_type,codec_name,width,height,r_frame_rate,channels,sample_rate",
        "-of",
        "json",
        str(path),
    ]
    return json.loads(run(command).stdout)


def probe_asset(asset: dict[str, Any], project_root: Path) -> tuple[dict[str, Any], Path]:
    for field in ("assetId", "sourceKind", "sourceValue", "sha256"):
        if not asset.get(field):
            raise EngineError(f"sourceAsset is missing {field}")
    if asset["sourceKind"] != "local-file":
        raise EngineError(f"Only sourceKind=local-file is supported, got {asset['sourceKind']}")

    source = resolve_source(asset["sourceValue"], project_root)
    actual_hash = sha256(source)
    if actual_hash != asset["sha256"].upper():
        raise EngineError(f"sha256 mismatch for {asset['assetId']}")
    raw = ffprobe(source)
    streams = raw.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    if not video:
        raise EngineError(f"Source asset has no video stream: {asset['assetId']}")
    duration_ms = round(float(raw["format"]["duration"]) * 1000)
    return (
        {
            "assetId": asset["assetId"],
            "sha256": actual_hash,
            "durationMs": duration_ms,
            "video": {
                "width": video.get("width"),
                "height": video.get("height"),
                "fps": parse_fraction(video.get("r_frame_rate")),
                "codec": video.get("codec_name"),
            },
            "audio": {
                "present": audio is not None,
                "codec": audio.get("codec_name") if audio else None,
                "sampleRateHz": int(audio["sample_rate"]) if audio and audio.get("sample_rate") else None,
                "channels": audio.get("channels") if audio else None,
            },
            "probeStatus": "ok",
        },
        source,
    )


def validate_request(request: dict[str, Any]) -> list[dict[str, Any]]:
    if request.get("schemaVersion") != "0.1":
        raise EngineError("Only schemaVersion=0.1 is supported")
    if request.get("operation") != "media.edit.plan":
        raise EngineError("operation must be media.edit.plan")
    if not request.get("requestId") or not request.get("projectId"):
        raise EngineError("requestId and projectId are required")
    if not request.get("editPrompt"):
        raise EngineError("editPrompt is required")
    assets = request.get("sourceAssets")
    if not isinstance(assets, list) or not assets:
        raise EngineError("sourceAssets must contain at least one local asset")
    return assets


def profile(request: dict[str, Any]) -> dict[str, Any]:
    target = request.get("targetProfile") or {}
    ratio = target.get("aspectRatio", "16:9")
    if ratio != "16:9":
        raise EngineError("MVP renderer currently supports targetProfile.aspectRatio=16:9 only")
    duration = target.get("targetDurationSec")
    if not isinstance(duration, (int, float)) or duration <= 0:
        raise EngineError("targetProfile.targetDurationSec must be positive")
    return {
        "aspectRatio": ratio,
        "targetDurationSec": float(duration),
        "width": int(target.get("width", 1920)),
        "height": int(target.get("height", 1080)),
        "fps": int(target.get("fps", 30)),
    }


def quality_policy() -> dict[str, Any]:
    config_path = Path(__file__).resolve().parents[1] / "config" / "default-horizontal-explainer-v1.json"
    policy = load_json(config_path).get("qualityPolicy")
    if not isinstance(policy, dict):
        raise EngineError("Default style configuration is missing qualityPolicy")
    return policy


def build_plan(request: dict[str, Any], workspace: Path, project_root: Path) -> dict[str, Any]:
    assets = validate_request(request)
    target = profile(request)
    source_probe: list[dict[str, Any]] = []
    source_map: dict[str, Path] = {}
    for asset in assets:
        item, source = probe_asset(asset, project_root)
        source_probe.append(item)
        source_map[item["assetId"]] = source

    probes = {item["assetId"]: item for item in source_probe}
    hints = request.get("selectionHints") or []
    if not hints:
        return {
            "schemaVersion": "0.1",
            "requestId": request["requestId"],
            "projectId": request["projectId"],
            "sourceProbe": source_probe,
            "segments": [],
            "editPlan": {},
            "artifacts": [],
            "qaReport": {},
            "humanReviewPoints": [
                {
                    "type": "selection_evidence_required",
                    "message": "No local transcript/model or human selectionHints are available to ground candidate selection.",
                }
            ],
            "evidenceRefs": [],
            "warnings": ["semantic_selection_not_configured"],
            "status": "insufficient_material",
            "finishedAt": utc_now(),
        }

    segments: list[dict[str, Any]] = []
    evidence_refs: list[dict[str, Any]] = []
    timeline: list[dict[str, Any]] = []
    output_cursor = 0
    for index, hint in enumerate(hints, start=1):
        asset_id = hint.get("assetId")
        if asset_id not in probes:
            raise EngineError(f"selectionHint references unknown assetId: {asset_id}")
        start_ms = int(hint.get("startMs", -1))
        end_ms = int(hint.get("endMs", -1))
        if not 0 <= start_ms < end_ms <= probes[asset_id]["durationMs"]:
            raise EngineError(f"selectionHint has invalid time range for {asset_id}")
        segment_id = f"seg-{asset_id}-{start_ms:08d}-{end_ms:08d}"
        evidence_id = f"ev-human-hint-{index:03d}"
        reason = hint.get("reason") or "Human-provided fixture selection hint."
        evidence_refs.append(
            {
                "evidenceRefId": evidence_id,
                "type": "human_note",
                "assetId": asset_id,
                "sourceSha256": probes[asset_id]["sha256"],
                "startMs": start_ms,
                "endMs": end_ms,
                "value": reason,
                "producer": "fixture-selection-hint",
                "confidence": 1.0,
            }
        )
        segments.append(
            {
                "segmentId": segment_id,
                "assetId": asset_id,
                "sourceSha256": probes[asset_id]["sha256"],
                "startMs": start_ms,
                "endMs": end_ms,
                "tags": hint.get("tags", []),
                "score": 0.75,
                "scoreBreakdown": {"humanEvidence": 1.0},
                "reason": reason,
                "evidenceRefIds": [evidence_id],
                "reviewState": "proposed",
            }
        )
        duration_ms = end_ms - start_ms
        timeline.append(
            {
                "timelineItemId": f"tl-{index:03d}",
                "segmentId": segment_id,
                "outputStartMs": output_cursor,
                "outputEndMs": output_cursor + duration_ms,
                "transitionOut": {"type": "cut"},
                "audio": {"mode": "source", "fadeInMs": 30, "fadeOutMs": 30},
                "captionRefs": [],
                "overlayRefs": [],
            }
        )
        output_cursor += duration_ms

    target_ms = round(target["targetDurationSec"] * 1000)
    warnings = ["semantic_selection_not_configured; plan uses explicit fixture selectionHints"]
    if abs(output_cursor - target_ms) > 1000:
        warnings.append(f"target_duration_deviation_ms={output_cursor - target_ms}")
    plan = {
        "planVersion": "0.1",
        "planId": f"plan-{request['requestId']}-r1",
        "approvalState": "pending",
        "styleProfileId": request.get("styleProfileId", "default-horizontal-explainer-v1"),
        "targetProfile": request.get("targetProfile"),
        "renderProfile": target,
        "timeline": timeline,
        "captions": [],
        "overlays": [],
        "qualityPolicy": quality_policy(),
        "cover": request.get("targetProfile", {}).get("cover", {"enabled": False}),
        "export": {"container": "mp4", "videoCodec": "h264", "audioCodec": "aac"},
    }
    result = {
        "schemaVersion": "0.1",
        "requestId": request["requestId"],
        "projectId": request["projectId"],
        "sourceProbe": source_probe,
        "segments": segments,
        "editPlan": plan,
        "artifacts": [{"artifactId": "art-plan-result", "type": "plan", "path": "plan-result.json", "producedBy": "local-plan"}],
        "qaReport": {},
        "humanReviewPoints": [
            {
                "type": "approval_required",
                "message": "Approve this plan before rendering. The current MVP used human fixture selectionHints, not semantic AI selection.",
            },
            {
                "type": "quality_policy_review_required",
                "message": "Review the configured visual, caption, and audio quality requirements before approving the plan.",
            }
        ],
        "evidenceRefs": evidence_refs,
        "warnings": warnings,
        "status": "review_required",
        "finishedAt": utc_now(),
        "requestSnapshot": request,
        "projectRoot": str(project_root),
    }
    write_json(workspace / "plan-result.json", result)
    return result


def approve(plan_path: Path, reviewer: str, output: Path) -> dict[str, Any]:
    result = load_json(plan_path)
    if result.get("status") != "review_required":
        raise EngineError("Only a review_required plan can be approved")
    if not reviewer.strip():
        raise EngineError("reviewer is required")
    result["editPlan"]["approvalState"] = "approved"
    result["editPlan"]["approvedBy"] = reviewer
    result["editPlan"]["approvedAt"] = utc_now()
    result["status"] = "completed"
    result["finishedAt"] = utc_now()
    write_json(output, result)
    return result


def source_for_segment(plan_result: dict[str, Any], segment: dict[str, Any]) -> tuple[dict[str, Any], Path]:
    project_root = Path(plan_result["projectRoot"])
    asset = next(item for item in plan_result["requestSnapshot"]["sourceAssets"] if item["assetId"] == segment["assetId"])
    source = resolve_source(asset["sourceValue"], project_root)
    if sha256(source) != segment["sourceSha256"]:
        raise EngineError(f"Source asset changed after planning: {segment['assetId']}")
    return asset, source


def render(plan_path: Path, workspace: Path) -> dict[str, Any]:
    result = load_json(plan_path)
    plan = result.get("editPlan", {})
    if plan.get("approvalState") != "approved":
        raise EngineError("Render requires an approved editPlan")
    workspace.mkdir(parents=True, exist_ok=True)
    render_profile = plan["renderProfile"]
    width, height, fps = render_profile["width"], render_profile["height"], render_profile["fps"]
    segments_by_id = {segment["segmentId"]: segment for segment in result["segments"]}
    clips_dir = workspace / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    clip_paths: list[Path] = []
    for item in plan["timeline"]:
        segment = segments_by_id[item["segmentId"]]
        _, source = source_for_segment(result, segment)
        clip_path = clips_dir / f"{item['timelineItemId']}.mp4"
        duration_sec = (segment["endMs"] - segment["startMs"]) / 1000
        fade_out = max(0.0, duration_sec - 0.03)
        video_filter = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x101418,setsar=1,fps={fps}"
        )
        command = [
            media_binary("ffmpeg"), "-y", "-ss", str(segment["startMs"] / 1000), "-i", str(source),
            "-t", str(duration_sec), "-map", "0:v:0", "-vf", video_filter,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-an",
            "-movflags", "+faststart", str(clip_path),
        ]
        run(command)
        clip_paths.append(clip_path)

    concat_file = workspace / "concat.txt"
    concat_file.write_text("".join(f"file '{path.as_posix()}'\n" for path in clip_paths), encoding="utf-8")
    final_path = workspace / "renders" / "final.mp4"
    final_path.parent.mkdir(parents=True, exist_ok=True)
    run([media_binary("ffmpeg"), "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(final_path)])
    qa_report = quality_report(plan, final_path)
    final_artifact = {
        "artifactId": "art-final-render",
        "type": "final_render",
        "path": str(final_path.relative_to(workspace)),
        "sha256": sha256(final_path),
        "producedBy": "local-render",
        "planId": plan["planId"],
    }
    result["artifacts"] = [item for item in result.get("artifacts", []) if item.get("type") != "final_render"] + [final_artifact]
    result["qaReport"] = qa_report
    result["status"] = "completed" if qa_report["status"] != "fail" else "failed"
    result["finishedAt"] = utc_now()
    write_json(workspace / "render-result.json", result)
    return result


def quality_report(plan: dict[str, Any], artifact: Path) -> dict[str, Any]:
    raw = ffprobe(artifact)
    streams = raw["streams"]
    video = next(stream for stream in streams if stream.get("codec_type") == "video")
    duration_ms = round(float(raw["format"]["duration"]) * 1000)
    expected_duration_ms = plan["timeline"][-1]["outputEndMs"] if plan["timeline"] else 0
    expected = plan["renderProfile"]
    duplicate_segments = len({item["segmentId"] for item in plan["timeline"]}) != len(plan["timeline"])
    checks = {
        "decodable": {"status": "pass", "detail": "ffprobe read final artifact"},
        "encoding": {"status": "pass" if video.get("codec_name") == "h264" else "fail", "actual": video.get("codec_name"), "expected": "h264"},
        "dimensions": {"status": "pass" if (video.get("width"), video.get("height")) == (expected["width"], expected["height"]) else "fail", "actual": [video.get("width"), video.get("height")], "expected": [expected["width"], expected["height"]]},
        "duration": {"status": "pass" if abs(duration_ms - expected_duration_ms) <= 500 else "fail", "actualMs": duration_ms, "expectedMs": expected_duration_ms},
        "duplicate": {"status": "fail" if duplicate_segments else "pass", "detail": "Exact repeated segment IDs in timeline"},
        "blackFrames": {"status": "warning", "detail": "Detector is reserved for the next QA increment; manual review required."},
        "silence": {"status": "warning", "detail": "Detector is reserved for the next QA increment; manual review required."},
    }
    return {"status": "fail" if any(item["status"] == "fail" for item in checks.values()) else "pass", "checks": checks}


def qa(plan_path: Path, artifact: Path) -> dict[str, Any]:
    result = load_json(plan_path)
    report = quality_report(result["editPlan"], artifact)
    return {"schemaVersion": "0.1", "qaReport": report, "finishedAt": utc_now()}


def doctor() -> dict[str, Any]:
    checks: dict[str, Any] = {}
    for name in ("ffmpeg", "ffprobe"):
        try:
            path = media_binary(name)
            version = run([path, "-version"]).stdout.splitlines()[0]
            checks[name] = {"status": "pass", "path": path, "version": version}
        except EngineError as error:
            checks[name] = {"status": "fail", "detail": str(error)}
    return {"status": "pass" if all(item["status"] == "pass" for item in checks.values()) else "fail", "checks": checks, "finishedAt": utc_now()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Local multi-video edit engine")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("doctor")
    plan_parser = subcommands.add_parser("plan")
    plan_parser.add_argument("--request", required=True, type=Path)
    plan_parser.add_argument("--workspace", required=True, type=Path)
    approve_parser = subcommands.add_parser("approve")
    approve_parser.add_argument("--plan", required=True, type=Path)
    approve_parser.add_argument("--reviewer", required=True)
    approve_parser.add_argument("--output", required=True, type=Path)
    render_parser = subcommands.add_parser("render")
    render_parser.add_argument("--plan", required=True, type=Path)
    render_parser.add_argument("--workspace", required=True, type=Path)
    qa_parser = subcommands.add_parser("qa")
    qa_parser.add_argument("--plan", required=True, type=Path)
    qa_parser.add_argument("--artifact", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "doctor":
            value = doctor()
        elif args.command == "plan":
            value = build_plan(load_json(args.request), args.workspace.resolve(), Path.cwd().resolve())
        elif args.command == "approve":
            value = approve(args.plan, args.reviewer, args.output)
        elif args.command == "render":
            value = render(args.plan, args.workspace.resolve())
        else:
            value = qa(args.plan, args.artifact)
        emit(value)
        return 0
    except EngineError as error:
        emit({"status": "failed", "error": str(error), "finishedAt": utc_now()})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
