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

    def test_verdict_rejects_ghost_sha_and_creates_no_directory(self):
        """⑦（zaku-003 幽灵目录险成案）：凭记忆写的 sha 不许被库照单全收、静默建目录。"""
        ghost = "A" * 63 + "9"  # 从未 ingest 的 sha
        self.assertFalse((self.lib / "tracks" / ghost[:16]).exists())
        rc, payload = self.run_lib("verdict", "--sha", ghost, "--text", "用户判决：就用它", "--who", "user")
        self.assertEqual(2, rc)
        self.assertIn("track_not_registered", payload["errors"][0]["rule"])
        self.assertFalse((self.lib / "tracks" / ghost[:16]).exists())  # 一字节不落盘

    def test_derived_writers_require_full_sha_match_not_just_16_prefix(self):
        """⑦ 深案：前 16 位撞车但尾段不同（当年 …430B vs …D291）＝串档，同样逐字拒。"""
        self.run_lib("ingest", "--audio", str(self.audio), "--title", "X")
        # wrong 与在册曲同 16 位前 缀（目录同档），但全量 sha 尾段不同＝另一条真曲的判决
        wrong = self.sha[:16] + ("0" * (len(self.sha) - 16) if self.sha[16] != "0" else "1" * (len(self.sha) - 16))
        track_dir = self.lib / "tracks" / self.sha[:16]
        for action, extra in [("verdict", ["--text", "判决", "--who", "user"]),
                              ("listen", ["--notes-text", "绝对笔记", "--model", "stub", "--prompt-ver", "v1"]),
                              ("grant", ["--license", "cleared-for-project", "--evidence", "凭据"]),
                              ("anchor", ["--brief", str(self.audio)])]:
            rc, payload = self.run_lib(action, "--sha", wrong, *extra)
            self.assertEqual(2, rc, f"{action} 放行了撞前缀假 sha")
            self.assertFalse((track_dir / "verdicts.jsonl").exists())
            self.assertFalse((track_dir / "listen.md").exists())
            self.assertFalse((track_dir / "style-brief.json").exists())
            self.assertEqual("X", json.loads((track_dir / "track.json").read_text(encoding="utf-8"))["aliases"][-1]["title"])
            self.assertNotIn("anchor", json.loads((track_dir / "track.json").read_text(encoding="utf-8"))["roles"])
        # 真 sha 照旧通过（大写小写归一也不误伤）
        rc, _ = self.run_lib("verdict", "--sha", self.sha.lower(), "--text", "判决", "--who", "user")
        self.assertEqual(0, rc)
        self.assertTrue((track_dir / "verdicts.jsonl").exists())

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

    def test_boundary_mismatch_warns_for_every_license_level(self):  # Issue ⑤
        rc, _ = self.run_lib("ingest", "--audio", str(self.audio), "--title", "Cleared",
                             "--license", "cleared-for-project", "--boundary", "internal_test",
                             "--project", "zaku-intro-001")
        self.assertEqual(0, rc)
        _, q = self.run_lib("query", "--sha", self.sha, "--project-boundary", "public_bilibili")
        warns = q["tracks"][0]["warnings"]
        self.assertTrue(any(w.startswith("🔴") and "cleared-for-project" in w for w in warns),
                        f"cleared-for-project 换对外项目必须红牌: {warns}")
        _, q_same = self.run_lib("query", "--sha", self.sha, "--project-boundary", "internal_test")
        self.assertEqual([], q_same["tracks"][0]["warnings"])

    def test_list_browses_the_library(self):  # Issue ④
        rc, _ = self.run_lib("ingest", "--audio", str(self.audio), "--title", "One",
                             "--license", "uncleared-platform-catalog", "--boundary", "internal_test")
        self.assertEqual(0, rc)
        rc, listing = self.run_lib("list")
        self.assertEqual(0, rc)
        self.assertEqual(1, listing["count"])
        row = listing["tracks"][0]
        self.assertEqual("One", row["title"])
        self.assertEqual(self.sha[:12], row["sha256"])
        self.assertEqual("uncleared-platform-catalog", row["license"])


if __name__ == "__main__":
    unittest.main()
