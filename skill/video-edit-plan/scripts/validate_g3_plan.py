#!/usr/bin/env python3
"""Validate traceability and G2 approval gates for a G3 edit-plan draft."""

import argparse
import json
from pathlib import Path


def fail(message: str) -> None:
    raise ValueError(message)


def normalized_ref(value: str) -> str:
    """Compare project-relative references consistently across Windows separators."""
    return value.replace("\\", "/").lstrip("./")


def validate_g2_decision(decision: dict, project_id: str, decision_path: Path) -> str:
    if decision.get("schemaVersion") != "0.1":
        fail("G2 decision schemaVersion must be 0.1")
    if decision.get("projectId") != project_id:
        fail("G2 decision projectId must match plan projectId")
    if decision.get("node") != "G2":
        fail("decision must belong to G2")
    if decision.get("status") != "approved_for_g3":
        fail("G2 decision is not approved_for_g3")
    approved = decision.get("approvedNarrationRef")
    if not isinstance(approved, str) or not approved.strip():
        fail("G2 decision requires approvedNarrationRef")
    for field in ("factCitationRef", "voiceBriefRef"):
        if not isinstance(decision.get(field), str) or not decision[field].strip():
            fail(f"G2 decision requires {field}")
    if not isinstance(decision.get("permittedFactIds"), list):
        fail("G2 decision requires permittedFactIds")
    if not isinstance(decision.get("prohibitedTopics"), list):
        fail("G2 decision requires prohibitedTopics")
    manually_verified = decision.get("userManuallyVerifiedClaims", [])
    if not isinstance(manually_verified, list) or not all(isinstance(item, str) and item.strip() for item in manually_verified):
        fail("userManuallyVerifiedClaims must be a list of non-empty strings")
    if manually_verified:
        provenance_rule = decision.get("provenanceRule")
        if not isinstance(provenance_rule, str) or "not" not in provenance_rule.lower() or "first" not in provenance_rule.lower():
            fail("manually verified claims require a provenanceRule stating they are not first-party verified")
    project_root = Path.cwd()
    approved_path = project_root / approved
    if not approved_path.is_file():
        fail(f"G2 approved narration does not exist: {approved}")
    for field in ("factCitationRef", "voiceBriefRef"):
        if not (project_root / decision[field]).is_file():
            fail(f"G2 decision reference does not exist: {decision[field]}")
    return normalized_ref(approved)


def validate_visual_analysis(manifest: dict, project_id: str, evidence: dict) -> None:
    if manifest.get("schemaVersion") != "0.1":
        fail("visual analysis schemaVersion must be 0.1")
    if manifest.get("projectId") != project_id:
        fail("visual analysis projectId must match plan projectId")
    if manifest.get("node") != "G3":
        fail("visual analysis must belong to G3")
    if manifest.get("status") != "completed":
        fail("visual analysis is not completed")
    if not isinstance(manifest.get("analysisScope"), str) or not manifest["analysisScope"].strip():
        fail("visual analysis requires analysisScope")
    targets = manifest.get("targetAssets")
    if not isinstance(targets, list) or not targets:
        fail("visual analysis requires targetAssets")
    known = {entry.get("assetId"): entry for entry in evidence.get("sourceEvidence", [])}
    for target in targets:
        if not isinstance(target, dict) or target.get("assetId") not in known:
            fail("visual analysis target assetId must exist in evidence")
        asset = known[target["assetId"]]
        if target.get("sha256", "").lower() != str(asset.get("sha256", "")).lower():
            fail(f"visual analysis SHA-256 does not match evidence for {target['assetId']}")
        keyframes = target.get("keyframes")
        if not isinstance(keyframes, list) or not keyframes:
            fail(f"visual analysis requires keyframes for {target['assetId']}")
        for frame in keyframes:
            if not isinstance(frame, dict) or not isinstance(frame.get("sourceMs"), int) or not isinstance(frame.get("analysisStatus"), str):
                fail("visual analysis keyframes require sourceMs and analysisStatus")
            if frame["analysisStatus"] not in {"completed", "failed", "timeout"}:
                fail("visual analysis keyframe analysisStatus is invalid")
            if frame["analysisStatus"] == "completed":
                if not isinstance(frame.get("observedVisuals"), str) or not frame["observedVisuals"].strip():
                    fail("completed visual analysis frame requires observedVisuals")
                if frame.get("identityStatus") not in {"confirmed", "uncertain", "not_present", "mixed"}:
                    fail("completed visual analysis frame requires valid identityStatus")


