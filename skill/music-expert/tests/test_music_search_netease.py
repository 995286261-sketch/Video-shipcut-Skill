#!/usr/bin/env python3
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
SEARCH = SKILL / "scripts" / "music_search_netease.py"
PYTHON = os.environ.get("P0C_PYTHON_BIN") or sys.executable

spec = importlib.util.spec_from_file_location("music_search_netease", SEARCH)
netease = importlib.util.module_from_spec(spec)
spec.loader.exec_module(netease)

FIXTURE_SONG = {"id": 2721110890, "name": "Melodic Minor（Phonk）", "duration": 124399, "fee": 8,
                "artists": [{"name": "VZEUS"}], "album": {"name": "Melodic Minor（Phonk）"}}


class PureFunctionTest(unittest.TestCase):
    def test_candidate_record_never_claims_license(self):
        record = netease.candidate_record(FIXTURE_SONG)
        self.assertEqual("uncleared-platform-catalog", record["license"])
        self.assertEqual("internal_test", record["distributionBoundary"])
        self.assertEqual("netease_search", record["provenance"])
        self.assertEqual(124399, record["durationMs"])
        self.assertIn("song?id=2721110890", record["sourceUrl"])
        self.assertIn("2721110890", record["previewUrl"])
        self.assertTrue(record["attributionRequired"])

    def test_risk_control_payload_blocks(self):
        blocker = netease.classify_block({"code": -462, "verifyType": 50, "message": "请绑定手机后再试哦~"})
        self.assertEqual("risk_control", blocker["type"])

    def test_malformed_payload_blocks(self):
        self.assertEqual("malformed_response", netease.classify_block({"code": 200})["type"])
        self.assertEqual("malformed_response", netease.classify_block("not a dict")["type"])

    def test_ok_payload_passes(self):
        self.assertIsNone(netease.classify_block({"code": 200, "result": {"songs": [FIXTURE_SONG]}}))


class CliBlockedTest(unittest.TestCase):
    def run_script(self, args, env=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        full_env = dict(os.environ)
        full_env["P0C_NETEASE_SEARCH_URL"] = "http://127.0.0.1:9/search"  # discard port: instant refusal
        if env:
            full_env.update(env)
        result = subprocess.run([PYTHON, str(SEARCH), "--query", "phonk", "--output-dir", tmp.name, *args],
                                capture_output=True, text=True, encoding="utf-8", env=full_env)
        return result, json.loads(result.stdout)

    def test_unreachable_endpoint_is_structured_block(self):
        result, payload = self.run_script([])
        self.assertEqual(2, result.returncode)
        self.assertEqual("blocked", payload["status"])
        # fail-fast on toolchain is by design; the network block is asserted only when
        # previews could actually be attempted (ffmpeg present).
        expected = "network_failed" if __import__("shutil").which("ffmpeg") else "missing_toolchain"
        self.assertEqual(expected, payload["blockers"][0]["type"])

    def test_no_preview_skips_ffmpeg_requirement(self):
        result, payload = self.run_script(["--no-preview"])
        self.assertEqual(2, result.returncode)
        self.assertEqual("blocked", payload["status"])  # still blocked on network, not on toolchain

    def test_query_is_required(self):
        full_env = dict(os.environ)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        result = subprocess.run([PYTHON, str(SEARCH), "--output-dir", tmp.name],
                                capture_output=True, text=True, encoding="utf-8", env=full_env)
        self.assertEqual(2, result.returncode)


if __name__ == "__main__":
    unittest.main()
