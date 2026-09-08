import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skill" / "p0-c-pipeline" / "scripts" / "pipeline_state.py"
CARD_TYPES = {
    "G1": "g1_direction_review",
    "G2": "g2_evidence_narration_review",
    "G3": "g3_timeline_review",
    "G4": "g4_candidate_review",
    "G5": "g5_delivery_review",
}
CHECKLISTS = {
    "G1": ("direction_brief", "claims_and_boundaries", "direction_card"),
    "G2": ("fact_citation", "approved_narration", "voice_brief", "g2_card"),
    "G3": ("approved_edit_plan", "final_timeline_review", "subtitle_timeline", "bgm_decision", "packaging_decisions", "g3_card"),
    "G4": ("candidate_or_export", "render_validation", "playback_review_card"),
    "G5": ("delivery_manifest", "qa_validation", "playback_review", "check_frames", "distribution_boundary"),
}


class PipelineStateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pack = self.root / "material-pack.json"
        self.state = self.root / "pipeline-state.json"
        self.pack.write_text(json.dumps({"packStatus": "complete"}), encoding="utf-8")
        self.files = {}
        for node in CARD_TYPES:
            self.files[node] = {
                "approval": self.file(f"{node}-approval.json"),
                "card": self.file(f"{node}-card.md"),
                "basis": self.file(f"{node}-basis.json"),
            }
            for item_id in CHECKLISTS[node]:
                self.files[node][item_id] = self.file(f"{node}-{item_id}.json")
        self.narration = self.file("G2-证据与口播/narration.md")
        self.facts = self.file("G2-证据与口播/facts.json")
        self.voice = self.file("G2-证据与口播/voice.json")
        self.plan = self.file("G3-剪辑计划/plan.json")
        self.timeline = self.file("G3-剪辑计划/timeline-review.md")
        self.render = self.file("G4-剪辑与渲染/final-candidate.mp4")
        self.g4_validation = self.file("G4-剪辑与渲染/validation.json")
        self.chatcut = self.file("G4-剪辑与渲染/ChatCut-导出/batch/final.mp4")
        self.delivery = self.file("G5-交付包/交付包-v0.1/delivery-manifest.json")
        self.g5_validation = self.file("G5-交付包/交付包-v0.1/validation.json")

    def file(self, relative):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture", encoding="utf-8")
        return path

    def run_cli(self, *args, code=0):
        result = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def init(self):
        return self.run_cli("init", "--project-id", "fixture", "--source-pack", self.pack, "--state", self.state, "--authorization", "authorized", "--distribution", "local_only")

    def receipt(self, node, *, project_id="fixture", card_type=None, missing_item=None, incomplete_item=None, basis_refs=None):
        evidence = self.files[node]
        checklist = []
        for item_id in CHECKLISTS[node]:
            if item_id == missing_item:
                continue
            checklist.append({
                "id": item_id,
                "required": True,
                "status": "pending" if item_id == incomplete_item else "completed",
                "evidenceRef": str(evidence[item_id]),
            })
        value = {
            "schemaVersion": "0.1",
            "projectId": project_id,
            "node": node,
            "cardType": card_type or CARD_TYPES[node],
            "reviewStatus": "ready_for_approval",
            "reviewCardRef": str(evidence["card"]),
            "basisRefs": [str(evidence["basis"])] if basis_refs is None else [str(value) for value in basis_refs],
            "checklist": checklist,
            "renderedAt": "2026-09-08T00:00:00Z",
        }
        path = self.root / f"{node}-review-gate.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def move_to_review(self, node):
        self.run_cli("record", "--state", self.state, "--node", node, "--node-status", "review_required")

    def register_review(self, node, **kwargs):
        return self.run_cli("record-review", "--state", self.state, "--node", node, "--review-gate-ref", self.receipt(node, **kwargs))

    def approve(self, node, *, token=None, response=None, code=0, g4_mode="local_direct"):
        args = ["approve", "--state", self.state, "--node", node, "--approval-ref", self.files[node]["approval"], "--approval-token", token or f"确认 {node}", "--approval-response", response if response is not None else token or f"确认 {node}"]
        if node == "G2":
            args += ["--approved-narration-ref", self.narration, "--fact-citation-ref", self.facts, "--voice-brief-ref", self.voice]
        elif node == "G3":
            args += ["--edit-plan-ref", self.plan, "--timeline-review-ref", self.timeline]
        elif node == "G4" and g4_mode == "chatcut":
            args += ["--g4-output-mode", "chatcut", "--chatcut-export-ref", self.chatcut]
        elif node == "G4":
            args += ["--local-render-ref", self.render, "--g4-validation-ref", self.g4_validation]
        elif node == "G5":
            args += ["--delivery-manifest-ref", self.delivery, "--g5-validation-ref", self.g5_validation]
        return self.run_cli(*args, code=code)

    def prepare_node(self, node, *, basis_refs=None):
        self.move_to_review(node)
        if basis_refs is None:
            basis_refs = [self.files[node]["basis"]]
            if node == "G2":
                basis_refs = [self.narration, self.facts, self.voice]
            elif node == "G3":
                basis_refs = [self.plan, self.timeline]
            elif node == "G4":
                basis_refs = [self.render, self.g4_validation]
            elif node == "G5":
                basis_refs = [self.delivery, self.g5_validation]
        self.register_review(node, basis_refs=[self.files[node]["approval"], *basis_refs])

    def advance_through(self, last_node):
        for node in ("G1", "G2", "G3", "G4", "G5"):
            self.prepare_node(node)
            self.approve(node)
            if node == last_node:
                return

    def test_initializes_with_missing_review_gate(self):
        self.init()
        status = self.run_cli("status", "--state", self.state)
        self.assertEqual("G1", status["currentNode"])
        self.assertEqual("missing", status["reviewGateStatus"])

    def test_every_node_requires_review_gate_before_approval(self):
        self.init()
        for node in ("G1", "G2", "G3", "G4", "G5"):
            self.move_to_review(node)
            blocked = self.approve(node, code=2)
            self.assertIn("review gate", blocked["error"])
            self.prepare_node(node)
            self.approve(node)

    def test_review_receipt_rejects_wrong_shape_and_unfinished_items(self):
        self.init()
        self.move_to_review("G1")
        invalid = self.run_cli("record-review", "--state", self.state, "--node", "G1", "--review-gate-ref", self.receipt("G1", missing_item="direction_card"), code=2)
        self.assertIn("checklist", invalid["error"])
        invalid = self.run_cli("record-review", "--state", self.state, "--node", "G1", "--review-gate-ref", self.receipt("G1", incomplete_item="direction_card"), code=2)
        self.assertIn("completed", invalid["error"])
        invalid = self.run_cli("record-review", "--state", self.state, "--node", "G1", "--review-gate-ref", self.receipt("G1", project_id="wrong"), code=2)
        self.assertIn("projectId", invalid["error"])
        invalid = self.run_cli("record-review", "--state", self.state, "--node", "G1", "--review-gate-ref", self.receipt("G1", card_type="g2_evidence_narration_review"), code=2)
        self.assertIn("cardType", invalid["error"])

    def test_only_exact_current_node_confirmation_can_advance(self):
        self.init()
        self.prepare_node("G1")
        for token in ("好的", "OK", "确认G", "确认 G2"):
            blocked = self.approve("G1", token=token, code=2)
            self.assertIn("approval", blocked["error"])
        result = self.approve("G1")
        self.assertEqual("G2", result["currentNode"])
        state = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual("确认 G1", state["nodes"]["G1"]["approval"]["approvalToken"])
        self.assertEqual("确认 G1", state["nodes"]["G1"]["approval"]["approvalResponse"])

    def test_g2_requires_existing_and_reviewed_references(self):
        self.init()
        self.prepare_node("G1")
        self.approve("G1")
        self.prepare_node("G2", basis_refs=[self.narration, self.facts, self.voice])
        self.facts.unlink()
        blocked = self.approve("G2", code=2)
        self.assertIn("G2 factCitationRef", blocked["error"])

    def test_reopen_invalidates_review_gate_and_approval(self):
        self.init()
        self.advance_through("G3")
        self.move_to_review("G4")
        result = self.run_cli("reopen-g3", "--state", self.state, "--reason", "plan defect", "--rework-ref", self.file("rework.md"))
        self.assertEqual("G3", result["currentNode"])
        state = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertIsNone(state["nodes"]["G3"]["reviewGate"])
        self.assertIsNone(state["nodes"]["G3"]["approval"])
        self.assertIsNone(state["nodes"]["G4"]["reviewGate"])

    def test_full_five_node_review_gate_chain(self):
        self.init()
        self.advance_through("G5")
        status = self.run_cli("status", "--state", self.state)
        self.assertEqual("completed", status["currentNode"])
        self.assertEqual("completed", status["status"])


if __name__ == "__main__":
    unittest.main()
