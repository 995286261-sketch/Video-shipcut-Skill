#!/usr/bin/env python3
"""Prepare a traceable G4 editable-segment manifest from an approved G3 plan."""
import argparse
import hashlib
import json
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--source-pack", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--handle-ms", type=int, default=0)
    args = parser.parse_args()
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
    target_ms = int(plan.get("targetProfile", {}).get("targetDurationSec", 0) * 1000)
    result = {
        "schemaVersion": "0.2", "node": "G4", "projectId": plan["projectId"],
        "status": "prepared_for_render", "inputPlan": str(args.plan), "inputEvidence": str(args.evidence),
        "sourceAudioPolicy": "exclude", "segmentCount": len(rendered), "timelineDurationMs": cursor,
        "targetDurationMs": target_ms, "durationDeltaMs": cursor-target_ms,
        "segments": rendered,
        "renderRequirements": {"preserveSegmentBoundaries": True, "sourceAudio": "exclude", "flattenedPreview": "qa_only_not_chatcut_timeline_source"},
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = args.output_dir / "G4-可编辑工程-v0.2.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "prepared", "manifest": str(out), "segments": len(rendered), "timelineDurationMs": cursor, "durationDeltaMs": cursor-target_ms}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "invalid", "error": str(error)}, ensure_ascii=True))
        raise SystemExit(2)
