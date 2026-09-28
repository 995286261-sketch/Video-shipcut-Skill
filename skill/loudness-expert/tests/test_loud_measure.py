"""loud_measure 端到端回归（lavfi 合成音，需 ffmpeg；缺席即 skip 不算绿）。"""
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
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import loud_measure  # noqa: E402
import loud_plan    # noqa: E402

HAS_FFMPEG = shutil.which("ffmpeg") is not None


def make_sine(directory: Path, name: str, volume: float) -> Path:
    out = directory / name
    result = subprocess.run(["ffmpeg", "-hide_banner", "-nostats",
                             "-f", "lavfi",
                             "-i", "sine=frequency=1000:sample_rate=48000:duration=2",
                             "-af", "volume={0}".format(volume), "-y", str(out)],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    return out


def run_cli(argv, entry=None):
    buf = io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(buf):
            (entry or loud_measure.main)(argv)
    except SystemExit as exc:
        code = exc.code or 0
    return code, json.loads(buf.getvalue())


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg 缺席——本层端到端用例不适用（skip 非通过）")
class MeasureTests(unittest.TestCase):
    def test_reports_measured_numbers_and_versioning(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path, work = Path(tmp), Path(tmp) / "work"
            src = make_sine(tmp_path, "a.wav", 0.5)
            code, doc = run_cli(["--input", str(src), "--output-dir", str(work)])
            self.assertEqual(code, 0)
            self.assertEqual(doc["status"], "measured")
            self.assertEqual(doc["skill"], "loudness-expert")
            self.assertIsNotNone(doc["measured"]["integratedLufs"])
            self.assertEqual(len(doc["sha256"]), 64)
            artifact = Path(doc["output"])
            self.assertTrue(artifact.is_file())
            self.assertEqual(artifact.name, "响度-实测报告-v0.1.json")
            # 再跑一次：版本自增，旧文件字节不变
            old_bytes = artifact.read_bytes()
            code2, doc2 = run_cli(["--input", str(src), "--output-dir", str(work)])
            self.assertEqual(code2, 0)
            self.assertEqual(Path(doc2["output"]).name, "响度-实测报告-v0.2.json")
            self.assertEqual(artifact.read_bytes(), old_bytes)

    def test_linear_scaling_shifts_integrated_loudness(self):
        """物理自证：同频正弦线性缩小 20 dB，集成响度应随动（±1.5 LU）。"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path, work = Path(tmp), Path(tmp) / "work"
            _, loud = run_cli(["--input", str(make_sine(tmp_path, "l.wav", 0.5)),
                               "--output-dir", str(work)])
            _, quiet = run_cli(["--input", str(make_sine(tmp_path, "q.wav", 0.05)),
                                "--output-dir", str(work)])
            shift = loud["measured"]["integratedLufs"] - quiet["measured"]["integratedLufs"]
            self.assertAlmostEqual(shift, 20.0, delta=1.5)

    def test_ladder_linearity_three_step(self):
        """物理锁：振幅每减半，集成响度必须精确降 6.02 LU（±0.4，功率减半=3.01 是另一回事）。
        教训（2026-09-24 自证轮）：本机 lavfi sine 源默认峰值在 −18 dBFS 附近——
        绝对值不许想当然，线性关系与引擎互证（ebur128/loudnorm/volumedetect 三表
        同读数）才是测量可信的判据。"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path, work = Path(tmp), Path(tmp) / "work"
            levels = []
            for v in ("0.8", "0.4", "0.2"):
                src = make_sine(tmp_path, "v{0}.wav".format(v), float(v))
                _, doc = run_cli(["--input", str(src), "--output-dir", str(work)])
                levels.append(doc["measured"]["integratedLufs"])
            self.assertAlmostEqual(levels[0] - levels[1], 6.02, delta=0.4)
            self.assertAlmostEqual(levels[1] - levels[2], 6.02, delta=0.4)

    def test_engine_agreement_loudnorm_vs_ebur128(self):
        """同一文件 loudnorm pass1 规划口径与 ebur128 验收口径必须同读数（±0.5 LU）
        ——专员双口径互不背书但互相对账，谁漂了当场现形。"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = make_sine(tmp_path, "agree.wav", 0.4)
            _, measured = run_cli(["--input", str(src), "--output-dir", str(tmp_path / "w1")])
            _, planned = run_cli(["--input", str(src), "--output-dir", str(tmp_path / "w2"),
                                  "--profile", "video"], entry=loud_plan.main)
            self.assertAlmostEqual(measured["measured"]["integratedLufs"],
                                   planned["measured"]["inputI"], delta=0.5)

    def test_missing_input_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, doc = run_cli(["--input", str(Path(tmp) / "nope.wav"),
                                 "--output-dir", tmp])
            self.assertEqual(code, 1)
            self.assertEqual(doc["status"], "error")

    def test_capability_missing_structured(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "x.wav"
            src.write_bytes(b"not-a-real-audio")
            with mock.patch.object(loud_measure.loud_core, "ffmpeg_available", lambda: False):
                code, doc = run_cli(["--input", str(src), "--output-dir", tmp])
            self.assertEqual(code, 2)
            self.assertEqual(doc["status"], "capability_missing")
            self.assertIn("hint", doc["capability"])


if __name__ == "__main__":
    unittest.main()
