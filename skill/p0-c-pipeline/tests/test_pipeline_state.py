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

    def run_raw(self, *args):
        result = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_unicode_flag_emits_readable_chinese(self):
        # Issue ③: --unicode matches material_pack.py so agents stop piping decode.
        self.pack.write_text(json.dumps({"packStatus": "complete", "bgm": {"decision": "use_library_later", "libraryPending": True, "preference": "高燃电子"}}, ensure_ascii=False), encoding="utf-8")
        self.init()
        self.assertIn("\\u9ad8\\u71c3", self.run_raw("status", "--state", self.state))  # default stays escaped
        readable = self.run_raw("status", "--state", self.state, "--unicode")
        self.assertIn("高燃电子", readable)
        self.assertEqual("高燃电子", json.loads(readable)["bgm"]["preference"])  # still machine-parseable

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

    def test_bgm_pending_slot_blocks_g2_until_evidenced_flip(self):
        import hashlib
        audio = self.root / "07_授权音频" / "GoneBad.mp3"
        audio.parent.mkdir(parents=True, exist_ok=True)
        audio.write_bytes(b"fake-audio-bytes")
        sha = hashlib.sha256(audio.read_bytes()).hexdigest().upper()
        registration = audio.parent / "BGM-候选登记-GoneBad-ABCD.json"
        registration.write_text(json.dumps({"sha256": sha, "audioPath": str(audio),
                                            "analysisRef": "BGM-分析报告-GoneBad.json"}), encoding="utf-8")
        self.pack.write_text(json.dumps({"packStatus": "complete", "bgm": {
            "decision": "use_library_later", "preference": "想要 LOW 那种高燃 phonk 的感觉",
            "libraryPending": True, "clearCondition": "G1 末检索词卡找乐"},
            "audioAssets": [{"sha256": sha, "bgmAnalysis": {"relativePath": "x", "sha256": "y"}}]}), encoding="utf-8")
        self.init()
        status = self.run_cli("status", "--state", self.state)
        self.assertIn("待找乐", status["bgm"]["reminder"])
        self.assertEqual("想要 LOW 那种高燃 phonk 的感觉", status["bgm"]["preference"])
        self.prepare_node("G1")
        self.approve("G1")
        self.prepare_node("G2")
        blocked = self.approve("G2", code=2)
        self.assertIn("BGM 待找乐", blocked["error"])
        self.run_cli("bgm-choice", "--state", self.state, "--decision", "provided", code=2)  # 无证据不翻灯
        # Issue ⑱: evidence pointing at a not-yet-paired record must be refused.
        self.run_cli("bgm-choice", "--state", self.state, "--decision", "provided",
                     "--evidence", "07_授权音频/不存在.json", code=2)
        # Issue ㉔: slot closure without a registered full-track analysis is refused.
        no_analysis = audio.parent / "BGM-候选登记-NoAnalysis.json"
        no_analysis.write_text(json.dumps({"sha256": sha, "audioPath": str(audio)}), encoding="utf-8")
        self.pack.write_text(json.dumps({"packStatus": "complete", "audioAssets": [{"sha256": sha}]}), encoding="utf-8")
        blocked_flip = self.run_cli("bgm-choice", "--state", self.state, "--decision", "provided",
                                    "--evidence", str(no_analysis), code=2)
        self.assertIn("分析报告", blocked_flip["error"])
        self.pack.write_text(json.dumps({"packStatus": "complete", "audioAssets": [
            {"sha256": sha, "bgmAnalysis": {"relativePath": "x", "sha256": "y"}}]}), encoding="utf-8")
        self.run_cli("bgm-choice", "--state", self.state, "--decision", "provided",
                     "--evidence", str(registration), "--note", "用户选定金曲并登记")
        status = self.run_cli("status", "--state", self.state)
        self.assertNotIn("reminder", status["bgm"])
        self.approve("G2")  # 槽清后即可批
        bgm = json.loads(self.state.read_text(encoding="utf-8"))["bgm"]
        self.assertEqual("provided", bgm["decision"])
        self.assertEqual(1, len(bgm["history"]))  # 翻槽历史 append-only

    def test_bgm_no_bgm_clears_without_evidence(self):
        self.pack.write_text(json.dumps({"packStatus": "complete", "bgm": {"decision": "use_library_later", "libraryPending": True}}), encoding="utf-8")
        self.init()
        self.run_cli("bgm-choice", "--state", self.state, "--decision", "no_bgm", "--note", "用户决定本片不用 BGM")
        status = self.run_cli("status", "--state", self.state)
        self.assertFalse(status["bgm"]["libraryPending"])

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
        self.assertFalse(state["nodes"]["G1"]["approval"]["normalizedFromVariant"])

    def test_typed_variants_are_normalized_with_verbatim_trace(self):
        self.init()
        self.prepare_node("G1")
        result = self.approve("G1", token="确认G1")
        self.assertEqual("G2", result["currentNode"])
        approval = json.loads(self.state.read_text(encoding="utf-8"))["nodes"]["G1"]["approval"]
        self.assertEqual("确认 G1", approval["approvalToken"])
        self.assertEqual("确认G1", approval["approvalResponseVerbatim"])
        self.assertTrue(approval["normalizedFromVariant"])
        # bare 确认 attaches to the current pending gate only (node==currentNode was enforced above)
        self.prepare_node("G2")
        self.approve("G2", token="确认")
        approval = json.loads(self.state.read_text(encoding="utf-8"))["nodes"]["G2"]["approval"]
        self.assertEqual("确认 G2", approval["approvalResponse"])
        self.assertEqual("确认", approval["approvalResponseVerbatim"])
        # a variant naming another node must never approve this one
        self.prepare_node("G3")
        self.approve("G3", token="确认G2", code=2)
        # 确定了 is the most natural bare completion (zaku G2: "OK,那现在已经确定了"
        # was rejected for its prefix — bare 了-form passes, prefixed prose never does)
        self.approve("G3", token="确定了")
        approval = json.loads(self.state.read_text(encoding="utf-8"))["nodes"]["G3"]["approval"]
        self.assertEqual("确认 G3", approval["approvalToken"])
        self.assertEqual("确定了", approval["approvalResponseVerbatim"])
        self.assertTrue(approval["normalizedFromVariant"])
        # 确定 is the synonym real users type (zaku G2 live run: "确定 G2")
        self.prepare_node("G4")
        self.approve("G4", token="确定G4")
        approval = json.loads(self.state.read_text(encoding="utf-8"))["nodes"]["G4"]["approval"]
        self.assertEqual("确认 G4", approval["approvalToken"])
        self.assertEqual("确定G4", approval["approvalResponseVerbatim"])
        self.assertTrue(approval["normalizedFromVariant"])

    def test_g2_requires_existing_and_reviewed_references(self):
        self.init()
        self.prepare_node("G1")
        self.approve("G1")
        # facts deliberately NOT a receipt basisRef, so the approval-argument check is
        # what catches its deletion (receipt reload stays green).
        self.prepare_node("G2", basis_refs=[self.narration, self.voice])
        self.facts.unlink()
        blocked = self.approve("G2", code=2)
        self.assertIn("G2 factCitationRef", blocked["error"])

    def test_deleted_receipt_basis_after_record_review_is_flagged_invalid(self):
        # Issue 002-⑦ companion: a basis file pulled out from under a recorded receipt
        # makes the receipt no longer valid — approve must refuse, not trust the snapshot.
        self.init()
        self.prepare_node("G1")
        self.files["G1"]["basis"].unlink()
        blocked = self.approve("G1", code=2)
        self.assertIn("no longer valid", blocked["error"])

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

    def test_receipt_changed_after_record_review_is_flagged_stale(self):
        # Issue 002-⑦: editing the receipt after record-review must say "snapshot stale,
        # re-record" — never blame the (correct) frozen snapshot for a "missing" basisRef.
        self.init()
        self.prepare_node("G1")
        receipt_path = self.root / "G1-review-gate.json"
        value = json.loads(receipt_path.read_text(encoding="utf-8"))
        value["renderedAt"] = "2026-09-08T09:00:00Z"
        receipt_path.write_text(json.dumps(value), encoding="utf-8")
        blocked = self.approve("G1", code=2)
        self.assertIn("changed since record-review", blocked["error"])
        # Re-recording the (valid) receipt refreshes the snapshot and approval proceeds.
        self.register_review("G1", basis_refs=[self.files["G1"]["approval"], self.files["G1"]["basis"]])
        self.approve("G1")

    def test_receipt_broken_after_record_review_is_flagged_invalid(self):
        self.init()
        self.prepare_node("G1")
        receipt_path = self.root / "G1-review-gate.json"
        value = json.loads(receipt_path.read_text(encoding="utf-8"))
        value["reviewStatus"] = "draft"
        receipt_path.write_text(json.dumps(value), encoding="utf-8")
        blocked = self.approve("G1", code=2)
        self.assertIn("no longer valid", blocked["error"])


if __name__ == "__main__":
    unittest.main()
