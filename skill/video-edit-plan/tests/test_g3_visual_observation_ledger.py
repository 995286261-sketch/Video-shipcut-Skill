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

    def test_supersede_retires_active_record_and_returns_lineage(self):
        original = self.record()
        self.assertEqual(0, self.command("--append", original).returncode)
        replacement = self.record("obs-002")
        replacement.update({"correctionSource": "用户指认画面为驾驶员而非目标机体", "observedVisuals": "人物可见，目标主体未确认", "identityStatus": "person_only"})
        payload = {"supersedesRecordId": "obs-001", "newRecord": replacement}
        result = self.command("--supersede", payload)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        ledger = json.loads(self.ledger.read_text(encoding="utf-8"))
        self.assertEqual("superseded", ledger["records"][0]["analysisStatus"])
        self.assertEqual("obs-002", ledger["records"][0]["supersededBy"])
        self.assertEqual("obs-001", ledger["records"][1]["supersedesRecordId"])
        lookup = self.command("--lookup", original)
        self.assertIn("obs-002", lookup.stdout)
        self.assertNotIn('"recordId": "obs-001"', lookup.stdout)
        history = subprocess.run([PYTHON, str(SCRIPT), "--ledger", str(self.ledger), "--lookup", str(self.write("history-query.json", original)), "--history"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(0, history.returncode, history.stdout + history.stderr)
        self.assertIn("obs-001", history.stdout)
        self.assertIn("obs-002", history.stdout)

    def test_supersede_rejects_invalid_transitions(self):
        original = self.record()
        self.assertEqual(0, self.command("--append", original).returncode)
        replacement = self.record("obs-002")
        replacement.pop("correctionSource", None)
        bad = self.command("--supersede", {"supersedesRecordId": "obs-001", "newRecord": replacement})
        self.assertNotEqual(0, bad.returncode)
        self.assertIn("correctionSource", bad.stdout)
        bad = self.command("--supersede", {"supersedesRecordId": "missing", "newRecord": {**replacement, "correctionSource": "用户指认"}})
        self.assertNotEqual(0, bad.returncode)
        self.assertIn("not an active record", bad.stdout)
        wrong_key = {**replacement, "correctionSource": "用户指认", "sourceMs": 80000}
        bad = self.command("--supersede", {"supersedesRecordId": "obs-001", "newRecord": wrong_key})
        self.assertNotEqual(0, bad.returncode)
        self.assertIn("exact reuse key", bad.stdout)

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
