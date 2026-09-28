"""loud_echo 回显卡回归（纯呈现层：数据全取产物，零算术）。"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import loud_echo  # noqa: E402


def run_cli(argv):
    buf = io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(buf):
            loud_echo.main(argv)
    except SystemExit as exc:
        code = exc.code or 0
    return code, buf.getvalue()


PLAN_DOC = {"skill": "loudness-expert", "purpose": "loud_plan", "status": "ready",
            "version": "v0.1", "source": "/tmp/x/quiet.wav",
            "sha256": "ABCDEF0123456789" + "0" * 48,
            "measured": {"inputI": -29.3, "inputTp": -26.1, "inputLra": 3.2,
                         "inputThresh": -39.0},
            "targetProfile": {"integratedLufs": -14.0, "truePeakDbtp": -1.5,
                              "lraTargetLu": 9.0},
            "gainDb": 15.3, "estimatedTruePeak": -10.8, "ceilingLufs": -12.3,
            "blockedReasons": [], "exits": []}


class EchoTests(unittest.TestCase):
    def test_plan_card_renders_with_provenance_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "plan.json"
            artifact.write_text(json.dumps(PLAN_DOC, ensure_ascii=False), encoding="utf-8")
            code, card = run_cli(["--artifact", str(artifact)])
            self.assertEqual(code, 0)
            self.assertIn("响度规划卡", card)
            self.assertIn("可执行", card)
            self.assertIn("-29.3", card)          # 数据逐字来自产物
            self.assertIn("此卡由通过校验的响度专员产物生成", card)

    def test_foreign_artifact_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "other.json"
            artifact.write_text(json.dumps({"skill": "subtitle-expert"}), encoding="utf-8")
            code, _ = run_cli(["--artifact", str(artifact)])
            self.assertEqual(code, 1)

    def test_verify_card_shows_checks(self):
        doc = {"skill": "loudness-expert", "purpose": "loud_verify", "status": "failed",
               "version": "v0.1", "source": "/tmp/m.wav", "masterSha256": "F" * 64,
               "masterMeasured": {"integratedLufs": -17.2, "truePeakDbtp": -3.0,
                                  "loudnessRangeLu": 8.1},
               "checks": [{"check": "integratedWithinTolerance", "pass": False,
                           "detail": "实测 -17.2 vs 目标 -14.0，偏差 -3.2 LU（容差 ±1.0 LU）"}]}
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "audit.json"
            artifact.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
            code, card = run_cli(["--artifact", str(artifact)])
            self.assertEqual(code, 0)
            self.assertIn("验收不过", card)
            self.assertIn("偏差 -3.2", card)


if __name__ == "__main__":
    unittest.main()
