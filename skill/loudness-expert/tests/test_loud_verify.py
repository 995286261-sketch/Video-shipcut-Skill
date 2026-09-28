"""loud_verify 回归：端到端「规划→真跑链→独立复测=通过」+ 拒绝面。"""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import loud_core    # noqa: E402
import loud_plan    # noqa: E402
import loud_verify  # noqa: E402

HAS_FFMPEG = shutil.which("ffmpeg") is not None


def run_cli(module_main, argv):
    buf = io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(buf):
            module_main(argv)
    except SystemExit as exc:
        code = exc.code or 0
    return code, json.loads(buf.getvalue())


def make_sine(directory: Path, name: str, volume: float) -> Path:
    out = directory / name
    result = subprocess.run(["ffmpeg", "-hide_banner", "-nostats",
                             "-f", "lavfi",
                             "-i", "sine=frequency=1000:sample_rate=48000:duration=2",
                             "-af", "volume={0}".format(volume), "-y", str(out)],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    return out


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg 缺席——端到端验收用例不适用（skip 非通过）")
class VerifyE2ETests(unittest.TestCase):
    def test_full_loop_ready_plan_then_normalized_master_passes(self):
        """专员自证闭环：quiet 源→ready 规划→按 chain 真渲染→独立 ebur128 复测必须 passed。"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path, work = Path(tmp), Path(tmp) / "work"
            src = make_sine(tmp_path, "quiet.wav", 0.02)
            _, plan = run_cli(loud_plan.main, ["--input", str(src), "--output-dir", str(work),
                                               "--profile", "video"])
            self.assertEqual(plan["status"], "ready")
            normalized = tmp_path / "normalized.wav"
            self.assertTrue(loud_core.render_with_chain(src, plan["chain"], normalized))
            code, audit = run_cli(loud_verify.main, ["--plan", plan["output"],
                                                     "--master", str(normalized),
                                                     "--output-dir", str(work)])
            self.assertEqual(code, 0)
            self.assertEqual(audit["status"], "passed")
            self.assertEqual(audit["toleranceLu"], loud_core.DEFAULT_TOLERANCE_LU)
            self.assertEqual(audit["toleranceSource"], "合同默认")
            self.assertEqual(Path(audit["output"]).name, "响度-验收审计-v0.1.json")
            self.assertTrue(all(item["pass"] for item in audit["checks"]))

    def test_off_target_master_fails_with_numbers(self):
        """未归一化原件当 master：偏差必须点名并 failed（不许绿灯）。"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path, work = Path(tmp), Path(tmp) / "work"
            src = make_sine(tmp_path, "quiet.wav", 0.02)
            _, plan = run_cli(loud_plan.main, ["--input", str(src), "--output-dir", str(work),
                                               "--profile", "video"])
            code, audit = run_cli(loud_verify.main, ["--plan", plan["output"],
                                                     "--master", str(src),
                                                     "--output-dir", str(work)])
            self.assertEqual(code, 1)
            self.assertEqual(audit["status"], "failed")
            failing = [item for item in audit["checks"] if not item["pass"]]
            self.assertEqual(failing[0]["check"], "integratedWithinTolerance")
            self.assertIn("偏差", failing[0]["detail"])
            self.assertIsNotNone(audit["failNote"])

    def test_explicit_tolerance_override_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path, work = Path(tmp), Path(tmp) / "work"
            src = make_sine(tmp_path, "quiet.wav", 0.02)
            _, plan = run_cli(loud_plan.main, ["--input", str(src), "--output-dir", str(work),
                                               "--profile", "video"])
            normalized = tmp_path / "n.wav"
            loud_core.render_with_chain(src, plan["chain"], normalized)
            _, audit = run_cli(loud_verify.main, ["--plan", plan["output"],
                                                  "--master", str(normalized),
                                                  "--output-dir", str(work),
                                                  "--tolerance-lu", "0.5"])
            self.assertEqual(audit["toleranceLu"], 0.5)
            self.assertEqual(audit["toleranceSource"], "CLI 显式覆盖")


class VerifyRejectionTests(unittest.TestCase):
    def _plan_doc(self, tmp: Path, **overrides) -> Path:
        doc = {"skill": "loudness-expert", "purpose": "loud_plan", "status": "ready",
               "targetProfile": loud_core.PROFILES["video"], "version": "v0.1",
               "measured": {"inputI": -20.0, "inputTp": -10.0, "inputLra": 5.0,
                            "inputThresh": -30.0}}
        doc.update(overrides)
        path = tmp / "plan.json"
        path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        return path

    def test_foreign_skill_plan_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = self._plan_doc(Path(tmp), skill="someone-else")
            code, doc = run_cli(loud_verify.main, ["--plan", str(plan_path),
                                                   "--master", str(plan_path),
                                                   "--output-dir", tmp])
            self.assertEqual(code, 1)
            self.assertIn("身份不符", doc["error"])

    def test_blocked_plan_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = self._plan_doc(Path(tmp), status="blocked_true-peak")
            code, doc = run_cli(loud_verify.main, ["--plan", str(plan_path),
                                                   "--master", str(plan_path),
                                                   "--output-dir", tmp])
            self.assertEqual(code, 1)
            self.assertIn("重规划", doc["error"])

    def test_missing_master_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = self._plan_doc(Path(tmp))
            code, doc = run_cli(loud_verify.main, ["--plan", str(plan_path),
                                                   "--master", str(Path(tmp) / "ghost.wav"),
                                                   "--output-dir", tmp])
            self.assertEqual(code, 1)
            self.assertIn("master", doc["error"])


if __name__ == "__main__":
    unittest.main()
