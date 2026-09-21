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
        self.assertEqual(self.check_errors(plan_segment(transitionInstruction="叠化", transitionDurationMs=500)), [])
        self.assertTrue(any("transitionDurationMs" in error for error in self.check_errors(plan_segment(transitionInstruction="叠化"))))
        self.assertTrue(any("transitionDurationMs" in error for error in self.check_errors(plan_segment(transitionInstruction="叠化", transitionDurationMs=50))))

    def test_hard_cut_rejects_stray_duration(self):
        errors = self.check_errors(plan_segment(transitionInstruction="硬切", transitionDurationMs=500))
        self.assertTrue(any("must not carry" in error for error in errors))


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


if __name__ == "__main__":
    unittest.main()
