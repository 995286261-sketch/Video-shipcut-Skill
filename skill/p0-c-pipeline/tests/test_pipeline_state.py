import hashlib
import json
import os
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
        # v1.35.0 工作台选址硬闸：测试机器环境以 P0C_WORKSPACE_HOME 注入登记根，
        # 项目按正形 <根>/工作台/<projectId>/ 落位（run_cli 子进程继承 env）。
        self.home = Path(self.temp.name).resolve()
        os.environ["P0C_WORKSPACE_HOME"] = str(self.home)
        self.addCleanup(os.environ.pop, "P0C_WORKSPACE_HOME", None)
        self.root = self.home / "工作台" / "demo-001"
        self.root.mkdir(parents=True)
        self.pack = self.home / "material-pack.json"
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
        # 问题⑤（Leader 转场实跑 09-24）：G3 登记校验渲染器出处标记，夹具卡须为渲染器产物形状。
        self.files["G3"]["card"].write_text(
            "# G3 剪辑计划最终回显\n\n此卡由通过校验的 G3 最终回显数据生成。\n", encoding="utf-8")
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
        # ⑫ 甲案：注入文案逐字带上本次 reason，写死句子（"Rebuild narration-to-visual…"）退役
        self.assertIn("plan defect", state["nextAction"])
        self.assertNotIn("Rebuild narration", state["nextAction"])
        self.assertTrue(any("plan defect" in point for point in state["nodes"]["G3"]["humanReviewPoints"]))

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

    def test_reopen_g2_injects_reason_verbatim(self):
        # ⑫ 甲案（reopen-g2 同款病同批修）：回炉 G2 的审核点与 nextAction 逐字带 reason，
        # 旧写死句子（"Amend G2 evidence or approved narration…"）退役。
        self.init()
        self.advance_through("G2")  # currentNode=G3，reopen（G3→G2）的合法起点
        result = self.run_cli("reopen", "--state", self.state, "--reason", "旁白第 3 句证据过期",
                              "--rework-ref", self.file("rework-g2.md"))
        self.assertEqual("G2", result["currentNode"])
        state = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertIn("旁白第 3 句证据过期", state["nextAction"])
        self.assertNotIn("Amend G2 evidence", state["nextAction"])
        self.assertTrue(any("旁白第 3 句证据过期" in point for point in state["nodes"]["G2"]["humanReviewPoints"]))

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
    # 不能仅检查文件存在。有效报告与对应产物匹配且人工批准后才可推进。
    # 注（R2 后）：报告/成片本身也是被审文件，改完必须重新登记（prepare_node 重跑
    # = 重渲卡→record-review），否则先被 R2 的"登记审核后变更"拦下——那正是设计行为；
    # 本组用例先重登记越过 R2，再验 R1 的报告解析层。 ----

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
        self.prepare_node("G4")  # 报告换版后重新登记（越过 R2 卡↔文件层，专测 R1 解析层）
        blocked = self.approve("G4", code=2)
        self.assertIn("JSON", blocked["error"])

    def test_g4_failed_status_blocked(self):
        self.init()
        self.advance_through("G3")
        self.prepare_node("G4")
        self.rewrite_json(self.g4_validation, status="invalid")
        self.prepare_node("G4")
        blocked = self.approve("G4", code=2)
        self.assertIn("不可批准", blocked["error"])

    def test_g4_report_without_candidate_fingerprint_blocked(self):
        # invalid/failed 之外的第三种失败：valid 但没绑成片指纹=报告不指向任何实物。
        self.init()
        self.advance_through("G3")
        self.prepare_node("G4")
        self.drop_json_key(self.g4_validation, "candidate")
        self.prepare_node("G4")
        blocked = self.approve("G4", code=2)
        self.assertIn("未绑定候选成片指纹", blocked["error"])

    def test_g4_report_from_other_project_blocked(self):
        self.init()
        self.advance_through("G3")
        self.prepare_node("G4")
        self.rewrite_json(self.g4_validation, projectId="other-film")
        self.prepare_node("G4")
        blocked = self.approve("G4", code=2)
        self.assertIn("不符", blocked["error"])

    def test_g4_stale_report_after_render_change_blocked(self):
        # 结果过期：重渲候选成片并重新登记（R2 过）后，报告仍描述旧成片 → R1 指纹对不上，逼重跑。
        self.init()
        self.advance_through("G3")
        self.prepare_node("G4")
        self.render.write_bytes(b"re-rendered candidate, report no longer describes this file")
        self.prepare_node("G4")
        blocked = self.approve("G4", code=2)
        self.assertIn("指纹不符", blocked["error"])

    def test_g4_rerun_bound_report_unblocks(self):
        # 过期被拒后，按门禁提示重跑 g4_validate --candidate（等价语义：重新登记真实指纹）
        # 并重新登记 → 放行（修复通道可用）。
        self.init()
        self.advance_through("G3")
        self.prepare_node("G4")
        self.render.write_bytes(b"re-rendered candidate, report no longer describes this file")
        self.prepare_node("G4")
        blocked = self.approve("G4", code=2)
        self.assertIn("指纹不符", blocked["error"])
        self.rewrite_json(self.g4_validation, candidate={"path": str(self.render), "sha256": sha_upper(self.render.read_bytes())})
        self.prepare_node("G4")
        result = self.approve("G4")
        self.assertEqual("G5", result["currentNode"])

    def test_g5_non_json_placeholder_report_blocked(self):
        self.init()
        self.advance_through("G4")
        self.prepare_node("G5")
        self.g5_validation.write_text("fixture", encoding="utf-8")
        self.prepare_node("G5")  # 重新登记后专测 R1 解析层
        blocked = self.approve("G5", code=2)
        self.assertIn("JSON", blocked["error"])

    def test_g5_failed_or_machine_pending_status_blocked(self):
        self.init()
        self.advance_through("G4")
        self.prepare_node("G5")
        for bad in ("invalid", "failed", "pending_g5_machine_checks"):
            self.rewrite_json(self.g5_validation, status=bad)
            self.prepare_node("G5")
            blocked = self.approve("G5", code=2)
            self.assertIn("不可批准", blocked["error"])

    def test_g5_report_from_other_project_blocked(self):
        self.init()
        self.advance_through("G4")
        self.prepare_node("G5")
        self.rewrite_json(self.g5_validation, projectId="other-film")
        self.prepare_node("G5")
        blocked = self.approve("G5", code=2)
        self.assertIn("不符", blocked["error"])

    def test_g5_report_without_artifact_bindings_blocked(self):
        self.init()
        self.advance_through("G4")
        self.prepare_node("G5")
        self.drop_json_key(self.g5_validation, "artifacts")
        self.prepare_node("G5")
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
        # final-video 不在收据引用面（报告↔实物由 R1 管），改它不触发 R2。
        self.init()
        self.advance_through("G4")
        self.prepare_node("G5")
        self.rewrite_json(self.g5_validation, status="completed_with_accepted_warnings")
        self.prepare_node("G5")
        self.g5_final.write_bytes(b"swapped final video")
        blocked = self.approve("G5", code=2)
        self.assertIn("指纹不符", blocked["error"])
        self.g5_final.write_bytes(b"fake-final-video")
        self.approve("G5")

    # ---- Leader 反馈 R2（用户 09-24 裁决）：审批绑定被审文件指纹——登记审核后
    # 同路径替换/修改内容=真人所批版本不存在，旧批准不可复用；须重渲卡→重登记→重确认。 ----

    def test_r2_plan_tampered_after_record_blocked(self):
        # 她复现的原案：登记 G3 卡后偷换计划内容，approve 必须拒（此前放行）。
        self.init()
        self.advance_through("G2")
        self.prepare_node("G3")
        self.plan.write_text(json.dumps({"projectId": "fixture", "status": "approved_for_g3", "segments": ["偷偷加了一段"]}), encoding="utf-8")
        blocked = self.approve("G3", code=2)
        self.assertIn("被审文件已在登记审核后变更", blocked["error"])
        self.assertIn("G3-剪辑计划/plan.json", blocked["error"])

    def test_r2_rerender_and_rerecord_unblocks(self):
        # 修复通道：改动后重渲染卡（新内容）→ 重新登记 → 人工重新确认 → 放行。
        self.init()
        self.advance_through("G2")
        self.prepare_node("G3")
        self.plan.write_text(json.dumps({"projectId": "fixture", "status": "approved_for_g3", "segments": ["v2"]}), encoding="utf-8")
        self.files["G3"]["card"].write_text(
            "# G3 剪辑计划最终回显\n\n此卡由通过校验的 G3 最终回显数据生成。\n\n（v2 重渲染）\n", encoding="utf-8")
        self.prepare_node("G3")
        result = self.approve("G3")
        self.assertEqual("G4", result["currentNode"])

    def test_g3_handwritten_card_without_renderer_marker_blocked(self):
        # 问题⑤（转场实跑 09-24）：编排手制的"长得像"卡必须被登记环节机械拒绝。
        self.init()
        self.advance_through("G2")
        self.prepare_node("G3")
        self.files["G3"]["card"].write_text("# G3 最终回显卡（手制）\n\n| 自拟表头 | 不合规 |\n", encoding="utf-8")
        blocked = self.run_cli("record-review", "--state", self.state, "--node", "G3",
                               "--review-gate-ref", self.receipt("G3"), code=2)
        self.assertIn("render_g3_review_card.py", blocked["error"])
        self.assertIn("缺机器出处标记", blocked["error"])

    def test_r2_approval_record_written_at_close_is_exempt(self):
        # 豁免规则活证：approvalRef 文件本来就是关单时才写的，登记后写它不得误伤。
        self.init()
        self.advance_through("G2")
        self.prepare_node("G3")
        self.files["G3"]["approval"].write_text("用户原话：确认 G3（关单时记录）\n", encoding="utf-8")
        result = self.approve("G3")
        self.assertEqual("G4", result["currentNode"])

    def test_r2_checklist_evidence_tampered_blocked(self):
        # checklist evidenceRef 也在绑定面：登记后改证据文件同样失效。
        self.init()
        self.advance_through("G2")
        self.prepare_node("G3")
        self.files["G3"]["subtitle_timeline"].write_text("retouched evidence", encoding="utf-8")
        blocked = self.approve("G3", code=2)
        self.assertIn("被审文件已在登记审核后变更", blocked["error"])

    def test_r2_validation_report_swapped_after_record_blocked(self):
        # 卡↔报告层（与 R1 互补）：登记 G4 卡后整个换掉验证报告文件——不重登记就想批=拒。
        self.init()
        self.advance_through("G3")
        self.prepare_node("G4")
        # 换入一份"内容不同但 R1 本会通过"的报告（如另一次运行的产物）：靠 R2 指纹层拦下。
        self.g4_validation.write_text(json.dumps({
            "status": "valid", "projectId": "fixture", "segments": 9, "timelineDurationMs": 1000,
            "candidate": {"path": str(self.render), "sha256": sha_upper(self.render.read_bytes())}}), encoding="utf-8")
        blocked = self.approve("G4", code=2)
        self.assertIn("被审文件已在登记审核后变更", blocked["error"])

    def test_r2_legacy_snapshot_without_hashes_blocked(self):
        # 升级前登记的在途门禁（快照无 basisHashes）→ 硬切：指路重新登记。
        self.init()
        self.advance_through("G2")
        self.prepare_node("G3")
        state = json.loads(self.state.read_text(encoding="utf-8"))
        del state["nodes"]["G3"]["reviewGate"]["basisHashes"]
        self.state.write_text(json.dumps(state), encoding="utf-8")
        blocked = self.approve("G3", code=2)
        self.assertIn("缺少被审文件指纹", blocked["error"])

    def test_r2_unreferenced_file_change_does_not_block(self):
        # 绑定面只含卡引用的文件：项目里无关文件的改动不得误伤审批。
        self.init()
        self.advance_through("G2")
        self.prepare_node("G3")
        self.file("G3-剪辑计划/unrelated-worknote.md")
        result = self.approve("G3")
        self.assertEqual("G4", result["currentNode"])

    def test_r2_approval_records_source_and_frozen_versions(self):
        # 她要求的留痕：批准记录含来源、时间、口令，且快照冻结了被审文件指纹。
        self.init()
        self.advance_through("G2")
        self.prepare_node("G3")
        self.approve("G3")
        state = json.loads(self.state.read_text(encoding="utf-8"))
        approval = state["nodes"]["G3"]["approval"]
        self.assertEqual("host-session", approval["approvalSource"])
        self.assertTrue(approval["approvedAt"])
        gates = state["nodes"]["G3"]["reviewGate"]
        # 已关单门禁保留 basisHashes 作审计（含卡与计划两枚指纹）。
        self.assertIn(str(self.plan), gates["basisHashes"])
        self.assertIn(str(self.files["G3"]["card"]), gates["basisHashes"])


    # ---- v1.22.0 自动确认模式（approvalMode=auto）：机器验收链照跑，口令段换成
    # 策略预检；信任类事项未被预授权覆盖一律 fail-stop；留痕如实写 auto-policy，
    # 绝不伪造人类原话；auto 项目里人工口令裁决单闸=如实双记（host-session+override）。 ----

    AUTO_STATEMENT = "本项目以自动确认模式运行：各闸由机器验收+策略自动批准；信任类事项按预授权清单执行，未覆盖一律停下等人。"

    def preauth(self, category, basis=None, **params):
        entry = {"category": category,
                 "basis": basis or f"{category}：委托方于输入端预授权（测试夹具）",
                 "authorizedBy": "委托方（输入端）", "authorizedAt": "2026-09-30T00:00:00Z"}
        if params:
            entry["parameters"] = params
        return entry

    def write_policy(self, preauths=None, project_id="fixture", statement=None):
        policy = {"schemaVersion": "0.1", "kind": "auto-approval-policy", "projectId": project_id,
                  "statement": self.AUTO_STATEMENT if statement is None else statement,
                  "preAuthorizations": list(preauths or [])}
        path = self.root / "auto-policy.json"
        path.write_text(json.dumps(policy, ensure_ascii=False), encoding="utf-8")
        return path

    def init_auto(self, preauths=None, authorization="authorized", distribution="local_only"):
        policy = self.write_policy(preauths)
        return self.run_cli("init", "--project-id", "fixture", "--source-pack", self.pack, "--state", self.state,
                            "--authorization", authorization, "--distribution", distribution,
                            "--approval-mode", "auto", "--auto-policy", policy)

    def approve_auto(self, node, code=0, accepted=None):
        args = ["approve", "--state", self.state, "--node", node, "--auto",
                "--approval-ref", self.files[node]["approval"]]
        if node == "G2":
            args += ["--approved-narration-ref", self.narration, "--fact-citation-ref", self.facts, "--voice-brief-ref", self.voice]
        elif node == "G3":
            args += ["--edit-plan-ref", self.plan, "--timeline-review-ref", self.timeline]
        elif node == "G4":
            args += ["--local-render-ref", self.render, "--g4-validation-ref", self.g4_validation]
        elif node == "G5":
            args += ["--delivery-manifest-ref", self.delivery, "--g5-validation-ref", self.g5_validation]
            for warning in accepted or []:
                args += ["--accepted-warning", warning]
        return self.run_cli(*args, code=code)

    def run_auto_to(self, node, preauths=None):
        self.init_auto(preauths=preauths)
        for step in ("G1", "G2", "G3", "G4", "G5"):
            if step == node:
                return
            self.prepare_node(step)
            self.approve_auto(step)

    def write_g5_decision(self, performed=False, replaced="auto-policy:auto-policy.json"):
        doc = {"projectId": "fixture", "status": "approved", "decision": "accepted",
               "performed": performed, "acceptedWarnings": []}
        if replaced is not None:
            doc["replacedBy"] = replaced
        return self.json_file("G5-交付包/交付包-v0.1/human-review-decision.json", doc)

    def test_auto_init_requires_policy_and_records_mode(self):
        blocked = self.run_cli("init", "--project-id", "fixture", "--source-pack", self.pack, "--state", self.state,
                               "--authorization", "authorized", "--distribution", "local_only",
                               "--approval-mode", "auto", code=2)
        self.assertIn("--auto-policy", blocked["error"])
        result = self.init_auto()
        self.assertEqual("auto", result["approvalMode"])
        state = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual("auto", state["approvalMode"])
        self.assertTrue(state["autoPolicyRef"])
        # 不声明模式=human（安全兜底），字段显式落盘
        self.state.unlink()
        self.init()
        self.assertEqual("human", json.loads(self.state.read_text(encoding="utf-8"))["approvalMode"])

    def test_auto_policy_rejects_unknown_category_and_foreign_project(self):
        # 词表外类别当场拒——永久项（未清权×对外等）没有预授权通道，词表不可扩展
        self.write_policy([{"category": "distribution_rights_override", "basis": "试图绕过权益闸",
                            "authorizedBy": "x", "authorizedAt": "2026-09-30T00:00:00Z"}])
        blocked = self.run_cli("init", "--project-id", "fixture", "--source-pack", self.pack, "--state", self.state,
                               "--authorization", "authorized", "--distribution", "local_only",
                               "--approval-mode", "auto", "--auto-policy", self.root / "auto-policy.json", code=2)
        self.assertIn("受控词表", blocked["error"])
        self.write_policy(project_id="other-project")
        blocked = self.run_cli("init", "--project-id", "fixture", "--source-pack", self.pack, "--state", self.state,
                               "--authorization", "authorized", "--distribution", "local_only",
                               "--approval-mode", "auto", "--auto-policy", self.root / "auto-policy.json", code=2)
        self.assertIn("不符", blocked["error"])

    def test_auto_full_chain_records_policy_source(self):
        self.init_auto(preauths=[self.preauth("subject_policy", basis="主体政策由输入工单承载：目标主体=fixture 机体")])
        for node in ("G1", "G2", "G3", "G4"):
            self.prepare_node(node)
            self.approve_auto(node)
        self.write_g5_decision()
        self.prepare_node("G5")
        self.approve_auto("G5")
        state = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual("completed", state["currentNode"])
        self.assertEqual("completed_auto_reviewed", state["status"])
        self.assertEqual("completed_auto_reviewed", state["nodes"]["G5"]["status"])
        for node in ("G1", "G2", "G3", "G4", "G5"):
            approval = state["nodes"][node]["approval"]
            self.assertEqual("auto-policy", approval["approvalSource"])
            self.assertEqual(f"auto-policy:{node}", approval["approvalToken"])
            self.assertIn("自动确认模式", approval["approvalTokenVerbatim"])
            self.assertFalse(approval["normalizedFromVariant"])
        self.assertEqual(["subject_policy"], state["nodes"]["G3"]["approval"]["preAuthorizationsUsed"])

    def test_auto_mixing_token_and_flag_rejected(self):
        self.init_auto()
        self.prepare_node("G1")
        blocked = self.run_cli("approve", "--state", self.state, "--node", "G1", "--auto",
                               "--approval-ref", self.files["G1"]["approval"],
                               "--approval-token", "确认 G1", "--approval-response", "确认 G1", code=2)
        self.assertIn("混用", blocked["error"])

    def test_auto_flag_on_human_project_rejected(self):
        self.init()
        self.prepare_node("G1")
        blocked = self.run_cli("approve", "--state", self.state, "--node", "G1", "--auto",
                               "--approval-ref", self.files["G1"]["approval"], code=2)
        self.assertIn("approvalMode=human", blocked["error"])

    def test_human_mode_still_requires_token(self):
        self.init()
        self.prepare_node("G1")
        blocked = self.run_cli("approve", "--state", self.state, "--node", "G1",
                               "--approval-ref", self.files["G1"]["approval"], code=2)
        self.assertIn("人工批准必须携带", blocked["error"])

    def test_auto_failstop_preview_voice_and_preauth_cures(self):
        self.init_auto()
        self.prepare_node("G1")
        self.approve_auto("G1")
        self.voice.write_text(json.dumps({"voiceTier": "preview_only", "lines": 3}), encoding="utf-8")
        self.prepare_node("G2")
        blocked = self.approve_auto("G2", code=2)
        self.assertIn("preview_voice_production", blocked["error"])
        self.assertIn("自动确认受阻", blocked["error"])
        self.assertTrue(blocked["autoApprovalBlocked"]["missingPreAuthorizations"])
        # 预授权缺披露词'预览级' → 策略校验当场拒
        self.write_policy([self.preauth("preview_voice_production", basis="系统声直接进成片")])
        blocked = self.approve_auto("G2", code=2)
        self.assertIn("预览级", blocked["error"])
        self.write_policy([self.preauth("preview_voice_production", basis="委托方知情接受预览级系统声用于成片")])
        result = self.approve_auto("G2")
        self.assertEqual("G3", result["currentNode"])
        approval = json.loads(self.state.read_text(encoding="utf-8"))["nodes"]["G2"]["approval"]
        self.assertEqual(["preview_voice_production"], approval["preAuthorizationsUsed"])
        self.assertIn("预览级", approval["approvalTokenVerbatim"])

    def test_auto_failstop_loudness_blocked_exit(self):
        self.init_auto()
        self.prepare_node("G1")
        self.approve_auto("G1")
        loud = self.json_file("G2-证据与口播/响度-归一化计划-v0.1.json", {
            "skill": "loudness-expert", "purpose": "loud_plan", "status": "blocked_true-peak",
            "exits": ["先压缩后测：先跑压缩链再重新规划", "把目标响度降到 -24.3 LUFS"]})
        self.prepare_node("G2", basis_refs=[self.narration, self.facts, self.voice, loud])
        blocked = self.approve_auto("G2", code=2)
        self.assertIn("loudness_blocked_exit", blocked["error"])
        # 预授权指了不存在的出路 → 参数与现场事实对不上，仍拦
        self.write_policy([self.preauth("loudness_blocked_exit", exit="放弃响度控制")])
        blocked = self.approve_auto("G2", code=2)
        self.assertIn("参数与现场事实对不上", blocked["error"])
        self.write_policy([self.preauth("loudness_blocked_exit", exit="先压缩后测")])
        result = self.approve_auto("G2")
        self.assertEqual("G3", result["currentNode"])

    def test_auto_failstop_transition_waiver_and_sufficiency(self):
        self.init_auto(preauths=[self.preauth("subject_policy")])
        self.prepare_node("G1")
        self.approve_auto("G1")
        self.prepare_node("G2")
        self.approve_auto("G2")
        waiver = self.json_file("G3-剪辑计划/转场-预览清单-v0.1.json", {
            "transitionPreviewWaiver": {"status": "blocked_previews", "disclosure": "你批准的是未见过的效果"}})
        self.prepare_node("G3", basis_refs=[self.plan, self.timeline, waiver])
        blocked = self.approve_auto("G3", code=2)
        categories = [item["category"] for item in blocked["autoApprovalBlocked"]["missingPreAuthorizations"]]
        self.assertIn("transition_preview_waiver", categories)
        # 计划带充分性缩短兜底 → sufficiency_shorten 也上缺口清单
        self.plan.write_text(json.dumps({"targetSubject": {"userConfirmed": True,
                                                           "sufficiencyFallback": {"preApproved": "shorten_output"}}}), encoding="utf-8")
        self.prepare_node("G3", basis_refs=[self.plan, self.timeline, waiver])
        blocked = self.approve_auto("G3", code=2)
        categories = [item["category"] for item in blocked["autoApprovalBlocked"]["missingPreAuthorizations"]]
        self.assertIn("transition_preview_waiver", categories)
        self.assertIn("sufficiency_shorten", categories)
        self.write_policy([self.preauth("subject_policy"), self.preauth("transition_preview_waiver"),
                           self.preauth("sufficiency_shorten")])
        result = self.approve_auto("G3")
        self.assertEqual("G4", result["currentNode"])

    def test_auto_failstop_warning_acceptance_g4_and_g5(self):
        self.run_auto_to("G4", preauths=[self.preauth("subject_policy")])
        assembly = self.json_file("G4-剪辑与渲染/装配记录.json", {
            "pureNarration": {"verdict": "disclosed-exceedance", "measuredLufs": -15.6}})
        self.prepare_node("G4", basis_refs=[self.render, self.g4_validation, assembly])
        blocked = self.approve_auto("G4", code=2)
        self.assertIn("warning_acceptance", blocked["error"])
        self.write_policy([self.preauth("subject_policy"), self.preauth("warning_acceptance", scopes=["响度"])])
        result = self.approve_auto("G4")
        self.assertEqual("G5", result["currentNode"])
        # G5：包内响度审计 disclosed-exceedance + 接受警告点名响度
        self.json_file("G5-交付包/交付包-v0.1/loudness-audit.json", {
            "skill": "loudness-expert", "purpose": "loud_verify", "status": "disclosed-exceedance"})
        self.write_g5_decision()
        self.write_policy([self.preauth("subject_policy")])
        self.prepare_node("G5")
        blocked = self.approve_auto("G5", code=2)
        self.assertIn("warning_acceptance", blocked["error"])
        # scope 不覆盖现场警告 → 仍拦
        self.write_policy([self.preauth("subject_policy"), self.preauth("warning_acceptance", scopes=["水印"])])
        blocked = self.approve_auto("G5", accepted=["响度：实测 −15.5 超容差"], code=2)
        self.assertIn("参数与现场事实对不上", blocked["error"])
        self.write_policy([self.preauth("subject_policy"), self.preauth("warning_acceptance", scopes=["响度"])])
        self.approve_auto("G5", accepted=["响度：实测 −15.5 超容差"])
        state = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual("completed_auto_reviewed_with_accepted_warnings", state["status"])

    def test_auto_permanent_failstop_uncleared_external(self):
        self.pack.write_text(json.dumps({"packStatus": "complete", "audioAssets": [
            {"assetId": "bgm-001", "licenseType": "uncleared-platform-catalog"}]}), encoding="utf-8")
        self.init_auto(preauths=[self.preauth("subject_policy")], distribution="public_bilibili")
        self.prepare_node("G1")
        blocked = self.approve_auto("G1", code=2)
        self.assertIn("永久不可预授权", blocked["error"])
        self.assertIn("uncleared", blocked["error"])
        self.assertTrue(blocked["autoApprovalBlocked"]["permanent"])

    def test_auto_permanent_failstop_unknown_authorization_external(self):
        self.init_auto(authorization="unknown", distribution="public_bilibili")
        self.prepare_node("G1")
        blocked = self.approve_auto("G1", code=2)
        self.assertIn("授权不明", blocked["error"])

    def test_auto_permanent_failstop_manual_claims(self):
        self.init_auto()
        self.prepare_node("G1")
        self.approve_auto("G1")
        decision = self.json_file("G2-证据与口播/G2-审批决定-v0.1.json", {
            "schemaVersion": "0.2", "node": "G2", "projectId": "fixture", "status": "approved_for_g3",
            "userManuallyVerifiedClaims": ["委托方口头背书某主张"], "provenanceRule": "not first-party verified"})
        self.prepare_node("G2", basis_refs=[self.narration, self.facts, self.voice, decision])
        blocked = self.approve_auto("G2", code=2)
        self.assertIn("userManuallyVerifiedClaims", blocked["error"])

    def test_auto_bgm_flip_requires_delegated_selection(self):
        self.pack.write_text(json.dumps({"packStatus": "complete", "bgm": {
            "decision": "use_library_later", "preference": None, "libraryPending": True,
            "clearCondition": "G1 末检索"}}, ensure_ascii=False), encoding="utf-8")
        self.init_auto()
        blocked = self.run_cli("bgm-choice", "--state", self.state, "--decision", "no_bgm",
                               "--note", "系统想代拍", code=2)
        self.assertIn("music_delegated_selection", blocked["error"])
        self.write_policy([self.preauth("music_delegated_selection")])
        result = self.run_cli("bgm-choice", "--state", self.state, "--decision", "no_bgm",
                              "--note", "输入端预授权委托选定")
        self.assertEqual("recorded", result["status"])

    def test_auto_failstop_then_human_resolves_single_gate_and_auto_resumes(self):
        self.init_auto()  # 无任何预授权
        self.prepare_node("G1")
        self.approve_auto("G1")
        self.prepare_node("G2")
        self.approve_auto("G2")
        self.prepare_node("G3")
        blocked = self.approve_auto("G3", code=2)
        self.assertIn("subject_policy", blocked["error"])
        # 人工裁决本闸：口令路径，如实记 host-session + override 双记
        result = self.approve("G3")
        self.assertEqual("G4", result["currentNode"])
        state = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual("host-session", state["nodes"]["G3"]["approval"]["approvalSource"])
        self.assertTrue(state["nodes"]["G3"]["approval"]["autoModeOverride"])
        # 后续闸恢复自动
        self.prepare_node("G4")
        self.approve_auto("G4")
        self.write_g5_decision()
        self.prepare_node("G5")
        self.approve_auto("G5")
        state = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual("completed_auto_reviewed", state["status"])
        self.assertEqual("auto-policy", state["nodes"]["G5"]["approval"]["approvalSource"])

    def test_auto_r2_tamper_still_blocks(self):
        self.init_auto()
        self.prepare_node("G1")
        self.files["G1"]["basis"].write_text("tampered", encoding="utf-8")
        blocked = self.approve_auto("G1", code=2)
        self.assertIn("被审文件已在登记审核后变更", blocked["error"])
        self.prepare_node("G1")
        result = self.approve_auto("G1")
        self.assertEqual("G2", result["currentNode"])

    def test_auto_g5_requires_disclosed_decision_shape(self):
        self.run_auto_to("G5", preauths=[self.preauth("subject_policy")])
        self.prepare_node("G5")
        blocked = self.approve_auto("G5", code=2)
        self.assertIn("human-review-decision.json", blocked["error"])
        self.write_g5_decision(performed=True, replaced=None)
        blocked = self.approve_auto("G5", code=2)
        self.assertIn("不得声称做过人工审", blocked["error"])
        self.write_g5_decision()
        result = self.approve_auto("G5")
        self.assertEqual("completed", result["currentNode"])

    def test_human_g5_rejects_exempt_shape(self):
        self.init()
        self.advance_through("G4")
        self.write_g5_decision()  # performed:false 的自动披露形状
        self.prepare_node("G5")
        blocked = self.approve("G5", code=2)
        self.assertIn("performed:false 免审声明", blocked["error"])
        self.write_g5_decision(performed=True, replaced=None)
        result = self.approve("G5")
        self.assertEqual("completed", result["currentNode"])

    def test_set_approval_mode_requires_reason_and_policy(self):
        self.init()
        blocked = self.run_cli("set-approval-mode", "--state", self.state, "--mode", "auto",
                               "--reason", "想试试自动", code=2)
        self.assertIn("auto-policy", blocked["error"])
        policy = self.write_policy([self.preauth("subject_policy")])
        self.run_cli("set-approval-mode", "--state", self.state, "--mode", "auto",
                     "--reason", "输入端授权自动跑", "--auto-policy", policy)
        state = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual("auto", state["approvalMode"])
        self.assertEqual(1, len(state["approvalModeHistory"]))
        self.assertEqual("输入端授权自动跑", state["approvalModeHistory"][0]["reason"])
        unchanged = self.run_cli("set-approval-mode", "--state", self.state, "--mode", "auto", "--reason", "重复")
        self.assertEqual("unchanged", unchanged["status"])
        self.assertEqual(1, len(json.loads(self.state.read_text(encoding="utf-8"))["approvalModeHistory"]))
        self.run_cli("set-approval-mode", "--state", self.state, "--mode", "human", "--reason", "转回人工")
        state = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual("human", state["approvalMode"])
        self.assertEqual(2, len(state["approvalModeHistory"]))


if __name__ == "__main__":
    unittest.main()
