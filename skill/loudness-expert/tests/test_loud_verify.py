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

    def test_blocked_plan_without_assembly_record_refused(self):
        # 批四丙口径：blocked 验收不再"一概拒"，但没有 G4 记账对账照样拒——让步必须可对账。
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = self._plan_doc(Path(tmp), status="blocked_true-peak")
            code, doc = run_cli(loud_verify.main, ["--plan", str(plan_path),
                                                   "--master", str(plan_path),
                                                   "--output-dir", tmp])
            self.assertEqual(code, 1)
            self.assertIn("--assembly-record", doc["error"])

    def test_bogus_plan_status_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = self._plan_doc(Path(tmp), status="half-baked")
            code, doc = run_cli(loud_verify.main, ["--plan", str(plan_path),
                                                   "--master", str(plan_path),
                                                   "--output-dir", tmp])
            self.assertEqual(code, 1)
            self.assertIn("既非 ready 也非 blocked", doc["error"])

    def _blocked_pair(self, tmp: Path, **assembly_overrides) -> "tuple[Path, Path]":
        """blocked 计划 + 逐项对得上的 G4 装配记录（可整体覆写记账字段演负向）。"""
        plan_path = self._plan_doc(tmp, status="blocked_true-peak")
        loud_block = {"planRef": {"path": str(plan_path), "sha256": loud_core.sha256_file(plan_path)},
                      "mode": "controlled-dynamic",
                      "targetProfile": loud_core.PROFILES["video"]}
        loud_block.update(assembly_overrides)
        assembly = {"node": "G4", "loudness": loud_block}
        assembly_path = tmp / "assembly.json"
        assembly_path.write_text(json.dumps(assembly, ensure_ascii=False), encoding="utf-8")
        return plan_path, assembly_path

    def test_blocked_binding_plan_hash_drift_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path, assembly_path = self._blocked_pair(Path(tmp), planRef={"path": "x", "sha256": "F" * 64})
            code, doc = run_cli(loud_verify.main, ["--plan", str(plan_path), "--master", str(plan_path),
                                                   "--output-dir", tmp, "--assembly-record", str(assembly_path)])
            self.assertEqual(code, 1)
            self.assertIn("绑定对账失败", doc["error"])

    def test_blocked_binding_wrong_mode_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path, assembly_path = self._blocked_pair(Path(tmp), mode="linear-verbatim")
            code, doc = run_cli(loud_verify.main, ["--plan", str(plan_path), "--master", str(plan_path),
                                                   "--output-dir", tmp, "--assembly-record", str(assembly_path)])
            self.assertEqual(code, 1)
            self.assertIn("controlled-dynamic", doc["error"])

    def test_blocked_binding_profile_drift_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path, assembly_path = self._blocked_pair(Path(tmp), targetProfile=loud_core.PROFILES["podcast"])
            code, doc = run_cli(loud_verify.main, ["--plan", str(plan_path), "--master", str(plan_path),
                                                   "--output-dir", tmp, "--assembly-record", str(assembly_path)])
            self.assertEqual(code, 1)
            self.assertIn("targetProfile", doc["error"])

    def test_missing_master_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = self._plan_doc(Path(tmp))
            code, doc = run_cli(loud_verify.main, ["--plan", str(plan_path),
                                                   "--master", str(Path(tmp) / "ghost.wav"),
                                                   "--output-dir", tmp])
            self.assertEqual(code, 1)
            self.assertIn("master", doc["error"])

    # ---- ⑩ 入包副本先验（banshee-001 台账，2026-10-10 用户拍板甲案）：两条合同校验
    # 在测量之前 fail-fast，不需要 ffmpeg。----
    def test_bundle_copy_bad_name_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = self._plan_doc(Path(tmp))
            code, doc = run_cli(loud_verify.main, ["--plan", str(plan_path), "--master", str(plan_path),
                                                   "--output-dir", tmp,
                                                   "--bundle-copy", str(Path(tmp) / "loudness-report.json")])
            self.assertEqual(code, 1)
            self.assertIn("loudness-audit.json", doc["error"])
            self.assertIn("命名", doc["error"])

    def test_bundle_copy_missing_dir_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = self._plan_doc(Path(tmp))
            ghost = Path(tmp) / "no-such-bundle" / "loudness-audit.json"
            code, doc = run_cli(loud_verify.main, ["--plan", str(plan_path), "--master", str(plan_path),
                                                   "--output-dir", tmp, "--bundle-copy", str(ghost)])
            self.assertEqual(code, 1)
            self.assertIn("目录不存在", doc["error"])
            self.assertFalse(ghost.parent.exists())  # 不替你创建目录树


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg 缺席——blocked 档端到端验收用例不适用（skip 非通过）")
class BlockedTierE2ETests(unittest.TestCase):
    """批四丙口径验收面：blocked 计划+合规 G4 记账 → passed/disclosed-exceedance 两态如实；
    TP 超限即使 blocked 也 failed（两档共同硬闸，限幅链路坏≠响度取舍）。"""

    def _pair(self, tmp: Path) -> "tuple[Path, Path]":
        plan_doc = {"skill": "loudness-expert", "purpose": "loud_plan", "status": "blocked_true-peak",
                    "targetProfile": dict(loud_core.PROFILES["video"]), "version": "v0.1",
                    "ceilingLufs": -22.8}
        plan_path = tmp / "plan.json"
        plan_path.write_text(json.dumps(plan_doc, ensure_ascii=False), encoding="utf-8")
        loud_block = {"planRef": {"path": str(plan_path), "sha256": loud_core.sha256_file(plan_path)},
                      "mode": "controlled-dynamic", "targetProfile": dict(loud_core.PROFILES["video"])}
        assembly_path = tmp / "assembly.json"
        assembly_path.write_text(json.dumps({"node": "G4", "loudness": loud_block}, ensure_ascii=False), encoding="utf-8")
        return plan_path, assembly_path

    def test_blocked_plan_master_on_target_passes_with_assembly_trail(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path, work = Path(tmp), Path(tmp) / "work"
            plan_path, assembly_path = self._pair(tmp_path)
            src = make_sine(tmp_path, "src.wav", 0.02)
            master = tmp_path / "master.wav"
            self.assertTrue(loud_core.render_with_chain(src, "loudnorm=I=-14:TP=-1.5:LRA=9", master))
            code, audit = run_cli(loud_verify.main, ["--plan", str(plan_path), "--master", str(master),
                                                     "--output-dir", str(work), "--assembly-record", str(assembly_path)])
            self.assertEqual(code, 0)
            self.assertEqual(audit["status"], "passed")
            self.assertEqual(audit["planStatus"], "blocked_true-peak")
            self.assertEqual(audit["assemblyRef"]["sha256"], loud_core.sha256_file(assembly_path))
            self.assertEqual(audit["targetProfile"], loud_core.PROFILES["video"])

    def test_blocked_plan_master_exceeding_is_disclosed_not_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path, work = Path(tmp), Path(tmp) / "work"
            plan_path, assembly_path = self._pair(tmp_path)
            master = make_sine(tmp_path, "quiet.wav", 0.01)  # 安静正弦：I 远低于 −14，TP 合规
            code, audit = run_cli(loud_verify.main, ["--plan", str(plan_path), "--master", str(master),
                                                     "--output-dir", str(work), "--assembly-record", str(assembly_path)])
            self.assertEqual(code, 1)
            self.assertEqual(audit["status"], "disclosed-exceedance")
            self.assertIsNotNone(audit["disclosureNote"])
            self.assertIsNone(audit["failNote"])

    def test_blocked_plan_master_over_tp_fails_even_in_blocked_tier(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path, work = Path(tmp), Path(tmp) / "work"
            plan_path, assembly_path = self._pair(tmp_path)
            master = make_sine(tmp_path, "loud.wav", 8.0)  # 削顶到满幅（本 lavfi 正弦默认电平低，×8 实测 TP≥−0.3）：超 −1.5+0.3 余量
            code, audit = run_cli(loud_verify.main, ["--plan", str(plan_path), "--master", str(master),
                                                     "--output-dir", str(work), "--assembly-record", str(assembly_path)])
            self.assertEqual(code, 1)
            self.assertEqual(audit["status"], "failed")


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg 缺席——入包副本端到端用例不适用（skip 非通过）")
class BundleCopyE2ETests(unittest.TestCase):
    """⑩ 机械入包副本：字节相同双写入包；不同内容目标=拒覆盖且写前罢工（banshee 手工 cp 改名搬运的退役替代）。"""

    def _ready_pair(self, tmp_path: Path, work: Path) -> "tuple[Path, Path]":
        src = make_sine(tmp_path, "quiet.wav", 0.02)
        _, plan = run_cli(loud_plan.main, ["--input", str(src), "--output-dir", str(work),
                                           "--profile", "video"])
        normalized = tmp_path / "normalized.wav"
        self.assertTrue(loud_core.render_with_chain(src, plan["chain"], normalized))
        return Path(plan["output"]), normalized

    def test_bundle_copy_written_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            work, bundle = tmp_path / "work", tmp_path / "bundle"
            bundle.mkdir()
            plan_path, master = self._ready_pair(tmp_path, work)
            target = bundle / "loudness-audit.json"
            code, audit = run_cli(loud_verify.main, ["--plan", str(plan_path), "--master", str(master),
                                                     "--output-dir", str(work),
                                                     "--bundle-copy", str(target)])
            self.assertEqual(code, 0)
            native = Path(audit["output"])
            self.assertEqual(native.read_bytes(), target.read_bytes())  # 字节完全相同
            self.assertEqual(audit["bundleCopy"]["path"], str(target))
            self.assertTrue(audit["bundleCopy"]["byteIdenticalToNative"])
            # 入包副本本身就是 G5 校验器要读的合同名文件，内容身份不缺
            copied = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(copied["purpose"], "loud_verify")
            self.assertEqual(copied["status"], "passed")

    def test_bundle_copy_refuses_overwrite_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            work, bundle = tmp_path / "work", tmp_path / "bundle"
            bundle.mkdir()
            plan_path, master = self._ready_pair(tmp_path, work)
            target = bundle / "loudness-audit.json"
            stale = b'{"status": "from-a-previous-project"}\n'
            target.write_bytes(stale)
            code, doc = run_cli(loud_verify.main, ["--plan", str(plan_path), "--master", str(master),
                                                   "--output-dir", str(work),
                                                   "--bundle-copy", str(target)])
            self.assertEqual(code, 1)
            self.assertIn("拒绝覆盖", doc["error"])
            self.assertEqual(target.read_bytes(), stale)  # 旧副本原样未动
            self.assertEqual(list(work.glob("响度-验收审计-*.json")), [])  # 原生报告也没写=写前罢工


if __name__ == "__main__":
    unittest.main()
