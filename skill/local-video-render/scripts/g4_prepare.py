#!/usr/bin/env python3
"""Prepare a traceable G4 editable-segment manifest from an approved G3 plan."""
import argparse
import hashlib
import json
import re
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def fail(message: str) -> None:
    raise ValueError(message)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


# Mirrors p0-c-pipeline/project_layout.py by contract (skills never import each other).
G4_DIRECTORY = "G4-剪辑与渲染"
WORKBENCH_DIRECTORY = "工作台"


def enforce_g4_root(plan_path: Path, output_dir: Path) -> None:
    """Issue ㉚: a plan that lives inside a formal project (工作台/<projectId>/...)
    can only produce artifacts G4 approval will accept when they sit under that
    project's canonical G4 directory. Deriving the target from --output-dir
    alone let tiger-intro-001 land in a wrongly-named directory, which only
    surfaced at approve time. Non-工作台 plans (temp fixtures) stay unmanaged."""
    resolved = plan_path.resolve()
    project_root = None
    for parent in resolved.parents:
        if parent.parent is not None and parent.parent.name == WORKBENCH_DIRECTORY:
            project_root = parent
            break
    if project_root is None:
        return
    expected = project_root / G4_DIRECTORY
    actual = output_dir.resolve()
    if actual != expected and expected not in actual.parents:
        fail(f"--output-dir must be the project's G4 directory ({expected} or a subdirectory), got {actual}; "
             "G4 approval only accepts artifacts under the active G4 directory (issue ㉚)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--source-pack", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--handle-ms", type=int, default=0)
    parser.add_argument("--force", action="store_true", help="overwrite an existing derived manifest intentionally")
    args = parser.parse_args()
    enforce_g4_root(args.plan, args.output_dir)
    plan, evidence, pack_manifest = load(args.plan), load(args.evidence), load(args.source_pack / "material-pack.json")
    if plan.get("status") != "approved_for_g4":
        fail("G4 requires plan status approved_for_g4")
    if plan.get("projectId") != evidence.get("projectId"):
        fail("plan and evidence projectId must match")
    if plan.get("sourceAudioPolicy") != "exclude":
        fail("G4 requires sourceAudioPolicy exclude")
    if args.handle_ms < 0:
        fail("handle-ms must be non-negative")
    evidence_by_id = {item.get("assetId"): item for item in evidence.get("sourceEvidence", [])}
    pack_by_id = {item.get("assetId"): item for item in pack_manifest.get("sourceAssets", [])}
    declared = {item.get("segmentId"): item for item in plan.get("segments", [])}
    timeline = plan.get("editPlan", {}).get("timeline", [])
    order = [item.get("segmentId") for item in timeline]
    timeline_by_id = {item.get("segmentId"): item for item in timeline}
    if not order or len(order) != len(declared) or len(set(order)) != len(order):
        fail("editPlan timeline must contain every declared segment exactly once")
    source_ranges = {}
    rendered, cursor = [], 0
    for index, segment_id in enumerate(order, 1):
        segment = declared.get(segment_id)
        if not segment:
            fail(f"timeline references unknown segment {segment_id}")
        visual = segment.get("visualVerification")
        if not isinstance(visual, dict) or visual.get("status") != "verified":
            fail(f"segment {segment_id} lacks verified visual evidence; G4 refuses guessed timecodes")
        if not isinstance(visual.get("frameManifestRef"), str) or not visual.get("frameRefs") or not visual.get("observedVisuals"):
            fail(f"segment {segment_id} has incomplete visual verification")
        source = evidence_by_id.get(segment.get("assetId"))
        if not source:
            fail(f"segment {segment_id} has no evidence asset")
        registered = pack_by_id.get(segment.get("assetId"), {})
        relative = source.get("relativePath") or registered.get("relativePath")
        path = (args.source_pack / relative).resolve()
        if not relative or not path.is_file() or args.source_pack.resolve() not in path.parents:
            fail(f"registered source missing for {segment_id}: {relative}")
        expected_hash = source.get("sha256") or registered.get("sha256")
        if not expected_hash:
            fail(f"registered source lacks sha256 for {segment_id}")
        if sha256(path) != expected_hash.upper():
            fail(f"source hash mismatch for {segment_id}")
        start, end = segment.get("startMs"), segment.get("endMs")
        if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
            fail(f"invalid source timecode for {segment_id}")
        duration = end - start
        source_key = str(source.get("sha256") or segment.get("assetId")).lower()
        existing_ranges = source_ranges.setdefault(source_key, [])
        for prior_start, prior_end, prior_id in existing_ranges:
            if start < prior_end and end > prior_start:
                fail(f"source range overlap for {prior_id} and {segment_id}")
        existing_ranges.append((start, end, segment_id))
        source_duration = source.get("sourceProbe", {}).get("durationMs")
        if not isinstance(source_duration, int) or end > source_duration:
            fail(f"timecode outside registered source for {segment_id}")
        handle_start, handle_end = max(0, start - args.handle_ms), min(source_duration, end + args.handle_ms)
        edit_timeline = timeline_by_id[segment_id]
        output_duration = edit_timeline.get("timelineEndMs", edit_timeline.get("timelineStartMs", 0) + duration) - edit_timeline.get("timelineStartMs", 0)
        if not isinstance(output_duration, int) or output_duration <= 0:
            fail(f"invalid output timeline duration for {segment_id}")
        if output_duration > duration:
            fail(f"output duration exceeds approved source range for {segment_id}")
        rendered.append({
            "segmentId": segment_id,
            "order": index,
            "assetId": segment["assetId"],
            "source": {"relativePath": relative, "sha256": expected_hash, "startMs": start, "endMs": end, "durationMs": duration},
            "timeline": {"startMs": cursor, "endMs": cursor + output_duration, "durationMs": output_duration},
            "mapping": {"mode": segment.get("mappingMode", "one_to_one"), "playbackRate": 1.0, "freeze": None, "padding": None},
            "editableSource": {"startMs": handle_start, "endMs": handle_end, "handleBeforeMs": start-handle_start, "handleAfterMs": handle_end-end},
            "output": {"filename": f"seg-{index:03d}.mp4", "audio": "excluded", "subtitleTreatment": "per G3 source-subtitle policy"},
            "riskFlags": segment.get("riskFlags", []),
        })
        cursor += output_duration
    # Issue 025: the authoritative target duration is the user-approved durationDecision,
    # not an optional targetProfile; a missing decision must block instead of yielding 0ms.
    decision_target = plan.get("durationDecision", {}).get("targetDurationSec")
    profile_target = plan.get("targetProfile", {}).get("targetDurationSec")
    target_seconds = decision_target if isinstance(decision_target, (int, float)) and not isinstance(decision_target, bool) and decision_target > 0 else profile_target
    if not isinstance(target_seconds, (int, float)) or isinstance(target_seconds, bool) or target_seconds <= 0:
        fail("plan lacks a positive durationDecision.targetDurationSec; G4 refuses to prepare with a zero target (issue 025)")
    target_ms = int(target_seconds * 1000)
    # Issue 002-⑨: the approved plan's frame rate is a machine fact; carry it into the
    # manifest so render and assembly inherit it instead of silently defaulting to 24.
    edit_fps = plan.get("editPlan", {}).get("fps")
    if edit_fps is not None and (not isinstance(edit_fps, int) or isinstance(edit_fps, bool) or edit_fps <= 0):
        fail("editPlan.fps must be a positive integer when present (issue 002-⑨)")
    result = {
        "schemaVersion": "0.2", "node": "G4", "projectId": plan["projectId"],
        "status": "prepared_for_render", "inputPlan": str(args.plan), "inputEvidence": str(args.evidence),
        "durationDecisionRef": "plan.durationDecision" if decision_target else "plan.targetProfile",
        "sourceAudioPolicy": "exclude", "segmentCount": len(rendered), "timelineDurationMs": cursor,
        "targetDurationMs": target_ms, "durationDeltaMs": cursor-target_ms, "targetFps": edit_fps,
        "segments": rendered,
        "renderRequirements": {"preserveSegmentBoundaries": True, "sourceAudio": "exclude", "flattenedPreview": "qa_only_not_chatcut_timeline_source"},
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    # Issue 029: derive the manifest version from the input plan filename so reruns never
    # silently overwrite the previous batch's manifest.
    version_match = re.search(r"v(\d+(?:\.\d+)?)", args.plan.name)
    version = f"v{version_match.group(1)}" if version_match else "v0.1"
    out = args.output_dir / f"G4-可编辑工程-{version}.json"
    if out.exists() and not args.force:
        fail(f"{out.name} already exists; pass --force to overwrite intentionally (issue 029)")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "prepared", "manifest": str(out), "segments": len(rendered), "timelineDurationMs": cursor, "durationDeltaMs": cursor-target_ms}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "invalid", "error": str(error)}, ensure_ascii=True))
        raise SystemExit(2)
