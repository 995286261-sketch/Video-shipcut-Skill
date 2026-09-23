import json
import subprocess
import sys
import tempfile
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_g3_callback.py"
RENDERER = ROOT / "scripts" / "render_g3_review_card.py"
PYTHON = sys.executable
spec = importlib.util.spec_from_file_location("validate_g3_callback", SCRIPT)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class G3CallbackValidatorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def write(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def plan(self):
        segments = []
        for number, start in enumerate((0, 1000), 1):
            segments.append({"segmentId": f"seg-{number:03}", "startMs": start + 10000, "endMs": start + 11000,
                "outputStartMs": start, "outputEndMs": start + 1000,
                "visualVerification": {"status": "verified"}, "semanticAlignment": {"status": "direct_match"}})
        return self.write("plan.json", {"projectId": "p", "segments": segments})

    def callback(self):
        rows = []
        for number, start in enumerate((0, 1000), 1):
            rows.append({"segmentId": f"seg-{number:03}", "outputStartMs": start, "outputEndMs": start + 1000,
                "outputTimecode": validator.format_review_range(start, start + 1000),
                "narrationText": "口播原文", "sourceStartMs": start + 10000, "sourceEndMs": start + 11000,
                "sourceTimecode": validator.format_review_range(start + 10000, start + 11000),
                "observedVisuals": "实际可见的目标主体", "semanticStatus": "direct_match", "subjectStatus": "target_confirmed",
                "riskSummary": "左上角水印需裁切", "bgmPhrase": "phrase-01", "transitionInstruction": "硬切"})
        return {"schemaVersion": "0.1", "node": "G3", "projectId": "p", "callbackType": "final_review",
            "durationMs": 2000, "columns": ["片段 ID", "输出时间", "对应口播", "源片区间", "用途 / 实际画面观察", "语义匹配 / 主体状态 / 风险", "BGM 乐句", "转场指令"], "rows": rows}

    def run_cli(self, callback, plan=None, alignment=None):
        callback_path = self.write("callback.json", callback)
        command = [PYTHON, str(SCRIPT), "--callback", str(callback_path)]
        if plan:
            command += ["--plan", str(plan)]
        if alignment:
            command += ["--alignment", str(alignment)]
        return subprocess.run(command, capture_output=True, text=True, encoding="utf-8")

    def bgm_plan(self):
        plan = json.loads(self.plan().read_text(encoding="utf-8"))
        plan["timelineDurationMs"] = 2000
        for segment in plan["segments"]:
            segment["layoutTier"] = "推进"
        plan["bgmPlan"] = {"trackOffsetMs": 60000, "alignmentRef": "G3-剪辑计划/BGM-对齐建议-v0.2.json"}
        return self.write("plan-bgm.json", plan)

    def alignment_artifact(self, snapped=3, missed=1, ducking=2):
        value = {
            "schemaVersion": "0.2", "purpose": "bgm_alignment",
            "alignment": {"offsetMs": 60000, "timelineMs": 2000},
            "snapped": [] if snapped == 1 else [{"x": i} for i in range(snapped)],
            "missed": [{"x": 0}] if missed else [],
            "ducking": [{"sentenceId": f"N0{i}"} for i in range(1, ducking + 1)],
        }
        return self.write("alignment.json", value)

    def callback_v02(self, **basis_changes):
        value = self.callback()
        value["schemaVersion"] = "0.2"
        for row in value["rows"]:
            row["layoutTier"] = "推进"
        basis = {"alignmentRef": "G3-剪辑计划/BGM-对齐建议-v0.2.json", "trackOffsetMs": 60000,
                 "timelineMs": 2000, "snappedCount": 3, "missedCount": 1, "duckedSentences": 2}
        basis.update(basis_changes)
        value["bgmBasis"] = basis
        return value

    def test_valid_final_callback_passes(self):
        result = self.run_cli(self.callback(), self.plan())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_missing_output_time_field_is_blocked(self):
        value = self.callback()
        del value["rows"][0]["outputStartMs"]
        result = self.run_cli(value, self.plan())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outputStartMs", result.stdout)

    def test_missing_or_mismatched_display_timecode_is_blocked(self):
        value = self.callback()
        del value["rows"][0]["outputTimecode"]
        result = self.run_cli(value, self.plan())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outputTimecode", result.stdout)
        value = self.callback()
        value["rows"][0]["sourceTimecode"] = "00:00.000–00:01.000"
        result = self.run_cli(value, self.plan())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sourceTimecode", result.stdout)

    def test_review_timecode_formatting(self):
        self.assertEqual("00:00.000", validator.format_review_timecode(0))
        self.assertEqual("00:00.001", validator.format_review_timecode(1))
        self.assertEqual("01:01.234", validator.format_review_timecode(61_234))
        self.assertEqual("61:01.234", validator.format_review_timecode(3_661_234))

    def test_renderer_emits_human_readable_ranges(self):
        callback_path = self.write("callback.json", self.callback())
        plan_path = self.plan()
        output = self.root / "G3-回显卡.md"
        result = subprocess.run([PYTHON, str(RENDERER), "--callback", str(callback_path), "--plan", str(plan_path), "--output", str(output)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        card = output.read_text(encoding="utf-8")
        self.assertIn("00:00.000–00:01.000", card)
        self.assertIn("00:10.000–00:11.000", card)
        self.assertIn("确认 G3", card)

    def test_wrong_column_order_is_blocked(self):
        value = self.callback()
        value["columns"].pop()
        result = self.run_cli(value, self.plan())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fixed eight-column", result.stdout)

    def test_three_clips_cannot_cover_longer_timeline(self):
        value = self.callback()
        value["durationMs"] = 105648
        value["rows"] = value["rows"][:1]
        result = self.run_cli(value, self.plan())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exactly one row", result.stdout)

    def test_candidate_placeholder_is_blocked(self):
        value = self.callback()
        value["rows"][0]["bgmPhrase"] = "候选 phrase"
        result = self.run_cli(value, self.plan())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("placeholder", result.stdout)

    def test_semantic_mismatch_is_blocked(self):
        value = self.callback()
        value["rows"][0]["semanticStatus"] = "semantic_mismatch"
        result = self.run_cli(value, self.plan())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("semanticStatus", result.stdout)

    def test_bgm_card_v02_happy_path(self):
        result = self.run_cli(self.callback_v02(), self.bgm_plan(), self.alignment_artifact())
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_bgm_plan_requires_card_v02(self):
        result = self.run_cli(self.callback(), self.bgm_plan(), self.alignment_artifact())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("schemaVersion 0.2", result.stdout)

    def test_bgm_basis_counts_must_match_alignment_artifact(self):
        result = self.run_cli(self.callback_v02(snappedCount=9), self.bgm_plan(), self.alignment_artifact())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("snap counts", result.stdout)
        result = self.run_cli(self.callback_v02(duckedSentences=5), self.bgm_plan(), self.alignment_artifact())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duckedSentences", result.stdout)

    def test_bgm_basis_offset_must_match_plan(self):
        result = self.run_cli(self.callback_v02(trackOffsetMs=61000), self.bgm_plan(), self.alignment_artifact())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("trackOffsetMs", result.stdout)

    def test_row_layout_tier_must_match_plan_and_vocabulary(self):
        value = self.callback_v02()
        value["rows"][0]["layoutTier"] = "乱来"
        result = self.run_cli(value, self.bgm_plan(), self.alignment_artifact())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("layoutTier must be one of", result.stdout)
        value = self.callback_v02()
        value["rows"][0]["layoutTier"] = "留白"
        result = self.run_cli(value, self.bgm_plan(), self.alignment_artifact())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must equal the plan", result.stdout)

    def test_renderer_shows_bgm_basis_block_and_tier(self):
        callback_path = self.write("callback.json", self.callback_v02())
        plan_path = self.bgm_plan()
        alignment_path = self.alignment_artifact()
        output = self.root / "G3-回显卡-v0.2.md"
        result = subprocess.run([PYTHON, str(RENDERER), "--callback", str(callback_path), "--plan", str(plan_path),
                                 "--alignment", str(alignment_path), "--output", str(output)],
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        card = output.read_text(encoding="utf-8")
        self.assertIn("## BGM 依据区", card)
        self.assertIn("从音轨 01:00.000 起铺", card)
        self.assertIn("3/4", card)
        self.assertIn("phrase-01 · 推进档", card)


class G3PreviewGateTests(unittest.TestCase):
    """试装预览硬门禁（批②）：缺=拒、stale=拒、样被改=拒、豁免=如实披露才放行。
    进程内直调 validate_final/render（不起子进程，路径与哈希合同不变）。"""

    def setUp(self):
        render_spec = importlib.util.spec_from_file_location("render_g3_review_card_t2", RENDERER)
        self.render = importlib.util.module_from_spec(render_spec)
        render_spec.loader.exec_module(self.render)

    def transition_plan_payload(self, with_transition=True):
        segments = []
        for number, start in enumerate((0, 1000), 1):
            seg = {"segmentId": f"seg-{number:03}", "startMs": start + 10000, "endMs": start + 11000,
                   "outputStartMs": start, "outputEndMs": start + 1000,
                   "visualVerification": {"status": "verified"}, "semanticAlignment": {"status": "direct_match"}}
            if with_transition and number == 1:
                seg.update({"transitionInstruction": "叠化", "transitionDurationMs": 500})
            segments.append(seg)
        return {"projectId": "p", "segments": segments, "timelineDurationMs": 2000}

    def transition_callback(self, **extra):
        rows = []
        for number, start in enumerate((0, 1000), 1):
            row = {"segmentId": f"seg-{number:03}", "outputStartMs": start, "outputEndMs": start + 1000,
                   "outputTimecode": validator.format_review_range(start, start + 1000),
                   "narrationText": "口播原文", "sourceStartMs": start + 10000, "sourceEndMs": start + 11000,
                   "sourceTimecode": validator.format_review_range(start + 10000, start + 11000),
                   "observedVisuals": "实际可见的目标主体", "semanticStatus": "direct_match",
                   "subjectStatus": "target_confirmed", "riskSummary": "左上角水印需裁切",
                   "bgmPhrase": "phrase-01", "transitionInstruction": "硬切"}
            if number == 1:
                row.update({"transitionInstruction": "叠化", "transitionDurationMs": 500})
            rows.append(row)
        value = {"schemaVersion": "0.1", "node": "G3", "projectId": "p", "callbackType": "final_review",
                 "durationMs": 2000, "columns": list(validator.FINAL_HEADERS), "rows": rows}
        value.update(extra)
        return value

    def artifacts(self, plan_payload=None):
        import hashlib
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        plan_path = root / "plan.json"
        plan_path.write_text(json.dumps(plan_payload or self.transition_plan_payload(), ensure_ascii=False), encoding="utf-8")
        sample_dir = root / "预览小样"
        sample_dir.mkdir()
        clip = sample_dir / "转场预览-seg-001toseg-002-v0.1.mp4"
        clip.write_bytes(b"fake clip bytes")
        (sample_dir / "转场-预览观看页-v0.1.html").write_text("<html>观看页</html>", encoding="utf-8")
        manifest = {"skill": "transition-expert", "purpose": "transition_preview", "audio": False, "version": "v0.1",
                    "viewerPage": "转场-预览观看页-v0.1.html",
                    "planSha256": hashlib.sha256(plan_path.read_bytes()).hexdigest().upper(),
                    "previews": [{"boundary": "seg-001→seg-002", "type": "叠化", "durationMs": 500,
                                  "windowMs": [250, 1500], "file": clip.name,
                                  "sha256": hashlib.sha256(clip.read_bytes()).hexdigest().upper()}]}
        manifest_path = sample_dir / "转场-预览清单-v0.1.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        return plan_path, manifest_path, json.loads(plan_path.read_text(encoding="utf-8")), manifest

    def check(self, callback, plan_path, plan, manifest_path=None, manifest=None):
        validator.validate_final(callback, plan, None,
                                 plan_path=plan_path, preview_path=manifest_path, preview=manifest)

    def test_missing_preview_blocked(self):
        plan_path, _, plan, _ = self.artifacts()
        with self.assertRaises(ValueError) as caught:
            self.check(self.transition_callback(), plan_path, plan)
        self.assertIn("硬门禁", str(caught.exception))
        self.assertIn("seg-001→seg-002", str(caught.exception))

    def test_matching_preview_passes_and_renders_links(self):
        plan_path, manifest_path, plan, manifest = self.artifacts()
        callback = self.transition_callback(transitionPreviewRef=str(manifest_path))
        self.check(callback, plan_path, plan, manifest_path, manifest)  # 不抛=过检
        card = self.render.render(callback, manifest, manifest_path, manifest_path.parent.parent / "G3-回显卡.md")
        self.assertIn("## 转场试装预览（先看后批）", card)
        self.assertIn("[转场预览-seg-001toseg-002-v0.1.mp4](预览小样/转场预览-seg-001toseg-002-v0.1.mp4)", card)
        self.assertIn("纯画面无声", card)
        self.assertIn("seg-001→seg-002 ｜ 叠化 · 00:00.500", card)
        # 用户 09-23 拍板：卡下统一附一页看全部
        self.assertIn("[一页看全部：转场预览观看页 v0.1](预览小样/转场-预览观看页-v0.1.html)", card)

    def test_viewer_page_link_absent_for_old_manifest(self):
        # 批②时期清单无 viewerPage 字段：卡照常渲染、不编造链接（能力可以缺、事实不能编）
        plan_path, manifest_path, plan, manifest = self.artifacts()
        manifest.pop("viewerPage")
        callback = self.transition_callback(transitionPreviewRef=str(manifest_path))
        card = self.render.render(callback, manifest, manifest_path, manifest_path.parent.parent / "G3-回显卡.md")
        self.assertIn("## 转场试装预览（先看后批）", card)
        self.assertNotIn("一页看全部", card)

    def test_stale_plan_hash_blocked(self):
        plan_path, manifest_path, plan, manifest = self.artifacts()
        manifest["planSha256"] = "0" * 64
        callback = self.transition_callback(transitionPreviewRef=str(manifest_path))
        with self.assertRaises(ValueError) as caught:
            self.check(callback, plan_path, plan, manifest_path, manifest)
        self.assertIn("stale", str(caught.exception))

    def test_tampered_clip_blocked(self):
        plan_path, manifest_path, plan, manifest = self.artifacts()
        (manifest_path.parent / manifest["previews"][0]["file"]).write_bytes(b"tampered")
        callback = self.transition_callback(transitionPreviewRef=str(manifest_path))
        with self.assertRaises(ValueError) as caught:
            self.check(callback, plan_path, plan, manifest_path, manifest)
        self.assertIn("哈希不符", str(caught.exception))

    def test_missing_viewer_page_file_blocked(self):
        plan_path, manifest_path, plan, manifest = self.artifacts()
        (manifest_path.parent / manifest["viewerPage"]).unlink(missing_ok=True)
        callback = self.transition_callback(transitionPreviewRef=str(manifest_path))
        with self.assertRaises(ValueError) as caught:
            self.check(callback, plan_path, plan, manifest_path, manifest)
        self.assertIn("死链", str(caught.exception))

    def test_boundary_set_mismatch_blocked(self):
        plan_path, manifest_path, plan, manifest = self.artifacts()
        manifest["previews"][0]["boundary"] = "seg-999→seg-998"
        callback = self.transition_callback(transitionPreviewRef=str(manifest_path))
        with self.assertRaises(ValueError) as caught:
            self.check(callback, plan_path, plan, manifest_path, manifest)
        self.assertIn("不一一对应", str(caught.exception))

    def test_waiver_with_disclosure_passes(self):
        plan_path, _, plan, _ = self.artifacts()
        callback = self.transition_callback(transitionPreviewWaiver={
            "status": "blocked_previews", "reason": "宿主未安装 ffmpeg",
            "disclosure": "本机无法生成预览：你批准的是未见过的效果"})
        self.check(callback, plan_path, plan)  # 不抛=豁免放行
        card = self.render.render(callback, None, None, Path("G3-回显卡.md"))
        self.assertIn("能力豁免披露", card)
        self.assertIn("未见过的效果", card)

    def test_fabricated_waiver_shape_rejected(self):
        plan_path, _, plan, _ = self.artifacts()
        callback = self.transition_callback(transitionPreviewWaiver={"status": "completed", "reason": "忘了跑"})
        with self.assertRaises(ValueError) as caught:
            self.check(callback, plan_path, plan)
        self.assertIn("blocked_previews", str(caught.exception))

    def test_ref_and_waiver_together_rejected(self):
        plan_path, manifest_path, plan, manifest = self.artifacts()
        callback = self.transition_callback(transitionPreviewRef=str(manifest_path),
                                            transitionPreviewWaiver={"status": "blocked_previews", "disclosure": "d"})
        with self.assertRaises(ValueError) as caught:
            self.check(callback, plan_path, plan, manifest_path, manifest)
        self.assertIn("二选一", str(caught.exception))

    def test_no_transition_plan_rejects_stray_preview(self):
        plan_payload = self.transition_plan_payload(with_transition=False)
        plan_path, manifest_path, _, manifest = self.artifacts(plan_payload)
        callback = self.callback_plain()
        callback["transitionPreviewRef"] = str(manifest_path)
        with self.assertRaises(ValueError) as caught:
            self.check(callback, plan_path, plan_payload, manifest_path, manifest)
        self.assertIn("不得挂预览", str(caught.exception))

    def callback_plain(self):
        callback = self.transition_callback()
        for row in callback["rows"]:
            row["transitionInstruction"] = "硬切"
            row.pop("transitionDurationMs", None)
        return callback


if __name__ == "__main__":
    unittest.main()
