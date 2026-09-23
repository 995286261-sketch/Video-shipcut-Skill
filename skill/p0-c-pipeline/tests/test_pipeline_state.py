import hashlib
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


def sha_upper(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


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
        # R1（Leader 反馈，用户 09-23 裁决方案 A）：G4/G5 关单门禁解析质检报告内容
        # （status/projectId/产物指纹重算），夹具因此必须是真报告+真字节产物，不再是一行 "fixture"。
        self.render = self.binary("G4-剪辑与渲染/final-candidate.mp4", b"fake-candidate-video-bytes")
        self.g4_validation = self.json_file("G4-剪辑与渲染/validation.json", {
            "status": "valid", "projectId": "fixture", "segments": 1, "timelineDurationMs": 1000,
            "candidate": {"path": str(self.render), "sha256": sha_upper(self.render.read_bytes())},
        })
        self.chatcut = self.file("G4-剪辑与渲染/ChatCut-导出/batch/final.mp4")
        self.delivery = self.file("G5-交付包/交付包-v0.1/delivery-manifest.json")
        self.g5_final = self.binary("G5-交付包/交付包-v0.1/final-video.mp4", b"fake-final-video")
        # chapterClips 的真实形状是列表（sinjuku/tiger 实盘对同），夹具覆盖单条+列表两种。
        self.g5_clip = self.binary("G5-交付包/交付包-v0.1/clips/chapter-01.mp4", b"fake-chapter-clip")
        self.g5_validation = self.json_file("G5-交付包/交付包-v0.1/validation.json", {
            "status": "g5_pending_human_review", "projectId": "fixture",
            "artifacts": {
                "finalVideo": {"path": "final-video.mp4", "sha256": sha_upper(self.g5_final.read_bytes())},
                "chapterClips": [{"path": "clips/chapter-01.mp4", "sha256": sha_upper(self.g5_clip.read_bytes())}],
            },
        })

    def file(self, relative):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture", encoding="utf-8")
        return path

    def binary(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def json_file(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def rewrite_json(self, path, **overrides):
        value = json.loads(path.read_text(encoding="utf-8"))
        value.update(overrides)
        path.write_text(json.dumps(value), encoding="utf-8")
        return value

    def drop_json_key(self, path, key):
        value = json.loads(path.read_text(encoding="utf-8"))
        value.pop(key)
        path.write_text(json.dumps(value), encoding="utf-8")

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

    def test_natural_reply_with_single_unconditional_clause_is_accepted(self):
        # Issue ㉕ (sinjuku live runs): exact token + unrelated question, and prose
        # forms like "那这个G4我确认了", must pass while the verbatim reply is kept.
        self.init()
        self.prepare_node("G1")
        reply = "确认G1，那么我们就这边测试做完了是吧，我们下一步是什么"
        result = self.approve("G1", token=reply, response=reply)
        self.assertEqual("G2", result["currentNode"])
        approval = json.loads(self.state.read_text(encoding="utf-8"))["nodes"]["G1"]["approval"]
        self.assertEqual("确认 G1", approval["approvalToken"])
        self.assertEqual(reply, approval["approvalResponseVerbatim"])
        self.assertTrue(approval["normalizedFromVariant"])
        self.prepare_node("G2")
        reply = "OK，那这个G2我确认了"
        self.approve("G2", token=reply, response=reply)
        approval = json.loads(self.state.read_text(encoding="utf-8"))["nodes"]["G2"]["approval"]
        self.assertEqual("确认 G2", approval["approvalResponse"])
        self.assertEqual(reply, approval["approvalResponseVerbatim"])

    def test_conditional_or_ambiguous_replies_are_refused(self):
        # ㉕'s conservative edge: anything that is not one unconditional approval
        # clause naming this node stays refused — gates never infer from shaky prose.
        self.init()
        self.advance_through("G2")
        self.prepare_node("G3")
        for reply in ("这个bug修改完毕的话就 确认G3", "确认G2还是G3", "帮我确认G3",
                      "确认G3吗", "不确认G3", "确认G3，但先别渲染", "如果没问题就确认G3"):
            blocked = self.approve("G3", token=reply, response=reply, code=2)
            self.assertIn("确认 G3", blocked["error"])
        self.approve("G3")

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

    def test_reopen_g3_from_g5_resets_g5_and_g4_approval(self):
        # Issue ㉗（sinjuku ㉖ 事故现场）：G4 关单进入 G5 后发现 G3 批准范围分歧，
        # 必须有合法回退命令；回退连带重置 G5，产物留盘作审计。
        self.init()
        self.advance_through("G4")
        self.move_to_review("G5")
        result = self.run_cli("reopen-g3", "--state", self.state, "--reason", "approval scope dispute",
                              "--rework-ref", self.file("rework-g5.md"))
        self.assertEqual("G3", result["currentNode"])
        state = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertIsNone(state["nodes"]["G3"]["approval"])
        self.assertIsNone(state["nodes"]["G4"]["approval"])
        self.assertIsNone(state["nodes"]["G4"]["reviewGate"])
        self.assertIsNone(state["nodes"]["G5"]["reviewGate"])
        self.assertEqual("pending", state["nodes"]["G5"]["status"])

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


    # ---- Leader 反馈 R1（用户 09-23 裁决方案 A + 负向自动测试）：审批入口必须解析
    # G4/G5 质检报告——失败、报告缺失/非 JSON、结果过期、张冠李戴一律阻断，
    # 不能仅检查文件存在。有效报告与对应产物匹配且人工批准后才可推进。 ----

    def test_g4_positive_bound_report_approved(self):
        # 有效报告+对应产物匹配+人工批准 → 放行（R1 的正向基线）。
        self.init()
        self.advance_through("G3")
        self.prepare_node("G4")
        result = self.approve("G4")
        self.assertEqual("G5", result["currentNode"])

    def test_g4_non_json_placeholder_report_blocked(self):
        # "不能仅检查文件存在"：文件在、内容不是 JSON 报告 → 拒。
        self.init()
        self.advance_through("G3")
        self.prepare_node("G4")
        self.g4_validation.write_text("fixture", encoding="utf-8")
        blocked = self.approve("G4", code=2)
        self.assertIn("JSON", blocked["error"])

    def test_g4_failed_status_blocked(self):
        self.init()
        self.advance_through("G3")
        self.prepare_node("G4")
        self.rewrite_json(self.g4_validation, status="invalid")
        blocked = self.approve("G4", code=2)
        self.assertIn("不可批准", blocked["error"])

    def test_g4_report_without_candidate_fingerprint_blocked(self):
        # invalid/failed 之外的第三种失败：valid 但没绑成片指纹=报告不指向任何实物。
        self.init()
        self.advance_through("G3")
        self.prepare_node("G4")
        self.drop_json_key(self.g4_validation, "candidate")
        blocked = self.approve("G4", code=2)
        self.assertIn("未绑定候选成片指纹", blocked["error"])

    def test_g4_report_from_other_project_blocked(self):
        self.init()
        self.advance_through("G3")
        self.prepare_node("G4")
        self.rewrite_json(self.g4_validation, projectId="other-film")
        blocked = self.approve("G4", code=2)
        self.assertIn("不符", blocked["error"])

    def test_g4_stale_report_after_render_change_blocked(self):
        # 结果过期：报告生成后候选成片被重渲 → 指纹对不上，逼重跑。
        self.init()
        self.advance_through("G3")
        self.prepare_node("G4")
        self.render.write_bytes(b"re-rendered candidate, report no longer describes this file")
        blocked = self.approve("G4", code=2)
        self.assertIn("指纹不符", blocked["error"])

    def test_g4_rerun_bound_report_unblocks(self):
        # 过期被拒后，按门禁提示重跑 g4_validate --candidate（等价语义：重新登记真实指纹）→ 放行。
        self.init()
        self.advance_through("G3")
        self.prepare_node("G4")
        self.render.write_bytes(b"re-rendered candidate, report no longer describes this file")
        blocked = self.approve("G4", code=2)
        self.assertIn("指纹不符", blocked["error"])
        self.rewrite_json(self.g4_validation, candidate={"path": str(self.render), "sha256": sha_upper(self.render.read_bytes())})
        result = self.approve("G4")
        self.assertEqual("G5", result["currentNode"])

    def test_g5_non_json_placeholder_report_blocked(self):
        self.init()
        self.advance_through("G4")
        self.prepare_node("G5")
        self.g5_validation.write_text("fixture", encoding="utf-8")
        blocked = self.approve("G5", code=2)
        self.assertIn("JSON", blocked["error"])

    def test_g5_failed_or_machine_pending_status_blocked(self):
        self.init()
        self.advance_through("G4")
        self.prepare_node("G5")
        for bad in ("invalid", "failed", "pending_g5_machine_checks"):
            self.rewrite_json(self.g5_validation, status=bad)
            blocked = self.approve("G5", code=2)
            self.assertIn("不可批准", blocked["error"])

    def test_g5_report_from_other_project_blocked(self):
        self.init()
        self.advance_through("G4")
        self.prepare_node("G5")
        self.rewrite_json(self.g5_validation, projectId="other-film")
        blocked = self.approve("G5", code=2)
        self.assertIn("不符", blocked["error"])

    def test_g5_report_without_artifact_bindings_blocked(self):
        self.init()
        self.advance_through("G4")
        self.prepare_node("G5")
        self.drop_json_key(self.g5_validation, "artifacts")
        blocked = self.approve("G5", code=2)
        self.assertIn("未登记产物指纹", blocked["error"])

    def test_g5_missing_registered_artifact_blocked(self):
        # 报告登记了产物但交付包里没有实物。
        self.init()
        self.advance_through("G4")
        self.prepare_node("G5")
        self.g5_final.unlink()
        blocked = self.approve("G5", code=2)
        self.assertIn("不在交付包中", blocked["error"])

    def test_g5_tampered_artifact_after_report_blocked(self):
        # 结果过期（含 chapterClips 列表形状同检）：报告后改动任何登记产物 → 拒。
        self.init()
        self.advance_through("G4")
        self.prepare_node("G5")
        self.g5_clip.write_bytes(b"retouched chapter clip")
        blocked = self.approve("G5", code=2)
        self.assertIn("指纹不符", blocked["error"])
        self.assertIn("chapterClips", blocked["error"])

    def test_g5_completed_report_still_bound_to_artifacts(self):
        # completed* 可批（历史封包复检语义），但指纹绑定不因状态宽松而豁免。
        self.init()
        self.advance_through("G4")
        self.prepare_node("G5")
        self.rewrite_json(self.g5_validation, status="completed_with_accepted_warnings")
        self.g5_final.write_bytes(b"swapped final video")
        blocked = self.approve("G5", code=2)
        self.assertIn("指纹不符", blocked["error"])
        self.g5_final.write_bytes(b"fake-final-video")
        self.approve("G5")


if __name__ == "__main__":
    unittest.main()
