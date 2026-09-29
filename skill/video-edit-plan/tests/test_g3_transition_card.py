import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


callback_validator = load_script("validate_g3_callback")
plan_validator = load_script("validate_g3_plan")
renderer = load_script("render_g3_review_card")


def plan_segment(**override):
    segment = {"segmentId": "seg-001", "assetId": "a1", "startMs": 0, "endMs": 4000,
               "outputStartMs": 0, "outputEndMs": 4000, "outputDurationMs": 4000, "mappingMode": "one_to_one",
               "reason": "开场", "evidenceRefs": ["e1"],
               "visualVerification": {"status": "verified", "frameManifestRef": "m.json",
                                      "frameRefs": ["f1", "f2", "f3"], "observedVisuals": "机体入画"},
               "narrationStartMs": 100, "narrationEndMs": 3500, "narrationText": "开场白",
               "narrativeClaim": {"type": "object", "minimumVisibleEvidence": "机体"},
               "semanticAlignment": {"status": "direct_match", "evidence": "机体入画"},
               "semanticBeatIds": ["B01"]}
    segment.update(override)
    return segment


class PlanSegmentTransitionTests(unittest.TestCase):
    def check_errors(self, segment):
        plan_validator.ERRORS.clear()
        beat_index = {"B01": {"outputStartMs": 0, "outputEndMs": 4000}}
        plan_validator.validate_segment(segment, set(), {"a1": 10000}, beat_index, {"a1": "sha-a1"}, "review_required")
        return list(plan_validator.ERRORS)

    def test_absent_or_default_hard_cut_is_clean(self):
        self.assertEqual(self.check_errors(plan_segment()), [])
        self.assertEqual(self.check_errors(plan_segment(transitionInstruction="硬切")), [])

    def test_vague_compound_value_rejected(self):
        errors = self.check_errors(plan_segment(transitionInstruction="叠化/硬切按 G4 微调", transitionDurationMs=500))
        self.assertTrue(any("transitionInstruction" in error for error in errors))

    def test_reserved_wipe_rejected(self):
        errors = self.check_errors(plan_segment(transitionInstruction="抹开", transitionDurationMs=500))
        self.assertTrue(any("预留" in error for error in errors))

    def test_dissolve_requires_duration_in_range(self):
        self.assertEqual(self.check_errors(plan_segment(transitionInstruction="叠化", transitionDurationMs=500,
                                                        transitionReason="战果句退场、情绪渐隐")), [])
        self.assertTrue(any("transitionDurationMs" in error for error in self.check_errors(
            plan_segment(transitionInstruction="叠化", transitionReason="渐隐"))))
        self.assertTrue(any("transitionDurationMs" in error for error in self.check_errors(
            plan_segment(transitionInstruction="叠化", transitionDurationMs=50, transitionReason="渐隐"))))

    def test_hard_cut_rejects_stray_duration(self):
        errors = self.check_errors(plan_segment(transitionInstruction="硬切", transitionDurationMs=500))
        self.assertTrue(any("must not carry" in error for error in errors))

    # ---- ⑪ 每一步有所依据（zaku-intro-003 实测，用户 09-29 定案）：非硬切必须登记理由 ----
    def test_transition_without_reason_rejected(self):
        errors = self.check_errors(plan_segment(transitionInstruction="叠化", transitionDurationMs=500))
        self.assertTrue(any("transitionReason" in error for error in errors))
        errors = self.check_errors(plan_segment(transitionInstruction="黑场入", transitionDurationMs=500))
        self.assertTrue(any("transitionReason" in error for error in errors))
        errors = self.check_errors(plan_segment(transitionInstruction="黑场出", transitionDurationMs=500))
        self.assertTrue(any("transitionReason" in error for error in errors))

    def test_blank_reason_rejected(self):
        errors = self.check_errors(plan_segment(transitionInstruction="叠化", transitionDurationMs=500,
                                                 transitionReason="   "))
        self.assertTrue(any("transitionReason" in error for error in errors))

    def test_hard_cut_without_reason_stays_clean(self):
        # 默认档不强制理由（避免套话稀释）
        self.assertEqual(self.check_errors(plan_segment(transitionInstruction="硬切")), [])

    def test_reason_present_passes_black_modes(self):
        self.assertEqual(self.check_errors(plan_segment(transitionInstruction="黑场入", transitionDurationMs=500,
                                                        transitionReason="片头静默 800ms，渐亮进入钩子")), [])


def callback_row(**override):
    row = {"segmentId": "seg-001", "outputStartMs": 0, "outputEndMs": 4000,
           "narrationText": "开场白", "sourceStartMs": 0, "sourceEndMs": 4000,
           "outputTimecode": callback_validator.format_review_range(0, 4000),
           "sourceTimecode": callback_validator.format_review_range(0, 4000),
           "observedVisuals": "机体入画", "semanticStatus": "direct_match",
           "subjectStatus": "主体已确认", "riskSummary": "无风险项", "bgmPhrase": "无BGM",
           "transitionInstruction": "硬切"}
    row.update(override)
    return row


