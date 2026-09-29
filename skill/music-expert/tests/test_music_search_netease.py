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

    def test_title_slug_keeps_files_identifiable(self):
        self.assertEqual("Melodic_Minor（Phonk）", netease.title_slug("Melodic Minor（Phonk）"))
        self.assertEqual("生龙", netease.title_slug(" 生龙 "))
        self.assertEqual("ab", netease.title_slug("a/:*?\"<>|b"))  # 非法字符直接剥掉
        self.assertEqual("a_b", netease.title_slug("a  b"))  # 空格折叠为下划线
        self.assertEqual("untitled", netease.title_slug(None))
        self.assertLessEqual(len(netease.title_slug("长" * 99)), 48)

    def test_risk_control_payload_blocks(self):
        blocker = netease.classify_block({"code": -462, "verifyType": 50, "message": "请绑定手机后再试哦~"})
        self.assertEqual("risk_control", blocker["type"])

    def test_malformed_payload_blocks(self):
        self.assertEqual("malformed_response", netease.classify_block({"code": 200})["type"])
        self.assertEqual("malformed_response", netease.classify_block("not a dict")["type"])

    def test_ok_payload_passes(self):
        self.assertIsNone(netease.classify_block({"code": 200, "result": {"songs": [FIXTURE_SONG]}}))

    def test_preview_lands_directly_in_output_dir(self):  # Issue ⑪: --output-dir 即落盘目录，不再暗藏一层
        source = SEARCH.read_text(encoding="utf-8")
        self.assertNotIn('output_dir / "candidates"', source)
        self.assertIn("target_dir = args.output_dir", source)


class SchemeUpgradeTests(unittest.TestCase):
    """②（zaku-003 实测）：netease 预览 302 指 http CDN 被 guard 拦死→白名单域名
    才允许 http→https 升级；名单外 http 原样交给 guard 拒——红线=guard 不许拆。"""

    def test_allowlisted_cdn_http_upgrades_to_https(self):
        url, upgraded = netease.upgrade_cdn_scheme("http://m10.music.126.net/2026/x.mp3?sig=1")
        self.assertTrue(upgraded)
        self.assertEqual("https://m10.music.126.net/2026/x.mp3?sig=1", url)
        self.assertIsNone(netease.guard_url(url, netease.DOWNLOAD_ALLOWED_HOSTS))

    def test_https_passes_through(self):
        self.assertEqual(("https://m10.music.126.net/a.mp3", False),
                         netease.upgrade_cdn_scheme("https://m10.music.126.net/a.mp3"))

    def test_off_allowlist_http_never_upgraded_guard_still_refuses(self):
        url, upgraded = netease.upgrade_cdn_scheme("http://evil.example.com/a.mp3")
        self.assertFalse(upgraded)
        self.assertEqual("http://evil.example.com/a.mp3", url)
        refusal = netease.guard_url(url, netease.DOWNLOAD_ALLOWED_HOSTS)
        self.assertIsNotNone(refusal)   # guard 先拒 scheme、名单外同拒——两条防线都在

    def test_download_refuses_off_allowlist_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            failure = netease.download("http://evil.example.com/a.mp3", Path(tmp) / "a.mp3", [])
        self.assertIsNotNone(failure)
        self.assertIn("SSRF guard", failure)

    def test_loopback_exception_not_upgraded(self):
        # 既有测试套件的 discard-port http loopback 例外路径必须原样保留（09-21 guard 批锁例同款回归）。
        url, upgraded = netease.upgrade_cdn_scheme("http://127.0.0.1:9/x.mp3")
        self.assertFalse(upgraded)
        self.assertIsNone(netease.guard_url(url, netease.DOWNLOAD_ALLOWED_HOSTS))

    def test_preview_record_default_base_needs_no_upgrade(self):
        self.assertFalse(netease.PREVIEW_BASE.startswith("http://"))


class CliBlockedTest(unittest.TestCase):
    def run_script(self, args, env=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        full_env = dict(os.environ)
        # Generic env name first (legacy alias P0C_* stays covered by test_music_search_terms)
        full_env["MUSIC_EXPERT_NETEASE_SEARCH_URL"] = "http://127.0.0.1:9/search"  # discard port: instant refusal
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
