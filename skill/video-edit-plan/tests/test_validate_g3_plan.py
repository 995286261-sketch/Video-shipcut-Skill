import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skill" / "video-edit-plan" / "scripts" / "validate_g3_plan.py"
PYTHON = Path(sys.executable)


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
        self.evidence_path = self.write_json("evidence.json", {
            "projectId": "demo-001",
            "sourceEvidence": [{"assetId": "clip-1", "sha256": "fixture-sha", "sourceProbe": {"durationMs": 10_000}}],
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

    def run_cli(self, plan, decision):
        result = subprocess.run(
            [str(PYTHON), str(SCRIPT), "--plan", str(plan), "--evidence", str(self.evidence_path), "--g2-decision", str(decision), "--visual-analysis", str(self.visual_analysis_path), "--semantic-beats", str(self.semantic_beats_path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        return result.returncode, result.stdout + result.stderr

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
        self.assertIn("does not exist", output)

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


if __name__ == "__main__":
    unittest.main()