def validate_semantic_beats(beats_payload: dict, project_id: str, plan: dict, beats_path: Path) -> dict:
    if beats_payload.get("schemaVersion") != "0.1" or beats_payload.get("node") != "G3":
        fail("semantic beats must be a G3 schemaVersion 0.1 artifact")
    if beats_payload.get("projectId") != project_id:
        fail("semantic beats projectId must match plan projectId")
    if beats_payload.get("status") not in {"draft", "review_required", "approved"}:
        fail("semantic beats has an invalid status")
    beat_ref = plan.get("semanticBeatRef")
    if not isinstance(beat_ref, str) or normalized_ref(beat_ref) != normalized_ref(str(beats_path)):
        fail("plan semanticBeatRef must exactly identify --semantic-beats")
    beats = beats_payload.get("beats")
    if not isinstance(beats, list) or not beats:
        fail("semantic beats requires a non-empty beats list")
    result = {}
    for beat in beats:
        if not isinstance(beat, dict) or not isinstance(beat.get("beatId"), str):
            fail("semantic beats requires beatId values")
        if beat["beatId"] in result:
            fail("semantic beatId must be unique")
        start, end = beat.get("outputStartMs"), beat.get("outputEndMs")
        if not isinstance(start, int) or not isinstance(end, int) or end <= start:
            fail(f"semantic beat {beat['beatId']} has invalid output time range")
        result[beat["beatId"]] = beat
    return result


