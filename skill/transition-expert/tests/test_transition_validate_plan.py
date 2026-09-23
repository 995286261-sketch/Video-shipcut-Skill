import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "transition_validate_plan.py"


def load_validator():
    spec = importlib.util.spec_from_file_location("transition_validate_plan", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = load_validator()

HOST_PROFILE = {"skill": "transition-expert", "purpose": "transition_host_profile",
                "xfade": {"available": True, "transitions": ["dissolve", "fade", "fadeblack", "wipeleft"]},
                "capabilities": {"fade": True, "dissolve": True, "wipe": True, "fadeBlackBoundary": True}}


def base_plan() -> dict:
    return {
        "projectId": "p", "timelineDurationMs": 13000,
        "segments": [
            {"segmentId": "seg-001", "assetId": "a1", "startMs": 1000, "endMs": 5000,
             "outputStartMs": 0, "outputEndMs": 4000, "narrationStartMs": 200, "narrationEndMs": 3500,
             "transitionInstruction": "叠化", "transitionDurationMs": 500},
            {"segmentId": "seg-002", "assetId": "a2", "startMs": 500, "endMs": 5500,
             "outputStartMs": 4000, "outputEndMs": 9000, "narrationStartMs": 4300, "narrationEndMs": 8500,
             "transitionInstruction": "叠化", "transitionDurationMs": 500},
            {"segmentId": "seg-003", "assetId": "a3", "startMs": 2000, "endMs": 6000,
             "outputStartMs": 9000, "outputEndMs": 13000, "narrationStartMs": 9300, "narrationEndMs": 12000,
             "transitionInstruction": "黑场出", "transitionDurationMs": 800},
        ],
    }


def base_evidence() -> dict:
    return {"sourceEvidence": [
        {"assetId": "a1", "sha256": "A1", "sourceProbe": {"durationMs": 10000}},
        {"assetId": "a2", "sha256": "A2", "sourceProbe": {"durationMs": 8000}},
        {"assetId": "a3", "sha256": "A3", "sourceProbe": {"durationMs": 6000}},
    ]}


class TransitionValidatePlanTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def call(self, plan, evidence=None, host_profile=HOST_PROFILE):
        def dump(name, value):
            path = self.root / name
            if value is None:
                return None
            path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            return path
        argv = ["--plan", str(dump("plan.json", plan)), "--evidence", str(dump("evidence.json", evidence or base_evidence()))]
        profile_path = dump("host.json", host_profile)
        if profile_path:
            argv += ["--host-profile", str(profile_path)]
        stdout = io.StringIO()
        backup = sys.argv
        sys.argv = ["transition_validate_plan.py"] + argv
        try:
            with contextlib.redirect_stdout(stdout):
                try:
                    code = validator.main()
                except SystemExit as exit_signal:
                    code = exit_signal.code
        finally:
            sys.argv = backup
        return code, json.loads(stdout.getvalue())

    def assert_passed(self, plan, evidence=None):
        code, report = self.call(plan, evidence)
        self.assertEqual(code, 0, report)
        return report

    def assert_failed(self, plan, needle, evidence=None, host_profile=HOST_PROFILE):
        code, report = self.call(plan, evidence, host_profile)
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "invalid")
        joined = " | ".join(report.get("errors", [report.get("error", "")]))
        self.assertIn(needle, joined)

    def test_clean_plan_passes_and_reports_grid_invariant(self):
        report = self.assert_passed(base_plan())
        self.assertTrue(report["gridInvariant"])
        self.assertEqual(len(report["transitions"]), 3)
        first = report["transitions"][0]
        self.assertEqual(first["windowMs"], [3750, 4250])
        self.assertEqual(first["handlesMs"]["after"], 5000)

    def test_default_is_hard_cut_without_host_profile(self):
        plan = base_plan()
        for segment in plan["segments"]:
            segment.pop("transitionInstruction")
            segment.pop("transitionDurationMs")
        code, report = self.call(plan, host_profile=None)
        self.assertEqual(code, 0, report)
        self.assertEqual(report["transitions"], [])

    def test_vague_compound_instruction_rejected(self):
        plan = base_plan()
        plan["segments"][0]["transitionInstruction"] = "叠化/硬切按 G4 微调"
        self.assert_failed(plan, "不在词表")

    def test_reserved_wipe_tier_rejected(self):
        plan = base_plan()
        plan["segments"][0]["transitionInstruction"] = "抹开"
        self.assert_failed(plan, "预留档")

    def test_dissolve_on_last_segment_rejected(self):
        plan = base_plan()
        plan["segments"][2].pop("transitionDurationMs")
        plan["segments"][2]["transitionInstruction"] = "叠化"
        plan["segments"][2]["transitionDurationMs"] = 500
        self.assert_failed(plan, "末段")

    def test_fade_positions_enforced(self):
        plan = base_plan()
        plan["segments"][0].pop("transitionDurationMs")
        plan["segments"][0]["transitionInstruction"] = "黑场出"
        plan["segments"][0]["transitionDurationMs"] = 500
        self.assert_failed(plan, "末段")
        plan = base_plan()
        plan["segments"][1]["transitionInstruction"] = "黑场入"
        self.assert_failed(plan, "首段")

    def test_hard_cut_must_not_carry_duration(self):
        plan = base_plan()
        plan["segments"][0]["transitionInstruction"] = "硬切"
        self.assert_failed(plan, "must not carry transitionDurationMs")

    def test_duration_out_of_range_rejected(self):
        plan = base_plan()
        plan["segments"][0]["transitionDurationMs"] = 50
        self.assert_failed(plan, "transitionDurationMs")

    def test_window_over_narration_rejected(self):
        plan = base_plan()
        plan["segments"][1]["narrationStartMs"] = 4000  # 压住窗口 [3750,4250)
        self.assert_failed(plan, "口播停顿")

    def test_touching_narration_boundary_allowed(self):
        plan = base_plan()
        plan["segments"][1]["narrationStartMs"] = 4250  # 恰好相接不算重叠
        self.assert_passed(plan)

    def test_handle_shortfall_surfaces_with_feasible_max(self):
        # a2 源总长缩到 5600：seg-002 after = 5600-5500 = 100ms < 250ms → 摊牌，最大可行 D=2×100
        evidence = base_evidence()
        for entry in evidence["sourceEvidence"]:
            if entry["assetId"] == "a2":
                entry["sourceProbe"]["durationMs"] = 5600
        code, report = self.call(base_plan(), evidence)
        self.assertEqual(code, 2)
        joined = " | ".join(report["errors"])
        self.assertIn("缺料摊牌", joined)
        self.assertIn("最大可行 D=200ms", joined)

    def test_chapter_card_overlap_rejected(self):
        plan = base_plan()
        plan["packagingDecisions"] = {"chapterCards": [{"startMs": 3600, "endMs": 4400, "title": "第二章"}]}
        self.assert_failed(plan, "章节卡")

    def test_grid_break_rejected(self):
        plan = base_plan()
        plan["segments"][1]["outputStartMs"] = 3900
        self.assert_failed(plan, "网格")

    def test_dissolve_without_host_profile_refused(self):
        code, report = self.call(base_plan(), host_profile=None)
        self.assertEqual(code, 2)
        self.assertIn("先跑 transition_probe_host", " | ".join(report["errors"]))

    def test_dissolve_blocked_when_host_lacks_xfade(self):
        weak = {"skill": "transition-expert", "purpose": "transition_host_profile",
                "xfade": {"available": False, "transitions": []}, "capabilities": {"fade": False, "dissolve": False}}
        self.assert_failed(base_plan(), "blocked", host_profile=weak)

    def test_foreign_profile_identity_rejected(self):
        code, report = self.call(base_plan(), host_profile={"skill": "somebody-else", "purpose": "x"})
        self.assertEqual(code, 2)
        self.assertIn("transition_host_profile", " | ".join(report["errors"]))

    def test_same_source_claim_shrinks_handle(self):
        # a1 尾部 6200-6600 另被 seg-00x 占用：seg-001 after 从 5000 缩到 1200，仍 ≥250 → 过
        plan = base_plan()
        plan["segments"][2].pop("transitionInstruction")
        plan["segments"][2].pop("transitionDurationMs")
        plan["segments"].append({"segmentId": "seg-00x", "assetId": "a1", "startMs": 6200, "endMs": 6600,
                                 "outputStartMs": 13000, "outputEndMs": 13400,
                                 "transitionInstruction": "黑场出", "transitionDurationMs": 300})
        plan["timelineDurationMs"] = 13400
        self.assert_passed(plan)
        # 占用推到 5100：seg-001 after 只剩 100ms → 该边界摊牌
        plan["segments"][-1]["startMs"] = 5100
        self.assert_failed(plan, "缺料摊牌")

    def test_master_boundary_fade_needs_no_handles(self):
        plan = base_plan()
        for segment in plan["segments"]:
            segment.pop("transitionInstruction")
            segment.pop("transitionDurationMs")
        plan["segments"][0]["transitionInstruction"] = "黑场入"
        plan["segments"][0]["transitionDurationMs"] = 600
        plan["segments"][0]["narrationStartMs"] = 700  # 窗口 [0,600) 需避开
        report = self.assert_passed(plan)
        self.assertEqual(report["transitions"][0]["windowMs"], [0, 600])


if __name__ == "__main__":
    unittest.main()
