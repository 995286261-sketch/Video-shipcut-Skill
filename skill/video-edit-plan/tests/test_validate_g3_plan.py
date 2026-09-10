import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skill" / "video-edit-plan" / "scripts" / "validate_g3_plan.py"
PYTHON = Path(sys.executable)
AUDIO_SHA = "A" * 64


class ValidateG3PlanTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.narration = self.root / "approved.md"
        self.facts = self.root / "facts.md"
        self.voice = self.root / "voice.md"
        for path in (self.narration, self.facts, self.voice):
            path.write_text("fixture", encoding="utf-8")
        self.source_pack = self.root / "G0-素材包"
        self.source = self.source_pack / "clip.mp4"
        self.source.parent.mkdir()
        self.source.write_bytes(b"fixture")
        self.evidence_path = self.write_json("evidence.json", {
            "projectId": "demo-001",
            "sourceEvidence": [{"assetId": "clip-1", "relativePath": "clip.mp4", "sha256": "fixture-sha", "sourceProbe": {"durationMs": 10_000}}],
        })
        self.visual_analysis_path = self.write_json("visual-analysis.json", {
            "schemaVersion": "0.1", "projectId": "demo-001", "node": "G3", "status": "completed", "analysisScope": "fixture",
            "targetAssets": [{"assetId": "clip-1", "sha256": "fixture-sha", "keyframes": [{"sourceMs": 0, "analysisStatus": "completed", "identityStatus": "uncertain", "observedVisuals": "fixture frame"}]}],
        })
        self.semantic_beats_path = self.write_json("semantic-beats.json", {
            "schemaVersion": "0.1", "projectId": "demo-001", "node": "G3", "status": "draft",
            "narrationDraft": str(self.narration), "narrationDecisionRef": "decision.json", "timingBasis": "fixture",
            "beats": [{"beatId": "beat-001", "outputStartMs": 0, "outputEndMs": 1_000, "narrationText": "展示主体。", "claim": {"type": "object", "minimumVisibleEvidence": ["目标主体可辨认。"]}, "allowedVisualAlternatives": []}],
        })

    def write_json(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def decision(self, **changes):
        value = {
            "schemaVersion": "0.1", "projectId": "demo-001", "node": "G2",
            "status": "approved_for_g3", "approvedNarrationRef": str(self.narration),
            "factCitationRef": str(self.facts), "voiceBriefRef": str(self.voice),
            "permittedFactIds": ["f1"], "prohibitedTopics": [], "supersededDraftRefs": ["old.md"],
        }
        value.update(changes)
        return self.write_json("decision.json", value)

    def plan(self, decision_path, **changes):
        value = {
            "schemaVersion": "0.1", "projectId": "demo-001", "status": "review_required",
            "sourceAudioPolicy": "exclude", "narrationDraft": str(self.narration),
            "narrationDecisionRef": str(decision_path), "semanticBeatRef": str(self.semantic_beats_path), "humanReviewPoints": ["review"],
            "durationDecision": {"targetDurationSec": 10, "narrationEstimatedDurationSec": 8, "resolution": "preserve_target_with_editorial_padding", "decisionReason": "fixture permits a short deliberate outro.", "intentionalSilence": [{"startMs": 8_000, "endMs": 10_000, "purpose": "outro", "bgmPolicy": "approved_bgm_fade_out"}], "antiFillRule": {"disallowRepeatedSegments": True, "disallowLoops": True, "disallowMeaninglessSlowMotion": True, "disallowUnverifiedFactPadding": True}},
            "segments": [{"segmentId": "s1", "assetId": "clip-1", "startMs": 0, "endMs": 1_000, "outputStartMs": 0, "outputEndMs": 1_000, "outputDurationMs": 1_000, "mappingMode": "one_to_one", "reason": "fixture", "evidenceRefs": ["f1"], "semanticBeatIds": ["beat-001"], "narrationStartMs": 0, "narrationEndMs": 1_000, "narrationText": "展示主体。", "narrativeClaim": {"type": "object", "minimumVisibleEvidence": "目标主体在画面内可辨认。"}, "semanticAlignment": {"status": "direct_match", "evidence": "起点、中点和终点帧均可辨认目标主体。"}, "visualVerification": {"status": "verified", "frameManifestRef": "G3-visual-verification-frames.json", "frameRefs": ["start.jpg", "middle.jpg", "end.jpg"], "observedVisuals": "已查看起点、中点和终点帧，主体位于画面中央。", "verifiedBy": "agent", "verifiedAt": "2026-08-20T00:00:00Z"}}],
            "editPlan": {"timeline": [{"segmentId": "s1"}]},
        }
        value.update(changes)
        return self.write_json("plan.json", value)

    def subject_confirmation(self, **changes):
        value = {
            "schemaVersion": "0.1", "projectId": "demo-001", "node": "G3",
            "targetSubject": {
                "canonicalName": "测试主体", "userConfirmed": True,
                "identificationRules": ["起点、中点和终点可见测试主体。"],
                "exclusionRules": ["模糊或其他主体不得自动认定。"],
            },
            "candidateVerificationRule": "每个候选均须核验三帧。",
        }
        if "targetSubject" in changes:
            value["targetSubject"] = changes.pop("targetSubject")
        value.update(changes)
        return self.write_json("subject-confirmation.json", value)

    def ledger(self, records=None):
        value = {"schemaVersion": "0.1", "node": "G3", "projectId": "demo-001", "records": records if records is not None else [
            {"recordId": "obs-active", "sourceAssetId": "clip-1", "sourceSha256": "fixture-sha", "sourceMs": 0, "frameExtractionSpec": "fixture", "analysisPromptVersion": "v1", "provider": "local", "model": "vision", "analysisStatus": "completed", "frameRef": "start.jpg", "observedVisuals": "主体可见", "createdAt": "2026-09-08T00:00:00Z"},
            {"recordId": "obs-001", "sourceAssetId": "clip-1", "sourceSha256": "fixture-sha", "sourceMs": 500, "frameExtractionSpec": "fixture", "analysisPromptVersion": "v1", "provider": "local", "model": "vision", "analysisStatus": "completed", "frameRef": "middle.jpg", "observedVisuals": "旧主体判断", "createdAt": "2026-09-08T00:00:00Z"},
            {"recordId": "obs-002", "sourceAssetId": "clip-1", "sourceSha256": "fixture-sha", "sourceMs": 500, "frameExtractionSpec": "fixture", "analysisPromptVersion": "v1", "provider": "local", "model": "vision", "analysisStatus": "completed", "frameRef": "middle.jpg", "observedVisuals": "用户改判后的主体状态", "supersedesRecordId": "obs-001", "correctionSource": "用户指认", "createdAt": "2026-09-08T00:00:01Z"},
        ]}
        by_id = {record["recordId"]: record for record in value["records"]}
        for record in value["records"]:
            target = record.get("supersedesRecordId")
            if target in by_id:
                by_id[target]["analysisStatus"] = "superseded"
                by_id[target]["supersededBy"] = record["recordId"]
        return self.write_json("ledger.json", value)

    def run_cli(self, plan, decision, subject=None, ledger=None, bgm=None):
        command = [str(PYTHON), str(SCRIPT), "--plan", str(plan), "--evidence", str(self.evidence_path), "--g2-decision", str(decision), "--visual-analysis", str(self.visual_analysis_path), "--semantic-beats", str(self.semantic_beats_path)]
        if subject:
            command += ["--subject-confirmation", str(subject)]
        if ledger:
            command += ["--ledger", str(ledger)]
        if bgm:
            pack_path, alignment_path = bgm
            if pack_path:
                command += ["--material-pack", str(pack_path)]
            if alignment_path:
                command += ["--bgm-alignment", str(alignment_path)]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
        return result.returncode, result.stdout + result.stderr

    def enable_bgm_chain(self, plan_path):
        """Build a G0-style audio→report→alignment machine chain and wire the
        plan's bgmPlan to it; returns (bgm plan path, pack manifest, alignment)."""
        report_dir = self.source_pack / "07_授权音频"
        report_dir.mkdir(exist_ok=True)
        report_path = report_dir / "BGM-分析报告-test.json"
        report_path.write_text(json.dumps({"cacheKey": {"sha256": AUDIO_SHA, "analysisVersion": "music-expert-analysis-v0.2"}}), encoding="utf-8")
        report_sha = hashlib.sha256(report_path.read_bytes()).hexdigest().upper()
        pack = self.source_pack / "material-pack.json"
        pack.write_text(json.dumps({"audioAssets": [{
            "sha256": AUDIO_SHA,
            "bgmRegistration": {"licenseType": "cleared-for-project", "relativePath": "07_授权音频/登记.json"},
            "bgmAnalysis": {"relativePath": "07_授权音频/BGM-分析报告-test.json", "sha256": report_sha},
        }]}), encoding="utf-8")
        fades = {"fadeInMs": 500, "fadeOutStartMs": 500, "fadeOutMs": 500}
        alignment = self.root / "BGM-对齐建议-v0.2.json"
        alignment.write_text(json.dumps({
            "schemaVersion": "0.2", "purpose": "bgm_alignment", "skill": "music-expert",
            "inputs": {"reportCacheKey": {"sha256": AUDIO_SHA}},
            "alignment": {"offsetMs": 60_000, "timelineMs": 1_000},
            "boundaries": [{"sentenceId": "N01", "startMs": 0, "endMs": 1_000}],
            "layout": {"tierVocabulary": ["快切", "推进", "常规", "留白"], "phrasesOnTimeline": []},
            "snapped": [{}, {}], "missed": [{}],
            "ducking": [{"sentenceId": "N01"}], "fades": fades,
        }), encoding="utf-8")
        alignment_sha = hashlib.sha256(alignment.read_bytes()).hexdigest().upper()
        content = json.loads(plan_path.read_text(encoding="utf-8"))
        content["timelineDurationMs"] = 1_000
        content["segments"][0]["layoutTier"] = "推进"
        content["bgmPlan"] = {
            "audioSha256": AUDIO_SHA, "reportSha256": report_sha, "alignmentSha256": alignment_sha,
            "alignmentRef": str(alignment), "trackOffsetMs": 60_000, "fades": fades,
            "duckingPolicy": "旁白优先，句内 BGM 压低（深度参数待 §6-② 拍板）",
        }
        return self.write_json("plan-bgm.json", content), pack, alignment

    def test_valid_g2_decision_is_consumable_by_g3(self):
        decision = self.decision()
        validator = ROOT / "skill" / "media-evidence-prep" / "scripts" / "validate_g2_decision.py"
        result = subprocess.run([str(PYTHON), str(validator), "--decision", str(decision), "--project-root", str(self.root)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        code, output = self.run_cli(self.plan(decision), decision)
        self.assertEqual(0, code, output)

    def test_legacy_approval_field_names_are_rejected(self):
        value = {
            "schemaVersion": "0.1", "projectId": "demo-001", "node": "G2", "status": "approved_for_g3",
            "approvedNarrationRef": str(self.narration), "factDecisionRef": str(self.facts),
            "voiceDecisionRef": str(self.voice), "permittedFactIds": ["f1"], "prohibitedTopics": [],
        }
        decision = self.write_json("legacy-decision.json", value)
        code, output = self.run_cli(self.plan(decision), decision)
        self.assertNotEqual(0, code)
        self.assertIn("factCitationRef", output)

    def test_directory_approval_reference_is_rejected(self):
        decision = self.decision(factCitationRef=str(self.root))
        code, output = self.run_cli(self.plan(decision), decision)
        self.assertNotEqual(0, code)
        self.assertIn("existing project file", output)

    def test_evidence_must_expose_relative_path_for_g3_consumers(self):
        value = json.loads(self.evidence_path.read_text(encoding="utf-8"))
        del value["sourceEvidence"][0]["relativePath"]
        self.evidence_path.write_text(json.dumps(value), encoding="utf-8")
        decision = self.decision()
        verification_plan = self.plan(decision)
        for script, extra in ((ROOT / "skill/video-edit-plan/scripts/g3_extract_verification_frames.py", ("--plan", str(verification_plan))), (ROOT / "skill/video-edit-plan/scripts/g3_extract_visual_analysis_keyframes.py", ("--asset-id", "clip-1"))):
            result = subprocess.run([str(PYTHON), str(script), "--evidence", str(self.evidence_path), "--source-pack", str(self.source_pack), "--output-dir", str(self.root / "frames"), *extra], capture_output=True, text=True, encoding="utf-8")
            self.assertNotEqual(0, result.returncode)
            self.assertIn("relativePath", result.stdout)

    def test_approved_g2_narration_can_enter_g3(self):
        decision = self.decision()
        code, output = self.run_cli(self.plan(decision), decision)
        self.assertEqual(0, code, output)

    def test_needs_fact_review_decision_is_blocked(self):
        decision = self.decision(status="needs_fact_review")
        code, output = self.run_cli(self.plan(decision), decision)
        self.assertNotEqual(0, code)
        self.assertIn("not approved_for_g3", output)

    def test_candidate_narration_is_blocked(self):
        decision = self.decision()
        candidate = self.root / "candidate.md"
        candidate.write_text("candidate", encoding="utf-8")
        code, output = self.run_cli(self.plan(decision, narrationDraft=str(candidate)), decision)
        self.assertNotEqual(0, code)
        self.assertIn("exactly match", output)

    def test_superseded_narration_is_blocked(self):
        old = self.root / "old.md"
        old.write_text("old", encoding="utf-8")
        decision = self.decision(approvedNarrationRef=str(old), supersededDraftRefs=[str(old)])
        code, output = self.run_cli(self.plan(decision, narrationDraft=str(old)), decision)
        self.assertNotEqual(0, code)
        self.assertIn("superseded", output)

    def test_missing_approved_narration_is_blocked(self):
        decision = self.decision(approvedNarrationRef=str(self.root / "missing.md"))
        code, output = self.run_cli(self.plan(decision), decision)
        self.assertNotEqual(0, code)
        self.assertIn("must be an existing project file", output)

    def test_missing_g2_decision_argument_is_rejected(self):
        result = subprocess.run([str(PYTHON), str(SCRIPT), "--plan", "x", "--evidence", "y"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("--g2-decision", result.stderr)

    def test_manually_verified_claim_needs_non_first_party_provenance(self):
        decision = self.decision(userManuallyVerifiedClaims=["a claim"])
        code, output = self.run_cli(self.plan(decision), decision)
        self.assertNotEqual(0, code)
        self.assertIn("provenanceRule", output)

    def test_manually_verified_claim_with_provenance_is_allowed(self):
        decision = self.decision(
            userManuallyVerifiedClaims=["a claim"],
            provenanceRule="Confirmed by the user; not first-party verified.",
        )
        code, output = self.run_cli(self.plan(decision), decision)
        self.assertEqual(0, code, output)

    def test_approved_for_g4_requires_explicit_approval_record(self):
        decision = self.decision()
        code, output = self.run_cli(self.plan(decision, status="approved_for_g4"), decision)
        self.assertNotEqual(0, code)
        self.assertIn("timelineReview", output)

    def test_approved_for_g4_with_approval_record_is_allowed(self):
        decision = self.decision()
        plan = self.plan(decision, status="approved_for_g4", timelineReview={
            "status": "confirmed", "confirmedBy": "user", "confirmedAt": "2026-08-18", "feedback": "整体确认", "basisRefs": ["G3-逐段剪辑时间表-v0.1.md"],
        }, g3Approval={
            "approvedBy": "user", "approvedAt": "2026-08-18", "basisRefs": ["G3-放行检查-v0.1.md"],
        })
        code, output = self.run_cli(plan, decision)
        self.assertEqual(0, code, output)
        self.assertIn('"planStatus": "approved_for_g4"', output)

    def test_approved_for_g4_without_timeline_review_is_blocked(self):
        decision = self.decision()
        plan = self.plan(decision, status="approved_for_g4", g3Approval={"approvedBy":"user","approvedAt":"2026-08-18","basisRefs":["check.md"]})
        code, output = self.run_cli(plan, decision)
        self.assertNotEqual(0, code)
        self.assertIn("timelineReview", output)

    def test_bom_encoded_json_is_allowed(self):
        decision = self.decision()
        plan = self.plan(decision)
        plan.write_text(plan.read_text(encoding="utf-8"), encoding="utf-8-sig")
        self.evidence_path.write_text(self.evidence_path.read_text(encoding="utf-8"), encoding="utf-8-sig")
        decision.write_text(decision.read_text(encoding="utf-8"), encoding="utf-8-sig")
        code, output = self.run_cli(plan, decision)
        self.assertEqual(0, code, output)

    def test_unverified_visual_candidate_is_blocked(self):
        decision = self.decision()
        plan = self.plan(decision)
        content = json.loads(plan.read_text(encoding="utf-8"))
        content["segments"][0]["visualVerification"]["status"] = "candidate"
        plan.write_text(json.dumps(content), encoding="utf-8")
        code, output = self.run_cli(plan, decision)
        self.assertNotEqual(0, code)
        self.assertIn("verified visualVerification", output)

    def test_missing_narration_mapping_is_blocked(self):
        decision = self.decision()
        plan = self.plan(decision)
        content = json.loads(plan.read_text(encoding="utf-8"))
        del content["segments"][0]["narrationText"]
        plan.write_text(json.dumps(content), encoding="utf-8")
        code, output = self.run_cli(plan, decision)
        self.assertNotEqual(0, code)
        self.assertIn("narrationText", output)

    def test_semantic_mismatch_is_blocked_for_g4(self):
        decision = self.decision()
        plan = self.plan(decision, status="approved_for_g4", timelineReview={
            "status": "confirmed", "confirmedBy": "user", "confirmedAt": "2026-08-18", "feedback": "整体确认", "basisRefs": ["review.md"],
        }, g3Approval={"approvedBy": "user", "approvedAt": "2026-08-18", "basisRefs": ["check.md"]})
        content = json.loads(plan.read_text(encoding="utf-8"))
        content["segments"][0]["semanticAlignment"]["status"] = "semantic_mismatch"
        plan.write_text(json.dumps(content), encoding="utf-8")
        code, output = self.run_cli(plan, decision)
        self.assertNotEqual(0, code)
        self.assertIn("semantic_mismatch", output)

    def test_subject_policy_confirmation_can_be_referenced_by_approved_plan(self):
        decision = self.decision()
        subject = self.subject_confirmation()
        ledger = self.ledger()
        plan = self.plan(decision, status="approved_for_g4", timelineReview={
            "status": "confirmed", "confirmedBy": "user", "confirmedAt": "2026-09-08", "feedback": "整体确认",
            "basisRefs": [str(subject), str(ledger), "review.md"],
        }, g3Approval={"approvedBy": "user", "approvedAt": "2026-09-08", "basisRefs": ["check.md"]})
        content = json.loads(plan.read_text(encoding="utf-8"))
        content["segments"][0]["visualVerification"]["derivedFromObservationIds"] = ["obs-active", "obs-002"]
        plan.write_text(json.dumps(content), encoding="utf-8")
        code, output = self.run_cli(plan, decision, subject=subject, ledger=ledger)
        self.assertEqual(0, code, output)

    def test_subject_confirmation_rejects_unconfirmed_policy(self):
        decision = self.decision()
        subject = self.subject_confirmation(targetSubject={
            "canonicalName": "测试主体", "userConfirmed": False,
            "identificationRules": ["规则"], "exclusionRules": ["排除规则"],
        })
        code, output = self.run_cli(self.plan(decision), decision, subject=subject)
        self.assertNotEqual(0, code)
        self.assertIn("userConfirmed=true", output)

    def test_subject_sufficiency_fallback_requires_complete_preapproval(self):
        decision = self.decision()
        subject = self.subject_confirmation(sufficiencyFallback={"preApproved": "shorten_output"})
        code, output = self.run_cli(self.plan(decision), decision, subject=subject)
        self.assertNotEqual(0, code)
        self.assertIn("approvedBy", output)

    def test_ledger_blocks_approved_plan_from_using_superseded_observation(self):
        decision = self.decision()
        subject = self.subject_confirmation()
        ledger = self.ledger()
        plan = self.plan(decision, status="approved_for_g4", timelineReview={
            "status": "confirmed", "confirmedBy": "user", "confirmedAt": "2026-09-08", "feedback": "整体确认",
            "basisRefs": [str(subject), str(ledger), "review.md"],
        }, g3Approval={"approvedBy": "user", "approvedAt": "2026-09-08", "basisRefs": ["check.md"]})
        content = json.loads(plan.read_text(encoding="utf-8"))
        content["segments"][0]["visualVerification"]["derivedFromObservationIds"] = ["obs-active", "obs-001"]
        plan.write_text(json.dumps(content), encoding="utf-8")
        code, output = self.run_cli(plan, decision, subject=subject, ledger=ledger)
        self.assertNotEqual(0, code)
        self.assertIn("non-active observation obs-001", output)

    def test_missing_visual_analysis_argument_is_rejected(self):
        decision = self.decision()
        plan = self.plan(decision)
        result = subprocess.run([str(PYTHON), str(SCRIPT), "--plan", str(plan), "--evidence", str(self.evidence_path), "--g2-decision", str(decision)], capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("--visual-analysis", result.stderr)

    def test_incomplete_visual_analysis_is_blocked(self):
        decision = self.decision()
        plan = self.plan(decision)
        visual = json.loads(self.visual_analysis_path.read_text(encoding="utf-8"))
        visual["status"] = "blocked"
        self.visual_analysis_path.write_text(json.dumps(visual), encoding="utf-8")
        code, output = self.run_cli(plan, decision)
        self.assertNotEqual(0, code)
        self.assertIn("visual analysis is not completed", output)

    def test_visual_analysis_hash_mismatch_is_blocked(self):
        decision = self.decision()
        plan = self.plan(decision)
        visual = json.loads(self.visual_analysis_path.read_text(encoding="utf-8"))
        visual["targetAssets"][0]["sha256"] = "wrong"
        self.visual_analysis_path.write_text(json.dumps(visual), encoding="utf-8")
        code, output = self.run_cli(plan, decision)
        self.assertNotEqual(0, code)
        self.assertIn("SHA-256", output)

    def test_missing_duration_decision_is_blocked(self):
        decision = self.decision()
        plan = self.plan(decision)
        content = json.loads(plan.read_text(encoding="utf-8"))
        del content["durationDecision"]
        plan.write_text(json.dumps(content), encoding="utf-8")
        code, output = self.run_cli(plan, decision)
        self.assertNotEqual(0, code)
        self.assertIn("durationDecision", output)

    def test_overlapping_source_ranges_with_different_ids_are_blocked(self):
        decision = self.decision()
        plan = self.plan(decision)
        content = json.loads(plan.read_text(encoding="utf-8"))
        duplicate = dict(content["segments"][0])
        duplicate["segmentId"] = "s2"
        duplicate["startMs"] = 500
        duplicate["endMs"] = 1_500
        content["segments"].append(duplicate)
        plan.write_text(json.dumps(content), encoding="utf-8")
        code, output = self.run_cli(plan, decision)
        self.assertNotEqual(0, code)
        self.assertIn("source range overlap", output)

    def test_repeated_timeline_segment_is_blocked(self):
        decision = self.decision()
        plan = self.plan(decision)
        content = json.loads(plan.read_text(encoding="utf-8"))
        content["editPlan"]["timeline"].append({"segmentId": "s1"})
        plan.write_text(json.dumps(content), encoding="utf-8")
        code, output = self.run_cli(plan, decision)
        self.assertNotEqual(0, code)
        self.assertIn("cannot repeat", output)

    def test_invalid_intentional_silence_is_blocked(self):
        decision = self.decision()
        plan = self.plan(decision)
        content = json.loads(plan.read_text(encoding="utf-8"))
        content["durationDecision"]["intentionalSilence"][0]["purpose"] = ""
        plan.write_text(json.dumps(content), encoding="utf-8")
        code, output = self.run_cli(plan, decision)
        self.assertNotEqual(0, code)
        self.assertIn("intentionalSilence requires purpose", output)

    def test_bgm_plan_full_hash_chain_passes(self):
        decision = self.decision()
        bgm_plan, pack, alignment = self.enable_bgm_chain(self.plan(decision))
        code, output = self.run_cli(bgm_plan, decision, bgm=(pack, alignment))
        self.assertEqual(0, code, output)

    def test_registered_bgm_without_plan_section_is_blocked(self):
        decision = self.decision()
        bgm_plan, pack, alignment = self.enable_bgm_chain(self.plan(decision))
        plain = self.plan(decision)
        code, output = self.run_cli(plain, decision, bgm=(pack, None))
        self.assertNotEqual(0, code)
        self.assertIn("must carry bgmPlan", output)

    def test_bgm_plan_without_arguments_cannot_escape_validation(self):
        decision = self.decision()
        bgm_plan, pack, alignment = self.enable_bgm_chain(self.plan(decision))
        code, output = self.run_cli(bgm_plan, decision)
        self.assertNotEqual(0, code)
        self.assertIn("--material-pack", output)
        code, output = self.run_cli(bgm_plan, decision, bgm=(pack, None))
        self.assertNotEqual(0, code)
        self.assertIn("--bgm-alignment", output)

    def test_report_tampered_after_g0_is_blocked(self):
        decision = self.decision()
        bgm_plan, pack, alignment = self.enable_bgm_chain(self.plan(decision))
        report = self.source_pack / "07_授权音频" / "BGM-分析报告-test.json"
        report.write_text(report.read_text(encoding="utf-8") + " ", encoding="utf-8")
        code, output = self.run_cli(bgm_plan, decision, bgm=(pack, alignment))
        self.assertNotEqual(0, code)
        self.assertIn("tampered after G0", output)

    def test_hand_edited_offset_is_blocked(self):
        decision = self.decision()
        bgm_plan, pack, alignment = self.enable_bgm_chain(self.plan(decision))
        content = json.loads(bgm_plan.read_text(encoding="utf-8"))
        content["bgmPlan"]["trackOffsetMs"] = 60_001
        bgm_plan.write_text(json.dumps(content), encoding="utf-8")
        code, output = self.run_cli(bgm_plan, decision, bgm=(pack, alignment))
        self.assertNotEqual(0, code)
        self.assertIn("change tool parameters", output)

    def test_alignment_v01_without_layout_is_rejected(self):
        decision = self.decision()
        bgm_plan, pack, alignment = self.enable_bgm_chain(self.plan(decision))
        value = json.loads(alignment.read_text(encoding="utf-8"))
        value["schemaVersion"] = "0.1"
        del value["layout"]
        alignment.write_text(json.dumps(value), encoding="utf-8")
        code, output = self.run_cli(bgm_plan, decision, bgm=(pack, alignment))
        self.assertNotEqual(0, code)
        self.assertIn("schemaVersion 0.2", output)

    def test_tampered_alignment_artifact_is_blocked(self):
        decision = self.decision()
        bgm_plan, pack, alignment = self.enable_bgm_chain(self.plan(decision))
        value = json.loads(alignment.read_text(encoding="utf-8"))
        value["alignment"]["offsetMs"] = 61_000
        alignment.write_text(json.dumps(value), encoding="utf-8")
        code, output = self.run_cli(bgm_plan, decision, bgm=(pack, alignment))
        self.assertNotEqual(0, code)
        self.assertIn("alignmentSha256", output)

    def test_narration_time_drift_beyond_voice_brief_is_blocked(self):
        decision = self.decision()
        bgm_plan, pack, alignment = self.enable_bgm_chain(self.plan(decision))
        content = json.loads(bgm_plan.read_text(encoding="utf-8"))
        content["segments"][0]["narrationEndMs"] = 1_200  # sentence N01 ends at 1000ms
        bgm_plan.write_text(json.dumps(content), encoding="utf-8")
        code, output = self.run_cli(bgm_plan, decision, bgm=(pack, alignment))
        self.assertNotEqual(0, code)
        self.assertIn("frozen", output)

    def test_segment_missing_layout_tier_is_blocked(self):
        decision = self.decision()
        bgm_plan, pack, alignment = self.enable_bgm_chain(self.plan(decision))
        content = json.loads(bgm_plan.read_text(encoding="utf-8"))
        content["segments"][0]["layoutTier"] = "炸裂"
        bgm_plan.write_text(json.dumps(content), encoding="utf-8")
        code, output = self.run_cli(bgm_plan, decision, bgm=(pack, alignment))
        self.assertNotEqual(0, code)
        self.assertIn("layoutTier", output)


if __name__ == "__main__":
    unittest.main()
