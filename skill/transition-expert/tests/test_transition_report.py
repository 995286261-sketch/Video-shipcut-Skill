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


report_script = load_script("transition_report")
directive_script = load_script("transition_directive")


def golden_directive() -> dict:
    plan = {"projectId": "p", "timelineDurationMs": 13000, "segments": [
        {"segmentId": "seg-001", "outputStartMs": 0, "outputEndMs": 4000, "transitionInstruction": "叠化", "transitionDurationMs": 500},
        {"segmentId": "seg-002", "outputStartMs": 4000, "outputEndMs": 9000, "transitionInstruction": "叠化", "transitionDurationMs": 500},
        {"segmentId": "seg-003", "outputStartMs": 9000, "outputEndMs": 13000, "transitionInstruction": "黑场出", "transitionDurationMs": 800},
    ]}
    return directive_script.build_directive(plan, {"sourceEvidence": []}, None)


GOLDEN_GRAPH = ("[0:v]fps=fps=24,format=yuv420p,setsar=1[segv0];[segv0][segv1]xfade=transition=dissolve:duration=0.500:offset=3.750[vcat0];"
                "[vcat0][segv2]xfade=transition=dissolve:duration=0.500:offset=8.750[vcat1];[vcat1],format=yuv420p,"
                "fade=t=out:st=12.200:d=0.800[v]")


class TransitionReportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write(self, name, payload):
        path = self.root / name
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def call(self, directive, graph=None, manifest=None, timeline_ms=13000):
        directive_path = self.write("directive.json", directive)
        manifest = manifest if manifest is not None else {
            "transitionDirective": {"path": str(directive_path),
                                    "sha256": hashlib.sha256(directive_path.read_bytes()).hexdigest().upper()}}
        record = {"filterGraph": graph, "timelineDurationMs": timeline_ms, "output": "master.mp4", "outputSha256": "ABCD"}
        out_dir = self.root / "audit"
        stdout = io.StringIO()
        backup = sys.argv
        sys.argv = ["transition_report.py", "--manifest", str(self.write("manifest.json", manifest)),
                    "--assembly-record", str(self.write("record.json", record)),
                    "--directive", str(directive_path), "--output-dir", str(out_dir)]
        try:
            with contextlib.redirect_stdout(stdout):
                try:
                    code = report_script.main()
                except SystemExit as exit_signal:
                    code = exit_signal.code
        finally:
            sys.argv = backup
        return code, json.loads(stdout.getvalue()), out_dir / "transition-audit.json"

    def test_executed_graph_matches_directive(self):
        code, payload, report_path = self.call(golden_directive(), GOLDEN_GRAPH)
        self.assertEqual(0, code, payload)
        self.assertEqual("passed", payload["status"])
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual("transition-expert", report["skill"])
        self.assertEqual("transition_check", report["purpose"])
        self.assertEqual(2, len(report["transitions"]))
        self.assertTrue(report["gridInvariant"])
        self.assertEqual("ABCD", report["master"]["sha256"])

    def test_offset_drift_fails_execution_equals_approval(self):
        drifted = GOLDEN_GRAPH.replace("offset=8.750", "offset=9.250")
        code, payload, report_path = self.call(golden_directive(), drifted)
        self.assertEqual(1, code)
        self.assertEqual("failed", payload["status"])
        joined = " | ".join(payload["errors"])
        self.assertIn("与指令不符", joined)
        self.assertEqual("failed", json.loads(report_path.read_text(encoding="utf-8"))["status"])

    def test_extra_xfade_is_unapproved(self):
        extra = GOLDEN_GRAPH.replace("[vcat1],format", "[vcat1][segv2]xfade=transition=dissolve:duration=0.500:offset=10.000[vcat2];[vcat2],format")
        code, payload, _ = self.call(golden_directive(), extra)
        self.assertEqual(1, code)
        self.assertIn("次数", " | ".join(payload["errors"]))

    def test_missing_approved_fade_out_is_silent_loss(self):
        code, payload, _ = self.call(golden_directive(), GOLDEN_GRAPH.replace("fade=t=out:st=12.200:d=0.800", "null"))
        self.assertEqual(1, code)
        self.assertIn("黑场出", " | ".join(payload["errors"]))

    def test_fade_out_timecode_shift_surfaces_grid_translation(self):
        code, payload, _ = self.call(golden_directive(), GOLDEN_GRAPH.replace("st=12.200", "st=12.700"))
        self.assertEqual(1, code)
        self.assertIn("网格平移", " | ".join(payload["errors"]))

    def test_stale_manifest_registration_flagged(self):
        directive = golden_directive()
        stale_manifest = {"transitionDirective": {"path": "nowhere.json", "sha256": "0" * 64}}
        code, payload, _ = self.call(directive, GOLDEN_GRAPH, manifest=stale_manifest)
        self.assertEqual(1, code)
        self.assertIn("stale", " | ".join(payload["errors"]))

    def test_foreign_directive_is_fatal(self):
        alien = golden_directive()
        alien["skill"] = "somebody-else"
        code, payload, _ = self.call(alien, GOLDEN_GRAPH)
        self.assertEqual(2, code)
        self.assertEqual("invalid", payload["status"])

    def test_clean_hard_cut_project_passes_with_empty_transitions(self):
        plan = {"projectId": "p", "timelineDurationMs": 3000, "segments": [
            {"segmentId": "seg-001", "outputStartMs": 0, "outputEndMs": 1500},
            {"segmentId": "seg-002", "outputStartMs": 1500, "outputEndMs": 3000},
        ]}
        directive = directive_script.build_directive(plan, {"sourceEvidence": []}, None)
        code, payload, report_path = self.call(directive, "[0:v]fps=fps=24,format=yuv420p[v]")
        self.assertEqual(0, code, payload)
        self.assertEqual([], json.loads(report_path.read_text(encoding="utf-8"))["transitions"])


if __name__ == "__main__":
    unittest.main()