class CallbackTransitionTests(unittest.TestCase):
    def final(self, rows):
        return {"schemaVersion": "0.1", "node": "G3", "projectId": "p", "callbackType": "final_review",
                "durationMs": 4000, "columns": callback_validator.FINAL_HEADERS, "rows": rows}

    def plan(self, segments):
        return {"projectId": "p", "segments": segments}

    def validate(self, rows, segments):
        callback_validator.validate_final(self.final(rows), self.plan(segments), None)

    def test_default_hard_cut_roundtrip_passes(self):
        self.validate([callback_row()], [plan_segment()])

    def test_card_hard_cut_vs_plan_dissolve_rejected(self):
        with self.assertRaises(ValueError) as caught:
            self.validate([callback_row()], [plan_segment(transitionInstruction="叠化", transitionDurationMs=500)])
        self.assertIn("must equal the plan", str(caught.exception))

    def test_vague_card_value_rejected_before_mismatch(self):
        with self.assertRaises(ValueError) as caught:
            self.validate([callback_row(transitionInstruction="叠化/硬切按 G4 微调")],
                          [plan_segment(transitionInstruction="叠化", transitionDurationMs=500)])
        self.assertIn("must be one of", str(caught.exception))

    def test_duration_mismatch_between_card_and_plan_rejected(self):
        with self.assertRaises(ValueError) as caught:
            self.validate([callback_row(transitionInstruction="叠化", transitionDurationMs=300)],
                          [plan_segment(transitionInstruction="叠化", transitionDurationMs=500)])
        self.assertIn("transitionDurationMs", str(caught.exception))

    def test_matching_dissolve_card_passes(self):
        self.validate([callback_row(transitionInstruction="叠化", transitionDurationMs=500)],
                      [plan_segment(transitionInstruction="叠化", transitionDurationMs=500)])


class RendererCellTests(unittest.TestCase):
    def test_cell_appends_human_readable_duration(self):
        self.assertEqual(renderer.transition_cell({"transitionInstruction": "硬切"}), "硬切")
        self.assertEqual(renderer.transition_cell({"transitionInstruction": "叠化", "transitionDurationMs": 500}),
                         "叠化 · 00:00.500")


def three_segment_plan():
    return {"segments": [
        plan_segment(),
        plan_segment(segmentId="seg-002", assetId="a2", startMs=4000, endMs=8000,
                     outputStartMs=4000, outputEndMs=8000, reason="战果句收束",
                     transitionInstruction="叠化", transitionDurationMs=500,
                     transitionReason="情绪渐隐，跨入新战场语境"),
        plan_segment(segmentId="seg-003", assetId="a3", startMs=8000, endMs=12000,
                     outputStartMs=8000, outputEndMs=12000, reason="新战场开场"),
    ]}


class RendererBasisTests(unittest.TestCase):
    """⑪ 转场依据区与第 5 列用途：逐字搬运计划字段、旧计划缺字段不编造。"""

    def test_basis_lines_verbatim_from_plan(self):
        text = "\n".join(renderer.transition_basis_lines(three_segment_plan()))
        self.assertIn("转场依据区", text)
        self.assertIn("seg-002→seg-003", text)
        self.assertIn("情绪渐隐，跨入新战场语境", text)

    def test_hard_cut_only_plan_has_no_basis_block(self):
        self.assertEqual(renderer.transition_basis_lines({"segments": [plan_segment()]}), [])

    def test_old_plan_missing_reason_disclosed_not_fabricated(self):
        plan = three_segment_plan()
        plan["segments"][1].pop("transitionReason")
        text = "\n".join(renderer.transition_basis_lines(plan))
        self.assertIn("未登记", text)

    def test_card_cell5_carries_purpose_and_basis_section_renders(self):
        rows = [
            callback_row(),
            callback_row(segmentId="seg-002", outputStartMs=4000, outputEndMs=8000,
                         outputTimecode=callback_validator.format_review_range(4000, 8000),
                         sourceStartMs=4000, sourceEndMs=8000,
                         sourceTimecode=callback_validator.format_review_range(4000, 8000),
                         transitionInstruction="叠化", transitionDurationMs=500),
            callback_row(segmentId="seg-003", outputStartMs=8000, outputEndMs=12000,
                         outputTimecode=callback_validator.format_review_range(8000, 12000),
                         sourceStartMs=8000, sourceEndMs=12000,
                         sourceTimecode=callback_validator.format_review_range(8000, 12000)),
        ]
        callback = {"schemaVersion": "0.1", "node": "G3", "projectId": "p",
                    "callbackType": "final_review", "durationMs": 12000,
                    "columns": callback_validator.FINAL_HEADERS, "rows": rows}
        card = renderer.render(callback, None, None, None, plan=three_segment_plan())
        self.assertIn("用途：开场｜画面观察：机体入画", card)
        self.assertIn("## 转场依据区", card)
        self.assertIn("情绪渐隐，跨入新战场语境", card)


if __name__ == "__main__":
    unittest.main()
