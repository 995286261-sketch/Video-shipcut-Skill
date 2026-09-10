#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
TERMS = SKILL / "scripts" / "music_search_terms.py"
NETEASE = SKILL / "scripts" / "music_search_netease.py"
PYTHON = os.environ.get("P0C_PYTHON_BIN") or sys.executable


class TermsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.brief = self.root / "style-brief.json"
        self.brief.write_text(json.dumps({"bpmRange": [101.1, 123.6]}), encoding="utf-8")

    def run_terms(self, extra):
        return subprocess.run([PYTHON, str(TERMS), "--output-dir", str(self.root / "out"), *extra],
                              capture_output=True, text=True, encoding="utf-8")

    def contract(self):
        return json.loads((self.root / "out" / "BGM-检索词-v0.1.json").read_text(encoding="utf-8"))

    def test_happy_path_prefers_user_words_and_derives_filters(self):
        result = self.run_terms(["--preference", "我要 phonk 那种", "--term", "phonk",
                                 "--term", "机战 燃向 电子", "--note", "机战 燃向 电子=主题翻译：机战科普+热血怀旧",
                                 "--theme", "扎古混剪科普", "--style-brief", str(self.brief), "--timeline-ms", "113310"])
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("completed", payload["status"])
        contract = self.contract()
        by_term = {r["term"]: r for r in contract["terms"]}
        self.assertEqual("preference", by_term["phonk"]["source"])
        self.assertEqual("theme", by_term["机战 燃向 电子"]["source"])
        self.assertEqual(114, contract["filters"]["durationMinSec"])
        self.assertEqual([101.1, 123.6], contract["filters"]["bpmRange"])
        self.assertTrue((self.root / "out" / "BGM-检索词回显-v0.1.md").is_file())

    def test_term_without_rationale_is_invalid(self):
        result = self.run_terms(["--term", "史诗 战斗 BGM"])
        self.assertEqual(2, result.returncode)
        payload = json.loads(result.stdout)
        self.assertEqual("invalid", payload["status"])
        self.assertEqual("note", payload["errors"][0]["field"])

    def test_dedupe_and_count_bounds(self):
        result = self.run_terms(["--term", "a", "--term", " A ", "--note", "a=x"])
        contract = json.loads(result.stdout)
        self.assertEqual(1, contract["terms"])
        many = []
        for i in range(7):
            many += ["--term", f"t{i}", "--note", f"t{i}=依据"]
        result = self.run_terms(many)
        self.assertEqual(2, result.returncode)
        self.assertEqual("invalid", json.loads(result.stdout)["status"])

    def test_brief_without_bpm_range_is_invalid(self):
        bad = self.root / "bad-brief.json"
        bad.write_text(json.dumps({"bpm": 120}), encoding="utf-8")
        result = self.run_terms(["--term", "phonk", "--note", "phonk=x", "--style-brief", str(bad)])
        self.assertEqual(2, result.returncode)
        self.assertEqual("styleBrief", json.loads(result.stdout)["errors"][0]["field"])


class NeteaseTermsFileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def run_search(self, args):
        env = dict(os.environ)
        env["P0C_NETEASE_SEARCH_URL"] = "http://127.0.0.1:9/search"
        return subprocess.run([PYTHON, str(NETEASE), "--output-dir", str(self.root), *args],
                              capture_output=True, text=True, encoding="utf-8", env=env)

    def test_query_and_terms_file_are_mutually_exclusive(self):
        contract = self.root / "terms.json"
        contract.write_text(json.dumps({"purpose": "bgm_search_terms", "terms": [{"term": "a"}]}), encoding="utf-8")
        result = self.run_search(["--query", "x", "--terms-file", str(contract), "--no-preview"])
        self.assertEqual(2, result.returncode)
        self.assertEqual("invalid", json.loads(result.stdout)["status"])

    def test_wrong_purpose_contract_is_invalid(self):
        contract = self.root / "terms.json"
        contract.write_text(json.dumps({"purpose": "something_else", "terms": []}), encoding="utf-8")
        result = self.run_search(["--terms-file", str(contract), "--no-preview"])
        self.assertEqual(2, result.returncode)
        payload = json.loads(result.stdout)
        self.assertEqual("invalid", payload["status"])
        self.assertEqual("termsFile", payload["errors"][0]["field"])

    def test_valid_contract_reaches_network_stage(self):
        contract = self.root / "terms.json"
        contract.write_text(json.dumps({"purpose": "bgm_search_terms",
                                        "terms": [{"term": "phonk 器乐"}, {"term": "燃向 电子"}],
                                        "filters": {"durationMinSec": 114}}), encoding="utf-8")
        result = self.run_search(["--terms-file", str(contract), "--no-preview"])
        payload = json.loads(result.stdout)
        self.assertEqual("blocked", payload["status"])  # unreachable endpoint, after terms validated
        self.assertEqual("network_failed", payload["blockers"][0]["type"])


if __name__ == "__main__":
    unittest.main()
