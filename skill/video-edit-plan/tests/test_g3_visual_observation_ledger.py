import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "g3_visual_observation_ledger.py"
PYTHON = sys.executable


class VisualObservationLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.ledger = self.root / "ledger.json"
        self.ledger.write_text(json.dumps({"schemaVersion": "0.1", "node": "G3", "projectId": "p", "records": []}), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def record(self, record_id="obs-001"):
        return {"recordId": record_id, "sourceAssetId": "source-1", "sourceSha256": "hash", "sourceMs": 70000,
            "frameExtractionSpec": "jpeg:q2", "analysisPromptVersion": "v1", "provider": "local", "model": "vision-1",
            "analysisStatus": "completed", "frameRef": "frame.jpg", "observedVisuals": "目标主体可见", "riskFlags": [], "createdAt": "2026-08-25T00:00:00Z"}

    def write(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def command(self, option, payload=None):
        args = [PYTHON, str(SCRIPT), "--ledger", str(self.ledger), option]
        if payload is not None:
            args.append(str(self.write(option[2:] + ".json", payload)))
        return subprocess.run(args, capture_output=True, text=True, encoding="utf-8")

    def test_append_then_lookup_reuses_same_exact_key(self):
        self.assertEqual(0, self.command("--append", self.record()).returncode)
        result = self.command("--lookup", self.record())
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn('"found": true', result.stdout)

    def test_duplicate_exact_key_is_rejected(self):
        self.assertEqual(0, self.command("--append", self.record()).returncode)
        result = self.command("--append", self.record("obs-002"))
        self.assertNotEqual(0, result.returncode)
        self.assertIn("reuse it", result.stdout)

    def test_timeout_is_retrievable_not_silently_lost(self):
        value = self.record()
        value["analysisStatus"] = "timeout"
        value.pop("observedVisuals")
        self.assertEqual(0, self.command("--append", value).returncode)
        result = self.command("--lookup", value)
        self.assertIn("timeout", result.stdout)


if __name__ == "__main__":
    unittest.main()
