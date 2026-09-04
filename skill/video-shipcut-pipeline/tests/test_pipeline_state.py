import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skill" / "video-shipcut-pipeline" / "scripts" / "pipeline_state.py"


class PipelineStateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.pack = self.root / "material-pack.json"; self.state = self.root / "pipeline-state.json"
        self.pack.write_text(json.dumps({"packStatus": "complete"}), encoding="utf-8")
        self.g1 = self.file("G1-创作方向/g1.json")
        self.g2 = self.file("G2-证据与口播/g2.json")
        self.g3 = self.file("G3-剪辑计划/g3.json")
        self.plan = self.file("G3-剪辑计划/plan.json")
        self.review = self.file("G3-剪辑计划/timeline-review.md")
        self.g4 = self.file("G4-剪辑与渲染/g4.json")
        self.render = self.file("G4-剪辑与渲染/final-candidate.mp4")
        self.g4_validation = self.file("G4-剪辑与渲染/validation.json")
        self.chatcut = self.file("G4-剪辑与渲染/ChatCut-导出/batch/final.mp4")
        self.g5 = self.file("G5-交付包/交付包-v0.1/g5.json")
        self.delivery = self.file("G5-交付包/交付包-v0.1/delivery-manifest.json")
        self.g5_validation = self.file("G5-交付包/交付包-v0.1/validation.json")

    def file(self, relative):
        path = self.root / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_text("fixture", encoding="utf-8"); return path

    def run_cli(self, *args, code=0):
        result = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def init(self):
        return self.run_cli("init", "--project-id", "fixture", "--source-pack", self.pack, "--state", self.state, "--authorization", "authorized", "--distribution", "local_only")

    def test_initializes_and_recovers_without_legacy_manifest(self):
        self.init(); value = self.run_cli("status", "--state", self.state)
        self.assertEqual("G1", value["currentNode"]); self.assertEqual("in_progress", value["nodeStatus"])

    def test_g2_cannot_advance_without_locked_narration_facts_and_voice(self):
        self.init(); self.run_cli("approve", "--state", self.state, "--node", "G1", "--approval-ref", self.g1)
        value = self.run_cli("approve", "--state", self.state, "--node", "G2", "--approval-ref", self.g2, code=2)
        self.assertEqual("blocked", value["status"])

    def test_g3_and_g4_have_required_human_gates(self):
        self.init(); self.run_cli("approve", "--state", self.state, "--node", "G1", "--approval-ref", self.g1)
        self.run_cli("approve", "--state", self.state, "--node", "G2", "--approval-ref", self.g2, "--approved-narration-ref", "script.md", "--fact-decision-ref", "facts.json", "--voice-decision-ref", "voice.json")
        blocked = self.run_cli("approve", "--state", self.state, "--node", "G3", "--approval-ref", self.g3, code=2)
        self.assertEqual("blocked", blocked["status"])
        self.run_cli("approve", "--state", self.state, "--node", "G3", "--approval-ref", self.g3, "--edit-plan-ref", self.plan, "--timeline-review-ref", self.review)
        blocked = self.run_cli("approve", "--state", self.state, "--node", "G4", "--approval-ref", self.g4, code=2)
        self.assertEqual("blocked", blocked["status"])

    def reach_g3(self):
        self.init()
        self.run_cli("approve", "--state", self.state, "--node", "G1", "--approval-ref", self.g1)
        self.run_cli("approve", "--state", self.state, "--node", "G2", "--approval-ref", self.g2, "--approved-narration-ref", "script.md", "--fact-decision-ref", "facts.json", "--voice-decision-ref", "voice.json")

    def test_g3_can_reopen_g2_for_a_traceable_amendment(self):
        self.reach_g3()
        result = self.run_cli("reopen", "--state", self.state, "--reason", "register an omitted G0 asset", "--rework-ref", "工作区/素材分析/fixture/G2-补证说明-v0.2.md")
        self.assertEqual("G2", result["currentNode"])
        state = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual("in_progress", state["nodes"]["G2"]["status"])
        self.assertEqual("pending", state["nodes"]["G3"]["status"])
        self.assertEqual("register an omitted G0 asset", state["amendmentHistory"][-1]["reason"])
        self.run_cli("approve", "--state", self.state, "--node", "G2", "--approval-ref", self.g2, "--approved-narration-ref", "script.md", "--fact-decision-ref", "facts-v2.json", "--voice-decision-ref", "voice.json")
        self.assertEqual("G3", self.run_cli("status", "--state", self.state)["currentNode"])

    def test_reopen_requires_active_g3_and_audit_data(self):
        self.init()
        result = self.run_cli("reopen", "--state", self.state, "--reason", "x", "--rework-ref", "x.md", code=2)
        self.assertEqual("blocked", result["status"])
        self.state.unlink()
        self.reach_g3()
        result = self.run_cli("reopen", "--state", self.state, "--reason", "", "--rework-ref", "", code=2)
        self.assertEqual("invalid", result["status"])

    def test_g4_can_reopen_g3_for_a_traceable_plan_defect(self):
        self.reach_g3()
        self.run_cli("approve", "--state", self.state, "--node", "G3", "--approval-ref", self.g3, "--edit-plan-ref", self.plan, "--timeline-review-ref", self.review)
        self.run_cli("record", "--state", self.state, "--node", "G4", "--node-status", "review_required", "--input-ref", "plan.json", "--review-point", "semantic mismatch")
        result = self.run_cli("reopen-g3", "--state", self.state, "--reason", "rough cut exposed a shot-plan mismatch", "--rework-ref", "G3-语义对齐返工说明-v0.1.md")
        self.assertEqual("G3", result["currentNode"])
        state = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual("in_progress", state["nodes"]["G3"]["status"])
        self.assertIsNone(state["nodes"]["G3"]["approval"])
        self.assertEqual("pending", state["nodes"]["G4"]["status"])
        self.assertEqual([], state["nodes"]["G4"]["inputRefs"])
        self.assertEqual("G4", state["amendmentHistory"][-1]["fromNode"])

    def test_g3_approval_requires_timeline_review_reference(self):
        self.reach_g3()
        blocked = self.run_cli("approve", "--state", self.state, "--node", "G3", "--approval-ref", self.g3, "--edit-plan-ref", self.plan, code=2)
        self.assertEqual("blocked", blocked["status"])
        self.assertIn("timelineReviewRef", blocked["error"])

    def test_g4_allows_validated_local_direct_branch(self):
        self.init(); self.run_cli("approve", "--state", self.state, "--node", "G1", "--approval-ref", self.g1)
        self.run_cli("approve", "--state", self.state, "--node", "G2", "--approval-ref", self.g2, "--approved-narration-ref", "script.md", "--fact-decision-ref", "facts.json", "--voice-decision-ref", "voice.json")
        self.run_cli("approve", "--state", self.state, "--node", "G3", "--approval-ref", self.g3, "--edit-plan-ref", self.plan, "--timeline-review-ref", self.review)
        result = self.run_cli("approve", "--state", self.state, "--node", "G4", "--approval-ref", self.g4, "--local-render-ref", self.render, "--g4-validation-ref", self.g4_validation)
        self.assertEqual("G5", result["currentNode"])

    def test_g5_keeps_accepted_warnings(self):
        self.init(); self.run_cli("approve", "--state", self.state, "--node", "G1", "--approval-ref", self.g1)
        self.run_cli("approve", "--state", self.state, "--node", "G2", "--approval-ref", self.g2, "--approved-narration-ref", "script.md", "--fact-decision-ref", "facts.json", "--voice-decision-ref", "voice.json")
        self.run_cli("approve", "--state", self.state, "--node", "G3", "--approval-ref", self.g3, "--edit-plan-ref", self.plan, "--timeline-review-ref", self.review)
        self.run_cli("approve", "--state", self.state, "--node", "G4", "--approval-ref", self.g4, "--g4-output-mode", "chatcut", "--chatcut-export-ref", self.chatcut)
        self.run_cli("approve", "--state", self.state, "--node", "G5", "--approval-ref", self.g5, "--delivery-manifest-ref", self.delivery, "--g5-validation-ref", self.g5_validation, "--accepted-warnings", "[\"duration_delta\"]")
        value = self.run_cli("status", "--state", self.state)
        self.assertEqual("completed", value["currentNode"]); self.assertEqual(["duration_delta"], value["acceptedWarnings"])


if __name__ == "__main__":
    unittest.main()
