#!/usr/bin/env python3
"""Validate a G5 delivery bundle without needing its raw source media."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


REQUIRED = ("final-video.mp4", "cover.jpg", "subtitles.srt", "subtitle-srt-check.json", "source-timecode-list.json", "edit-plan.json", "edit-timeline.md", "export-config.json", "metadata-validation-report.json", "human-review-decision.json", "delivery-manifest.json", "README.md", "failure-samples/README.md")
CONTRACT_FIELDS = ("schemaVersion", "projectId", "sourceProbe", "segments", "editPlan", "artifacts", "qaReport", "humanReviewPoints", "evidenceRefs", "warnings", "status", "finishedAt")
QA_CHECKS = ("decode", "videoCodec", "dimensions", "fps", "audio", "duration", "blackFrames", "silence", "duplicateSegments", "cover")


def check_delivery_srt(bundle: Path, errors: list[str]) -> None:
    """SRT format rules belong to subtitle-expert (issue ㊍: a 10× timebase slip once
    shipped in a bundle). G5 holds no private timestamp regex; it consumes the
    specialist's report — same artifact-handshake pattern as G0's BGM registration
    receipt: report present, status passed, and its sha256 still matches the bundle
    file (freshness, per ⑦ lesson: a receipt must describe THIS file)."""
    report_path = bundle / "subtitle-srt-check.json"
    if not report_path.is_file():
        errors.append("missing subtitle-srt-check.json — run subtitle-expert/scripts/subtitle_check_srt.py on subtitles.srt and file the report before closing QA")
        return
    report = load(report_path)
    if report.get("skill") != "subtitle-expert" or report.get("purpose") != "subtitle_check_srt":
        errors.append("subtitle-srt-check.json is not a subtitle-expert check report")
        return
    if report.get("status") != "passed":
        errors.append(f"subtitles.srt failed subtitle-expert check: status={report.get('status')} {('; '.join(report.get('errors', [])) or report.get('error') or '')[:200]}")
        return
    srt = bundle / "subtitles.srt"
    if not srt.is_file():
        errors.append("subtitle-srt-check.json present but subtitles.srt missing")
        return
    if str(report.get("sha256", "")).upper() != digest(srt):
        errors.append("subtitle-srt-check.json is stale: recorded sha256 does not match the bundle's subtitles.srt (re-run the specialist checker after any edit)")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest().upper()


def inside(bundle: Path, relative: str) -> Path | None:
    path = (bundle / relative).resolve()
    return path if path == bundle or bundle in path.parents else None


def check_artifact(bundle: Path, artifact: dict, errors: list[str]) -> None:
    path = artifact.get("path")
    target = inside(bundle, path) if isinstance(path, str) else None
    if not target or not target.is_file():
        errors.append(f"missing artifact: {path}")
    elif artifact.get("sha256") and digest(target) != artifact["sha256"].upper():
        errors.append(f"sha256 mismatch: {path}")


def fraction(value: str | None) -> float | None:
    if not value or value == "0/0": return None
    numerator, denominator = value.split("/", 1)
    return float(numerator) / float(denominator) if float(denominator) else None


def validate_media(bundle: Path, export: dict, errors: list[str]) -> None:
    video = bundle / "final-video.mp4"
    result = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        errors.append("final-video.mp4 cannot be fully decoded")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name,width,height,r_frame_rate", "-of", "json", str(video)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if probe.returncode:
        errors.append("final-video.mp4 cannot be probed")
    else:
        streams = json.loads(probe.stdout).get("streams", [])
        visual = next((item for item in streams if item.get("codec_type") == "video"), None)
        audio = [item for item in streams if item.get("codec_type") == "audio"]
        profile = export.get("video", {})
        audio_profile = export.get("audio", {})
        if not visual:
            errors.append("final-video.mp4 has no video stream")
        else:
            if profile.get("codec") and visual.get("codec_name") != profile["codec"]:
                errors.append("final-video.mp4 codec does not match export-config")
            if profile.get("width") and visual.get("width") != profile["width"] or profile.get("height") and visual.get("height") != profile["height"]:
                errors.append("final-video.mp4 dimensions do not match export-config")
            actual_fps, expected_fps = fraction(visual.get("r_frame_rate")), profile.get("fps")
            if expected_fps and (actual_fps is None or abs(actual_fps - float(expected_fps)) > .1):
                errors.append("final-video.mp4 fps does not match export-config")
            actual_ms = round(float(json.loads(probe.stdout).get("format", {}).get("duration", 0)) * 1000)
            expected_ms = profile.get("durationActualMs")
            if expected_ms and abs(actual_ms - expected_ms) > 150:
                errors.append("final-video.mp4 duration does not match export-config")
        if audio_profile.get("codec") and (len(audio) != 1 or audio[0].get("codec_name") != audio_profile["codec"]):
            errors.append("final-video.mp4 audio does not match export-config")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--media", action="store_true", help="Also decode and probe final-video.mp4 with FFmpeg")
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    errors: list[str] = []
    for name in REQUIRED:
        if not (bundle / name).is_file(): errors.append(f"missing required file: {name}")
    if errors:
        print(json.dumps({"status": "invalid", "errors": errors}, ensure_ascii=True)); return 2
    try:
        manifest, trace, plan = load(bundle / "delivery-manifest.json"), load(bundle / "source-timecode-list.json"), load(bundle / "edit-plan.json")
        qa, review, export = load(bundle / "metadata-validation-report.json"), load(bundle / "human-review-decision.json"), load(bundle / "export-config.json")
    except json.JSONDecodeError as error:
        print(json.dumps({"status": "invalid", "errors": [f"invalid JSON: {error}"]}, ensure_ascii=True)); return 2
    # Issue 002-⑬: the contract already allows "finishedAt OR explicit pending status"
    # (qa-contract); a pending-human-review manifest legitimately has no QA close time yet.
    manifest_status = str(manifest.get("status") or "")
    for field in CONTRACT_FIELDS:
        if field == "finishedAt" and manifest_status.startswith("pending"):
            continue
        if manifest.get(field) in (None, "", [], {}): errors.append(f"delivery manifest missing {field}")
    project_id = manifest.get("projectId")
    for label, data in (("traceability", trace), ("edit plan", plan), ("qa", qa), ("human review", review), ("export config", export)):
        if data.get("projectId") != project_id: errors.append(f"projectId mismatch: {label}")
    if manifest.get("schemaVersion") != "0.1": errors.append("unsupported delivery manifest schemaVersion")
    if not all(item.get("assetId") and item.get("sourceProbe") for item in manifest.get("sourceProbe", [])):
        errors.append("sourceProbe entries are incomplete")
    segments = {item.get("segmentId"): item for item in trace.get("segments", [])}
    if not segments or {item.get("segmentId") for item in manifest.get("segments", [])} != set(segments): errors.append("manifest segments do not match traceability")
    for item in segments.values():
        if not item.get("assetId") or not item.get("sourceSha256") or not isinstance(item.get("sourceStartMs"), (int, float)) or item.get("sourceEndMs", 0) <= item.get("sourceStartMs", 0): errors.append(f"invalid source traceability: {item.get('segmentId')}")
    chapters = trace.get("chapters", [])
    if not 3 <= len(chapters) <= 5: errors.append("chapter clip count must be 3 to 5")
    for chapter in chapters:
        output = chapter.get("output"); target = inside(bundle, output) if isinstance(output, str) else None
        if not target or not target.is_file(): errors.append(f"missing chapter output: {output}")
        # Issue ㉜: segments entries may be bare IDs or objects carrying segmentId;
        # normalize before hashing, or a dict crashes the whole validator.
        refs = [item if isinstance(item, str) else item.get("segmentId") for item in chapter.get("segments", []) if isinstance(item, (str, dict))]
        if not refs or not set(refs).issubset(segments): errors.append(f"chapter traceability failed: {chapter.get('chapterId')}")
    for item in [qa.get("artifacts", {}).get("finalVideo", {}), qa.get("artifacts", {}).get("cover", {}), qa.get("artifacts", {}).get("subtitles", {}), manifest.get("artifacts", {}).get("editTimeline", {})] + qa.get("artifacts", {}).get("chapterClips", []): check_artifact(bundle, item, errors)
    if not set(QA_CHECKS).issubset(qa.get("checks", {})): errors.append("qa report lacks required machine checks")
    check_delivery_srt(bundle, errors)
    if manifest.get("status", "").startswith("completed") and not (review.get("status") == "approved" and review.get("decision") == "accepted"):
        errors.append("completed bundle lacks accepted human review")
    if manifest.get("authorization") in (None, "") or manifest.get("distribution") in (None, ""): errors.append("authorization or distribution boundary missing")
    if args.media: validate_media(bundle, export, errors)
    result = {"status": "valid" if not errors else "invalid", "projectId": project_id, "chapters": len(chapters), "segments": len(segments), "errors": errors}
    print(json.dumps(result, ensure_ascii=True)); return 0 if not errors else 2


if __name__ == "__main__":
    try: raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "invalid", "errors": [str(error)]}, ensure_ascii=True)); raise SystemExit(2)
