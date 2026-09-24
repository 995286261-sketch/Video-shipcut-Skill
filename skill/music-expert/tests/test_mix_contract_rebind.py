"""⑩（转场实跑，2026-09-24 用户裁决）：修订轮合同重锁通道的机器验收。

红线=只动锁、不动参数、不遮丢字节——三条各一负例。进程内直调（脚本纯 stdlib），零子进程零 ffmpeg。
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skill" / "music-expert" / "scripts" / "music_mix_contract_rebind.py"


def load_module():
    spec = importlib.util.spec_from_file_location("music_mix_contract_rebind", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = load_module()


class MixContractRebindTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.audio = self.root / "aji-yema-3only-indulgence.mp3"
        self.audio.write_bytes(b"fake-audio-bytes-v1")
        digest = hashlib.sha256(self.audio.read_bytes()).hexdigest().upper()
        self.plan_old = self.root / "G3-剪辑计划-v0.1.json"
        self.plan_old.write_text(json.dumps({"projectId": "p", "fps": 30}))
        self.plan_new = self.root / "G3-剪辑计划-v0.1-revised.json"
        self.plan_new.write_text(json.dumps({"projectId": "p", "fps": 30, "status": "approved_for_g4"}))
        self.contract = self.root / "BGM-混音合同-v0.1.json"
        self.contract.write_text(json.dumps({
            "schemaVersion": "0.1", "skill": "music-expert", "purpose": "bgm_mix_contract", "projectId": "p",
            "bgmAudio": {"path": str(self.audio), "sha256": digest},
            "evidence": {"planRef": str(self.plan_old), "planSha256": hashlib.sha256(self.plan_old.read_bytes()).hexdigest().upper(),
                         "alignmentRef": "alignment.json", "alignmentSha256": "A" * 64},
            "timelineMs": 38832, "trackOffsetMs": 0, "bedGainDb": -12.0, "duckReductionDb": 6.0,
            "fades": {"fadeInMs": 2000, "fadeOutStartMs": 36832, "fadeOutMs": 2000},
            "ducking": [{"sentenceId": "s01", "fromMs": 217, "toMs": 4737}],
            "duckSegments": [{"fromMs": 217, "toMs": 4737, "sentenceIds": ["s01"]}],
            "mixMode": "duck-table",
            "predictedLufs": {"trackIntegratedLufs": -7.0, "bedDuckedLufs": -25.0},
        }, ensure_ascii=False), encoding="utf-8")

    def run_rebind(self, contract, plan, reason):
        """Invoke the CLI in-process; return (exit_code, parsed_json_output)."""
        argv = ["music_mix_contract_rebind.py", "--contract", str(contract),
                "--plan", str(plan), "--reason", reason]
        backup = sys.argv
        stdout = io.StringIO()
        code = 0
        try:
            sys.argv = argv
            with contextlib.redirect_stdout(stdout):
                try:
                    MODULE.main()
                except SystemExit as exit_signal:
                    code = exit_signal.code or 0
        finally:
            sys.argv = backup
        return code, json.loads(stdout.getvalue())

    def test_rebind_moves_only_the_plan_lock(self):
        code, outcome = self.run_rebind(self.contract, self.plan_new, "修订轮 ⑦⑧ 修复重批")
        self.assertEqual(0, code, outcome)
        self.assertEqual("completed", outcome["status"])
        new = json.loads(Path(outcome["contract"]).read_text(encoding="utf-8"))
        self.assertEqual(str(self.plan_new), new["evidence"]["planRef"])
        self.assertEqual(hashlib.sha256(self.plan_new.read_bytes()).hexdigest().upper(), new["evidence"]["planSha256"])
        old = json.loads(self.contract.read_text(encoding="utf-8"))
        # alignment lock and every mix parameter ride along verbatim; only evidence plan keys moved.
        self.assertEqual(old["evidence"]["alignmentSha256"], new["evidence"]["alignmentSha256"])
        for field in ("timelineMs", "trackOffsetMs", "bedGainDb", "duckReductionDb", "fades",
                      "ducking", "duckSegments", "mixMode", "predictedLufs"):
            self.assertEqual(old[field], new[field])
        self.assertEqual(str(self.contract), new["rebind"]["rebindFrom"]["path"])
        self.assertEqual(hashlib.sha256(self.contract.read_bytes()).hexdigest().upper(),
                         new["rebind"]["rebindFrom"]["sha256"])
        # 旧合同一字未动（重锁=新版本文件，不是原地改写）
        self.assertEqual(old, json.loads(self.contract.read_text(encoding="utf-8")))

    def test_tampered_audio_bytes_refuse_the_relock(self):
        # 变的是音乐字节就不是修订轮锁漂移——拒绝重锁，逼回 music_mix_plan+重批，不许遮丑。
        self.audio.write_bytes(b"different-music")
        code, outcome = self.run_rebind(self.contract, self.plan_new, "尝试")
        self.assertEqual(2, code)
        self.assertIn("BGM 音频字节", json.dumps(outcome, ensure_ascii=False))

    def test_foreign_artifact_is_refused(self):
        fake = self.root / "other-v0.1.json"
        fake.write_text(json.dumps({"skill": "subtitle-expert", "purpose": "subtitle_check_srt"}))
        code, outcome = self.run_rebind(fake, self.plan_new, "尝试")
        self.assertEqual(2, code)
        self.assertIn("身份不符", json.dumps(outcome, ensure_ascii=False))

    def test_version_bumps_forward_never_overwrites(self):
        # 已存在 v0.2 时自增到 v0.3，两个既有文件都不被改写（㉘）。
        (self.root / "BGM-混音合同-v0.2.json").write_text("sentinel", encoding="utf-8")
        code, outcome = self.run_rebind(self.contract, self.plan_new, "第二轮修订")
        self.assertEqual(0, code, outcome)
        self.assertEqual("BGM-混音合同-v0.3.json", Path(outcome["contract"]).name)
        self.assertEqual("sentinel", (self.root / "BGM-混音合同-v0.2.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
