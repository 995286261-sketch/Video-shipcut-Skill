#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
LIBRARY = SKILL / "scripts" / "music_library.py"
PYTHON = os.environ.get("P0C_PYTHON_BIN") or sys.executable


def sha_of(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


class LibraryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.lib = self.root / "music"
        self.lib.mkdir()
        self.audio = self.root / "song.mp3"
        self.audio.write_bytes(b"unique-audio-bytes-1")
        self.sha = sha_of(self.audio)

    def run_lib(self, *args):
        result = subprocess.run([PYTHON, str(LIBRARY), "--root", str(self.lib), *args],
                                capture_output=True, text=True, encoding="utf-8")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            self.fail(f"non-json output: {result.stdout}\n{result.stderr}")
        return result.returncode, payload

    def card(self):
        return json.loads((self.lib / "tracks" / self.sha[:16] / "track.json").read_text(encoding="utf-8"))

    def test_ingest_merges_aliases_and_never_downgrades_license(self):
        rc, _ = self.run_lib("ingest", "--audio", str(self.audio), "--title", "Good Phonk",
                             "--license", "cc0", "--netease-id", "123", "--provenance", "netease_search")
        self.assertEqual(0, rc)
        self.assertEqual("cc0", self.card()["license"])
        rc, payload = self.run_lib("ingest", "--sha", self.sha, "--title", "别名再遇",
                                   "--license", "uncleared-platform-catalog")
        self.assertEqual(0, rc)
        self.assertIn("licenseKeptExisting:cc0", payload["notes"])
        self.assertEqual("cc0", self.card()["license"])  # 红灯记录永远不能把绿灯洗成红灯，反之亦然：只升不降
        self.assertEqual(2, len(self.card()["aliases"]))

    def test_uncleared_red_light_and_grant_clears_it(self):
        self.run_lib("ingest", "--audio", str(self.audio), "--title", "X",
                     "--license", "uncleared-platform-catalog", "--boundary", "internal_test")
        _, q = self.run_lib("query", "--sha", self.sha, "--project-boundary", "public_release")
        self.assertTrue(any(w.startswith("🔴") for w in q["tracks"][0]["warnings"]))
        rc, _ = self.run_lib("grant", "--sha", self.sha, "--license", "cleared-for-project",
                             "--evidence", "官方渠道购买凭证 #42", "--audio", str(self.audio), "--project", "003")
        self.assertEqual(0, rc)
        self.assertEqual("cleared-for-project", self.card()["license"])
        _, q = self.run_lib("query", "--sha", self.sha)
        self.assertEqual([], q["tracks"][0]["warnings"])
        verdicts = (self.lib / "tracks" / self.sha[:16] / "verdicts.jsonl").read_text(encoding="utf-8")
        self.assertIn("license_granted", verdicts)

    def test_acoustic_records_climax_from_report(self):
        self.run_lib("ingest", "--audio", str(self.audio), "--title", "X")
        report = self.root / "report.json"
        report.write_text(json.dumps({
            "source": {"sha256": self.sha, "decodedDurationMs": 120_000},
            "tempoBpm": 112.35, "loudness": {"integratedLufs": -15.1},
            "energySegments": [{"startMs": 0, "endMs": 60_000, "energyMean": 0.1},
                               {"startMs": 60_000, "endMs": 120_000, "energyMean": 0.9}],
            "energyCurve": [], "beatsMs": [], "onsetsMs": [], "hitPoints": []}), encoding="utf-8")
        rc, payload = self.run_lib("acoustic", "--sha", self.sha, "--report", str(report))
        self.assertEqual(0, rc)
        self.assertEqual(60_000, payload["climaxSegment"]["startMs"])
        _, q = self.run_lib("query", "--sha", self.sha)
        self.assertTrue(q["tracks"][0]["hasAcoustic"])

    def test_relative_notes_are_rejected_as_library_facts(self):
        self.run_lib("ingest", "--audio", str(self.audio), "--title", "X")
        rc, payload = self.run_lib("listen", "--sha", self.sha, "--notes-text", "贴合度 2/10",
                                   "--model", "m", "--prompt-ver", "v1", "--reference", "LOW-PHONK")
        self.assertEqual(2, rc)
        self.assertEqual("rejected", payload["status"])

    def test_absolute_notes_append_and_reuse_by_model_version(self):
        self.run_lib("ingest", "--audio", str(self.audio), "--title", "X")
        rc, _ = self.run_lib("listen", "--sha", self.sha, "--notes-text", "drift phonk，牛铃，副歌在1:02",
                             "--model", "bl 1.22.0", "--prompt-ver", "v1")
        self.assertEqual(0, rc)
        _, q = self.run_lib("query", "--sha", self.sha)
        self.assertEqual(1, len(q["tracks"][0]["listenNotes"]))
        sys.path.insert(0, str(SKILL / "scripts"))
        import music_library
        hit = music_library.latest_listen_note(self.lib, self.sha, "bl 1.22.0", "v1")
        self.assertIn("牛铃", hit[1])
        self.assertIsNone(music_library.latest_listen_note(self.lib, self.sha, "bl 2.0", "v1"))  # 换模型=过期不冒充

    def test_anchor_role_and_query(self):
        self.run_lib("ingest", "--audio", str(self.audio), "--title", "LOW-PHONK")
        brief = self.root / "brief.json"
        brief.write_text(json.dumps({"bpm": 112.35, "energyShape": [0.1, 0.9]}), encoding="utf-8")
        rc, _ = self.run_lib("anchor", "--sha", self.sha, "--brief", str(brief))
        self.assertEqual(0, rc)
        _, q = self.run_lib("query", "--role", "anchor", "--match", "LOW")
        self.assertEqual(1, q["count"])
        self.assertIn("anchor", q["tracks"][0]["track"]["roles"])


if __name__ == "__main__":
    unittest.main()