def validate_duration_decision(plan: dict) -> None:
    decision = plan.get("durationDecision")
    if not isinstance(decision, dict):
        fail("plan requires durationDecision")
    for field in ("targetDurationSec", "narrationEstimatedDurationSec"):
        value = decision.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            fail(f"durationDecision.{field} must be a positive number")
    if decision.get("resolution") not in {"preserve_target_with_editorial_padding", "follow_narration_natural_duration", "rewrite_narration"}:
        fail("durationDecision.resolution is invalid")
    if not isinstance(decision.get("decisionReason"), str) or not decision["decisionReason"].strip():
        fail("durationDecision.decisionReason is required")
    silence = decision.get("intentionalSilence")
    if not isinstance(silence, list):
        fail("durationDecision.intentionalSilence must be a list")
    for item in silence:
        if not isinstance(item, dict):
            fail("durationDecision.intentionalSilence entries must be objects")
        start, end = item.get("startMs"), item.get("endMs")
        if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
            fail("intentionalSilence requires a positive startMs/endMs range")
        if not isinstance(item.get("purpose"), str) or not item["purpose"].strip():
            fail("intentionalSilence requires purpose")
        if not isinstance(item.get("bgmPolicy"), str) or not item["bgmPolicy"].strip():
            fail("intentionalSilence requires bgmPolicy")
    anti_fill = decision.get("antiFillRule")
    required = ("disallowRepeatedSegments", "disallowLoops", "disallowMeaninglessSlowMotion", "disallowUnverifiedFactPadding")
    if not isinstance(anti_fill, dict) or any(anti_fill.get(field) is not True for field in required):
        fail("durationDecision.antiFillRule must prohibit repeated segments, loops, meaningless slow motion, and unverified fact padding")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--g2-decision", required=True, type=Path)
    parser.add_argument("--visual-analysis", required=True, type=Path)
    parser.add_argument("--semantic-beats", required=True, type=Path)
    args = parser.parse_args()
    # Windows editors commonly write UTF-8 with a BOM. Accept it at every JSON boundary.
    plan = json.loads(args.plan.read_text(encoding="utf-8-sig"))
    evidence = json.loads(args.evidence.read_text(encoding="utf-8-sig"))
    decision = json.loads(args.g2_decision.read_text(encoding="utf-8-sig"))
    visual_analysis = json.loads(args.visual_analysis.read_text(encoding="utf-8-sig"))
    semantic_beats = json.loads(args.semantic_beats.read_text(encoding="utf-8-sig"))
    if plan.get("schemaVersion") != "0.1":
        fail("plan schemaVersion must be 0.1")
    if plan.get("projectId") != evidence.get("projectId"):
        fail("plan projectId must match evidence projectId")
    plan_status = plan.get("status")
    if plan_status not in {"review_required", "approved_for_g4"}:
        fail("G3 plan status must be review_required or approved_for_g4")
    if plan.get("sourceAudioPolicy") != "exclude":
        fail("G3 plan must exclude source audio")
    validate_duration_decision(plan)
    validate_visual_analysis(visual_analysis, plan["projectId"], evidence)
    beat_index = validate_semantic_beats(semantic_beats, plan["projectId"], plan, args.semantic_beats)
    approved_narration_ref = validate_g2_decision(decision, plan["projectId"], args.g2_decision)
    narration_draft = plan.get("narrationDraft")
    if not isinstance(narration_draft, str) or normalized_ref(narration_draft) != approved_narration_ref:
        fail("plan narrationDraft must exactly match G2 approvedNarrationRef")
    if normalized_ref(narration_draft) in {normalized_ref(ref) for ref in decision.get("supersededDraftRefs", []) if isinstance(ref, str)}:
        fail("plan narrationDraft is superseded by the G2 decision")
    decision_ref = plan.get("narrationDecisionRef")
    if not isinstance(decision_ref, str) or normalized_ref(decision_ref) != normalized_ref(str(args.g2_decision)):
        fail("plan narrationDecisionRef must exactly identify --g2-decision")
    evidence_entries = evidence.get("sourceEvidence", [])
    known = {entry["assetId"]: entry["sourceProbe"]["durationMs"] for entry in evidence_entries}
    source_identity = {entry["assetId"]: str(entry.get("sha256") or entry["assetId"]).lower() for entry in evidence_entries}
    segments = plan.get("segments")
    if not isinstance(segments, list) or not segments:
        fail("plan requires non-empty segments")
    ids = set()
    for segment in segments:
        segment_id = segment.get("segmentId")
        if not isinstance(segment_id, str) or segment_id in ids:
            fail("segmentId must be unique")
        ids.add(segment_id)
        asset_id = segment.get("assetId")
        if asset_id not in known:
            fail(f"unknown assetId: {asset_id}")
        start, end = segment.get("startMs"), segment.get("endMs")
        if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start or end > known[asset_id]:
            fail(f"invalid source timecode for {segment_id}")
        if not segment.get("reason") or not segment.get("evidenceRefs"):
            fail(f"segment {segment_id} requires reason and evidenceRefs")
        visual = segment.get("visualVerification")
        if not isinstance(visual, dict) or visual.get("status") != "verified":
            fail(f"segment {segment_id} requires verified visualVerification; candidate timecodes cannot enter G4")
        if not isinstance(visual.get("frameManifestRef"), str) or not visual["frameManifestRef"].strip():
            fail(f"segment {segment_id} visualVerification requires frameManifestRef")
        frame_refs = visual.get("frameRefs")
        if not isinstance(frame_refs, list) or len(frame_refs) < 3 or not all(isinstance(ref, str) and ref.strip() for ref in frame_refs):
            fail(f"segment {segment_id} visualVerification requires start/middle/end frameRefs")
        observed = visual.get("observedVisuals")
        if not isinstance(observed, str) or not observed.strip() or any(term in observed.lower() for term in ("希望出现", "想要", "wish", "want to show")):
            fail(f"segment {segment_id} observedVisuals must describe actual frames, not a desired shot")
        narration_start = segment.get("narrationStartMs")
        narration_end = segment.get("narrationEndMs")
        narration_text = segment.get("narrationText")
        narrative_claim = segment.get("narrativeClaim")
        semantic = segment.get("semanticAlignment")
        beat_ids = segment.get("semanticBeatIds")
        if not isinstance(beat_ids, list) or not beat_ids or not all(isinstance(beat_id, str) and beat_id in beat_index for beat_id in beat_ids):
            fail(f"segment {segment_id} requires semanticBeatIds from the semantic beat table")
        if not any(segment.get("outputStartMs", 0) < beat_index[beat_id]["outputEndMs"] and segment.get("outputEndMs", 0) > beat_index[beat_id]["outputStartMs"] for beat_id in beat_ids):
            fail(f"segment {segment_id} does not overlap its semantic beat output range")
        if not isinstance(narration_start, int) or not isinstance(narration_end, int) or narration_start < 0 or narration_end <= narration_start:
            fail(f"segment {segment_id} requires positive narrationStartMs/narrationEndMs")
        if not isinstance(narration_text, str) or not narration_text.strip():
            fail(f"segment {segment_id} requires narrationText")
        if not isinstance(narrative_claim, dict) or not isinstance(narrative_claim.get("type"), str) or not isinstance(narrative_claim.get("minimumVisibleEvidence"), str) or not narrative_claim["minimumVisibleEvidence"].strip():
            fail(f"segment {segment_id} requires narrativeClaim type and minimumVisibleEvidence")
        if not isinstance(semantic, dict) or semantic.get("status") not in {"direct_match", "partial_match", "semantic_mismatch", "not_applicable"}:
            fail(f"segment {segment_id} requires a valid semanticAlignment status")
        if not isinstance(semantic.get("evidence"), str) or not semantic["evidence"].strip():
            fail(f"segment {segment_id} semanticAlignment requires actual visual evidence")
        if semantic["status"] in {"partial_match", "semantic_mismatch"} and plan_status == "approved_for_g4":
            fail(f"approved segment {segment_id} cannot have {semantic['status']}")
        if plan_status == "approved_for_g4":
            mapping = segment.get("mappingMode", "one_to_one")
            source_duration = end - start
            output_start = segment.get("outputStartMs")
            output_end = segment.get("outputEndMs")
            output_duration = segment.get("outputDurationMs")
            if not isinstance(output_start, int) or not isinstance(output_end, int) or output_end <= output_start:
                fail(f"approved segment {segment_id} requires positive outputStartMs/outputEndMs")
            if not isinstance(output_duration, int) or output_duration != output_end - output_start:
                fail(f"segment {segment_id} outputDurationMs must match output timeline")
            if mapping not in {"one_to_one", "trim"}:
                fail(f"segment {segment_id} mappingMode is not allowed")
            if mapping == "one_to_one" and output_duration != source_duration:
                fail(f"segment {segment_id} one_to_one output/source durations differ")
            if mapping == "trim" and output_duration > source_duration:
                fail(f"segment {segment_id} trim cannot extend source duration")
    ranges = {}
    for segment in segments:
        key = source_identity[segment["assetId"]]
        ranges.setdefault(key, []).append((segment["startMs"], segment["endMs"], segment["segmentId"]))
    for source_key, items in ranges.items():
        items.sort()
        for previous, current in zip(items, items[1:]):
            if current[0] < previous[1]:
                overlap = min(previous[1], current[1]) - current[0]
                fail(f"source range overlap for {previous[2]} and {current[2]} on {source_key}: {overlap}ms")
    timeline = plan.get("editPlan", {}).get("timeline", [])
    timeline_ids = [entry.get("segmentId") for entry in timeline]
    if not timeline_ids or any(segment_id not in ids for segment_id in timeline_ids):
        fail("editPlan timeline must reference declared segments")
    if len(timeline_ids) != len(set(timeline_ids)):
        fail("editPlan timeline cannot repeat a segment to fill duration")
    for entry in timeline:
        if entry.get("loop") is True or entry.get("duplicateFill") is True:
            fail("editPlan timeline cannot use loops or duplicate fill")
        slow_motion = entry.get("slowMotion")
        if slow_motion is not None and not isinstance(entry.get("purpose"), str):
            fail("slowMotion requires a documented purpose")
    if not plan.get("humanReviewPoints"):
        fail("plan requires narrationDraft and humanReviewPoints")
    if plan_status == "approved_for_g4":
        review = plan.get("timelineReview")
        if not isinstance(review, dict) or review.get("status") != "confirmed":
            fail("approved_for_g4 plan requires confirmed timelineReview")
        for field in ("confirmedBy", "confirmedAt", "feedback", "basisRefs"):
            if not review.get(field):
                fail(f"approved_for_g4 plan requires timelineReview.{field}")
        if not isinstance(review["basisRefs"], list) or not all(isinstance(ref, str) and ref.strip() for ref in review["basisRefs"]):
            fail("timelineReview.basisRefs must be a non-empty list of references")
        if any(segment.get("status") in {"pending", "verified_candidate"} or segment.get("visualVerification", {}).get("status") != "verified" for segment in segments):
            fail("approved_for_g4 plan cannot contain pending or verified_candidate segments")
        approval = plan.get("g3Approval")
        if not isinstance(approval, dict):
            fail("approved_for_g4 plan requires g3Approval")
        for field in ("approvedBy", "approvedAt", "basisRefs"):
            if not approval.get(field):
                fail(f"approved_for_g4 plan requires g3Approval.{field}")
        if not isinstance(approval["basisRefs"], list) or not all(isinstance(ref, str) and ref.strip() for ref in approval["basisRefs"]):
            fail("g3Approval.basisRefs must be a non-empty list of references")
    print(json.dumps({"status": "completed", "segments": len(segments), "planStatus": plan_status, "reviewRequired": plan_status == "review_required"}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        # Keep failures machine-readable and safe for Windows console encodings.
        print(json.dumps({"status": "invalid", "error": str(error)}, ensure_ascii=True))
        raise SystemExit(2)
