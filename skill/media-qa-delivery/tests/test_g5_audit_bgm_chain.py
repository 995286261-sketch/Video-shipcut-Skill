import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skill/media-qa-delivery/scripts/g5_audit_bgm_chain.py"
PYTHON = sys.executable


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


class BgmChainAuditTests(unittest.TestCase):
    """Synthetic zaku-shaped chain: registration -> plan -> alignment/report ->
    contract -> assembly record; the audit must accept the intact chain and
    name the exact broken link for every single-point tampering."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        audio_dir = self.root / "G0素材包" / "07_授权音频"
        audio_dir.mkdir(parents=True)
        self.bgm = audio_dir / "LOW-PHONK.mp3"
        self.bgm.write_bytes(b"chain-fixture-audio" * 100)
        self.report = self.root / "BGM-分析报告.json"
        self._write(self.report, {"loudness": {"integratedLufs": -10.2}})
        self.alignment = self.root / "BGM-对齐建议-v0.2.json"
        self._write(self.alignment, {
            "schemaVersion": "0.2", "purpose": "bgm_alignment",
            "inputs": {"reportCacheKey": {"sha256": sha256(self.bgm)}, "report": str(self.report)},
            "alignment": {"offsetMs": 0, "timelineMs": 12000},
            "fades": {"fadeInMs": 1000, "fadeOutStartMs": 11000, "fadeOutMs": 1000},
            "ducking": [{"sentenceId": "N01", "fromMs": 0, "toMs": 5000},
                        {"sentenceId": "N02", "fromMs": 5000, "toMs": 12000}],
        })
        self.plan = self.root / "G3-剪辑计划-v0.1.json"
        self._write(self.plan, {
            "node": "G3", "status": "approved_for_g4", "projectId": "chain-test", "timelineDurationMs": 12000,
            "sourceAudioPolicy": {"policy": "exclude_copyrighted_source"},
            "bgmPlan": {"audioSha256": sha256(self.bgm), "alignmentRef": str(self.alignment),
                        "alignmentSha256": sha256(self.alignment), "trackOffsetMs": 0,
                        "fades": {"fadeInMs": 1000, "fadeOutStartMs": 11000, "fadeOutMs": 1000}},
        })
        self.contract = self.root / "BGM-混音合同-v0.1.json"
        self.duck_segments = [{"fromMs": 0, "toMs": 12000, "sentenceIds": ["N01", "N02"]}]
        self.fades = {"fadeInMs": 1000, "fadeOutStartMs": 11000, "fadeOutMs": 1000}
        self._write(self.contract, {
            "schemaVersion": "0.1", "skill": "music-expert", "purpose": "bgm_mix_contract",
            "projectId": "chain-test",
            "bgmAudio": {"path": str(self.bgm), "sha256": sha256(self.bgm)},
            "evidence": {"planRef": str(self.plan), "planSha256": sha256(self.plan),
                         "alignmentRef": str(self.alignment), "alignmentSha256": sha256(self.alignment)},
            "timelineMs": 12000, "trackOffsetMs": 0, "bedGainDb": -12.0, "duckReductionDb": 6.0,
            "fades": self.fades, "duckSegments": self.duck_segments, "mixMode": "duck-table",
            "predictedLufs": {"trackIntegratedLufs": -10.2, "bedFullLufs": -22.2, "bedDuckedLufs": -28.2,
                              "narrationTargetLufs": -14.0, "windowLufs": [-32.0, -20.0]},
        })
        self.registration = self.root / "BGM-候选登记.json"
        self._write(self.registration, {
            "sha256": sha256(self.bgm), "audioPath": str(self.bgm),
            "license": "cleared-for-project", "licenseEvidence": "04_授权说明.md",
            "distributionBoundary": "internal_test",
        })
        self.pack = self.root / "material-pack.json"
        self._write(self.pack, {"audioAssets": [{
            "relativePath": "07_授权音频/LOW-PHONK.mp3", "sha256": sha256(self.bgm),
            "bgmRegistration": {"relativePath": str(self.registration), "sha256": sha256(self.registration),
                                "licenseType": "cleared-for-project", "distributionBoundary": "internal_test"},
        }]})
        self.assembly = self.root / "装配记录.json"
        self._write(self.assembly, {"projectId": "chain-test", "bgmMix": {
            "audio": {"path": str(self.bgm), "sha256": sha256(self.bgm)},
            "contract": {"path": str(self.contract), "sha256": sha256(self.contract)},
            "trackOffsetMs": 0, "bedGainDb": -12.0, "duckReductionDb": 6.0,
            "fades": self.fades, "duckSegments": self.duck_segments, "measuredInPlaceLufs": -28.4,
        }})

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def _write(path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def run_audit(self):
        out = self.root / "audit.json"
        result = subprocess.run(
            [PYTHON, str(SCRIPT), "--assembly-record", str(self.assembly), "--plan", str(self.plan),
             "--registration", str(self.registration), "--material-pack", str(self.pack), "--output", str(out)],
            capture_output=True, text=True, encoding="utf-8",
        )
        payload = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
        return result, payload

    def failed_ids(self, payload):
        return {item["id"] for item in payload.get("checks", []) if item["status"] == "failed"}

    def test_intact_chain_passes(self):
        result, payload = self.run_audit()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("passed", payload["status"])
        self.assertEqual("chain-test", payload["projectId"])
        for check_id in ("bgmMixPresent", "contractFileHash", "bgmFileHash", "bgmPlanHash",
                         "planFileHash", "alignmentFileHash", "reportCacheKey", "audibilityRecheck",
                         "executionFidelity", "measuredInPlace", "registrationChain", "licenseCleared",
                         "distributionBoundary", "sourceAudioExcluded"):
            self.assertIn(check_id, {item["id"] for item in payload["checks"]})
        self.assertEqual("internal_test", payload["bgm"]["distributionBoundary"])

    def test_tampered_contract_hash_blocked(self):
        record = json.loads(self.assembly.read_text(encoding="utf-8"))
        record["bgmMix"]["contract"]["sha256"] = "F" * 64
        self._write(self.assembly, record)
        result, payload = self.run_audit()
        self.assertEqual(2, result.returncode)
        self.assertIn("contractFileHash", self.failed_ids(payload))

    def test_wrong_bgm_take_blocked(self):
        self.bgm.write_bytes(b"chain-fixture-audio" * 100 + b"remuxed")
        result, payload = self.run_audit()
        self.assertEqual(2, result.returncode)
        self.assertIn("bgmFileHash", self.failed_ids(payload))

    def test_hand_edited_mix_depth_blocked(self):
        record = json.loads(self.assembly.read_text(encoding="utf-8"))
        record["bgmMix"]["bedGainDb"] = -6.0
        self._write(self.assembly, record)
        result, payload = self.run_audit()
        self.assertEqual(2, result.returncode)
        self.assertIn("executionFidelity", self.failed_ids(payload))

    def test_inaudible_measured_level_blocked(self):
        record = json.loads(self.assembly.read_text(encoding="utf-8"))
        record["bgmMix"]["measuredInPlaceLufs"] = -40.0
        self._write(self.assembly, record)
        result, payload = self.run_audit()
        self.assertEqual(2, result.returncode)
        self.assertIn("measuredInPlace", self.failed_ids(payload))

    def test_boundary_upgrade_blocked(self):
        reg = json.loads(self.registration.read_text(encoding="utf-8"))
        reg["distributionBoundary"] = "worldwide"
        self._write(self.registration, reg)
        result, payload = self.run_audit()
        self.assertEqual(2, result.returncode)
        self.assertIn("distributionBoundary", self.failed_ids(payload))


if __name__ == "__main__":
    unittest.main()
