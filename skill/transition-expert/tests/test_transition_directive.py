import contextlib
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


directive_script = load_script("transition_directive")


HOST_PROFILE = {"skill": "transition-expert", "purpose": "transition_host_profile",
                "xfade": {"available": True, "transitions": ["dissolve", "fade", "fadeblack"]},
                "capabilities": {"fade": True, "dissolve": True, "wipe": False, "fadeBlackBoundary": True}}


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


class DirectiveBuildTests(unittest.TestCase):
    def test_handle_extras_split_half_per_boundary(self):
        directive = directive_script.build_directive(base_plan(), base_evidence(), HOST_PROFILE)
        extras = {item["segmentId"]: (item["headExtraMs"], item["tailExtraMs"]) for item in directive["segments"]}
        self.assertEqual((0, 250), extras["seg-001"])
        self.assertEqual((250, 250), extras["seg-002"])
        self.assertEqual((250, 0), extras["seg-003"])

    def test_boundaries_golden_offsets_grid_invariant(self):
        directive = directive_script.build_directive(base_plan(), base_evidence(), HOST_PROFILE)
        self.assertEqual([
            {"fromSegmentId": "seg-001", "toSegmentId": "seg-002", "transition": "fade", "durationMs": 500, "offsetMs": 3750},
            {"fromSegmentId": "seg-002", "toSegmentId": "seg-003", "transition": "fade", "durationMs": 500, "offsetMs": 8750},
        ], directive["boundaries"])
        # 网格不变是宪法：Σ文件长 − Σ重叠 == 批准网格 13000，指令必须自己先把账平掉。
        self.assertEqual(13000, directive["timelineDurationMs"])
        self.assertTrue(directive["gridInvariant"])
        self.assertEqual({"fadeInMs": 0, "fadeOutMs": 800}, directive["masterFades"])

    def test_no_transition_plan_yields_empty_directive(self):
        plan = base_plan()
        for segment in plan["segments"]:
            segment.pop("transitionInstruction")
            segment.pop("transitionDurationMs")
        directive = directive_script.build_directive(plan, base_evidence(), None)
        self.assertEqual([], directive["boundaries"])
        self.assertEqual({"fadeInMs": 0, "fadeOutMs": 0}, directive["masterFades"])
        self.assertEqual(13000, directive["timelineDurationMs"])


class DirectiveCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.out = self.root / "out"

    def write(self, name, payload):
        path = self.root / name
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def call(self, plan, evidence, host_profile):
        argv = ["--plan", str(self.write("plan.json", plan)), "--evidence", str(self.write("evidence.json", evidence)),
                "--output-dir", str(self.out)]
        if host_profile is not None:
            argv += ["--host-profile", str(self.write("host.json", host_profile))]
        stdout = io.StringIO()
        backup = sys.argv
        sys.argv = ["transition_directive.py"] + argv
        try:
            with contextlib.redirect_stdout(stdout):
                try:
                    code = directive_script.main()
                except SystemExit as exit_signal:
                    code = exit_signal.code
        finally:
            sys.argv = backup
        return code, json.loads(stdout.getvalue())

    def test_rerun_increments_version_and_never_overwrites(self):
        # issue ㉘ (sinjuku reopen 重跑现场): 旧指令文件必须原样留盘作审计。
        code, first = self.call(base_plan(), base_evidence(), HOST_PROFILE)
        self.assertEqual(0, code, first)
        first_path = Path(first["directive"])
        self.assertEqual("G4-转场执行指令-v0.1.json", first_path.name)
        first_bytes = first_path.read_bytes()
        code, second = self.call(base_plan(), base_evidence(), HOST_PROFILE)
        self.assertEqual(0, code, second)
        self.assertEqual("G4-转场执行指令-v0.2.json", Path(second["directive"]).name)
        self.assertEqual(first_bytes, first_path.read_bytes())

    def test_completed_binds_three_input_hashes(self):
        code, payload = self.call(base_plan(), base_evidence(), HOST_PROFILE)
        self.assertEqual(0, code, payload)
        self.assertEqual("completed", payload["status"])
        directive_path = Path(payload["directive"])
        self.assertEqual(Path("G4-转场执行指令-v0.1.json").name, directive_path.name)
        directive = json.loads(directive_path.read_text(encoding="utf-8"))
        for key, path in (("planSha256", self.root / "plan.json"), ("evidenceSha256", self.root / "evidence.json"),
                          ("hostProfileSha256", self.root / "host.json")):
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest().upper(), directive[key])

    def test_rerun_is_byte_deterministic(self):
        _, first = self.call(base_plan(), base_evidence(), HOST_PROFILE)
        again = Path(first["directive"])
        before = again.read_bytes()
        out2 = self.root / "out2"
        argv_backup = sys.argv
        sys.argv = ["transition_directive.py", "--plan", str(self.root / "plan.json"), "--evidence", str(self.root / "evidence.json"),
                    "--host-profile", str(self.root / "host.json"), "--output-dir", str(out2)]
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                directive_script.main()
        finally:
            sys.argv = argv_backup
        self.assertEqual(before, (out2 / "G4-转场执行指令-v0.1.json").read_bytes())

    def test_deep_check_failure_blocks_directive(self):
        plan = base_plan()
        plan["segments"][1]["narrationStartMs"] = 4000  # 窗口 [3750,4250) 压口播 → 深检拒
        code, payload = self.call(plan, base_evidence(), HOST_PROFILE)
        self.assertEqual(2, code)
        self.assertEqual("blocked", payload["status"])
        joined = " | ".join(str(item) for item in payload["validation"])
        self.assertIn("口播停顿", joined)
        self.assertFalse(self.out.exists() and any(self.out.iterdir()))

    def test_missing_host_profile_blocks_dissolve(self):
        code, payload = self.call(base_plan(), base_evidence(), None)
        self.assertEqual(2, code)
        self.assertEqual("blocked", payload["status"])


if __name__ == "__main__":
    unittest.main()
