#!/usr/bin/env python3
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
REGISTER = SKILL / "scripts" / "music_register_candidate.py"
SEARCH = SKILL / "scripts" / "music_search_freesound.py"
RECOMMEND = SKILL / "scripts" / "music_recommend.py"
PYTHON = os.environ.get("P0C_PYTHON_BIN") or sys.executable


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


class RegisterCandidateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def run_script(self, script, args, env=None):
        full_env = dict(os.environ)
        if env is not None:
            full_env.update(env)
        return subprocess.run([PYTHON, str(script), *args], capture_output=True, text=True,
                              encoding="utf-8", env=full_env)

    def real_wav(self):
        wav = self.root / "tone.wav"
        if shutil.which("ffmpeg"):
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:d=1",
                            str(wav)], check=True, capture_output=True, text=True)
        else:
            self.skipTest("ffmpeg required to synthesize a decodable fixture")
        return wav

    def test_register_valid_candidate(self):
        wav = self.real_wav()
        result = self.run_script(REGISTER, ["--audio", str(wav), "--title", "测试候选",
                                            "--license-type", "cc0", "--license-evidence", "https://example.org/cc0",
                                            "--output-dir", str(self.root / "pool")])
        payload = json.loads(result.stdout)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("completed", payload["status"])
        self.assertEqual("passed", payload["decodeProbe"])
        manifest = Path(payload["candidate"])
        self.assertTrue(manifest.is_file())
        record = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual(sha256(wav), record["sha256"])
        self.assertEqual("internal_test", record["distributionBoundary"])

    def test_register_undecodable_is_blocked(self):
        if not shutil.which("ffmpeg"):
            self.skipTest("ffmpeg required to attempt decode probe")
        fake = self.root / "fake.mp3"
        fake.write_bytes(b"CTENFDAM" + bytes(64))  # issue 023 root cause: renamed stream-encrypted cache
        result = self.run_script(REGISTER, ["--audio", str(fake), "--title", "假文件",
                                            "--license-type", "cc0", "--license-evidence", "https://example.org/x",
                                            "--output-dir", str(self.root / "pool")])
        payload = json.loads(result.stdout)
        self.assertEqual(2, result.returncode)
        self.assertEqual("blocked", payload["status"])
        self.assertEqual("audio_decode_probe_failed", payload["blockers"][0]["type"])

    def test_register_missing_evidence_is_invalid(self):
        wav = self.real_wav()
        result = self.run_script(REGISTER, ["--audio", str(wav), "--title", "无证据",
                                            "--license-type", "cc-by", "--license-evidence", "   ",
                                            "--output-dir", str(self.root / "pool")])
        self.assertEqual(2, result.returncode)
        self.assertEqual("invalid", json.loads(result.stdout)["status"])

    def test_register_controlled_tags_and_word_safe_filename(self):
        wav = self.real_wav()
        result = self.run_script(REGISTER, ["--audio", str(wav), "--title", "Lonely Lies; GOLDKID$ - Interlinked",
                                            "--license-type", "cc0", "--license-evidence", "https://example.org/cc0",
                                            "--tags", "epic,史诗,epic,cinematic",
                                            "--output-dir", str(self.root / "pool")])
        payload = json.loads(result.stdout)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        manifest = Path(payload["candidate"])
        # no mid-word truncation: the full tail survives, separators collapse to '-'
        self.assertIn("Lonely-Lies-GOLDKID-Interlinked", manifest.name)
        self.assertNotIn(" ", manifest.name)
        record = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual(["epic"], record["styleTags"])  # dedup across slug/zh/alias spellings

    def test_register_unknown_tag_is_invalid(self):
        wav = self.real_wav()
        result = self.run_script(REGISTER, ["--audio", str(wav), "--title", "测试",
                                            "--license-type", "cc0", "--license-evidence", "https://example.org/cc0",
                                            "--tags", "vibes,史诗", "--output-dir", str(self.root / "pool")])
        self.assertEqual(2, result.returncode)
        payload = json.loads(result.stdout)
        self.assertEqual("invalid", payload["status"])
        self.assertEqual("tags", payload["errors"][0]["field"])
        self.assertIn("unknown tags: vibes", payload["errors"][0]["detail"])
        self.assertIn("accepted", payload["errors"][0]["detail"])  # error teaches the vocabulary


class LicenseClassificationTest(unittest.TestCase):
    """Live 2026-09-17: the API returns license as a CC URL, not a display name —
    both forms must classify the same way, restricted variants fail closed."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location("music_search_freesound", SEARCH)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_url_forms_accepted(self):
        self.assertEqual("cc0", self.module.classify_license("http://creativecommons.org/publicdomain/zero/1.0/")["licenseType"])
        self.assertEqual("cc-by", self.module.classify_license("https://creativecommons.org/licenses/by/4.0/")["licenseType"])
        self.assertTrue(self.module.classify_license("https://creativecommons.org/licenses/by/4.0/")["attributionRequired"])

    def test_display_names_still_accepted(self):
        self.assertEqual("cc0", self.module.classify_license("Creative Commons 0")["licenseType"])
        self.assertEqual("cc-by", self.module.classify_license("Attribution")["licenseType"])

    def test_restricted_variants_fail_closed(self):
        for raw in ("https://creativecommons.org/licenses/by-nc/4.0/",
                    "https://creativecommons.org/licenses/by-nd/2.1/fr/",
                    "Attribution - Non-Commercial",
                    "Attribution - Non-NoDerivs",
                    "Creative Commons Sampling Plus 1.0",
                    "http://creativecommons.org/licenses/by-nc-sa/3.0/", None, ""):
            self.assertIsNone(self.module.classify_license(raw), raw)


class ApiDriftGuardTest(unittest.TestCase):
    """2026-09-17 live call: Freesound renamed preview keys to hyphen form and
    stopped returning urls.page/attribution in search results; the script must
    keep accepting both spellings and derive the canonical short URL."""

    def test_preview_key_both_spellings_and_short_url_fallback(self):
        source = SEARCH.read_text(encoding="utf-8")
        for marker in ('previews.get("preview_mp3")', 'previews.get("preview-hq-mp3")',
                       'previews.get("preview-lq-mp3")', 'https://freesound.org/s/'):
            self.assertIn(marker, source)


class SearchBlockedTest(unittest.TestCase):
    def test_missing_token_is_structured_block(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = dict(os.environ)
        env["P0C_FREESOUND_TOKEN"] = ""
        result = subprocess.run([PYTHON, str(SEARCH), "--query", "ambient", "--output-dir", tmp.name],
                                capture_output=True, text=True, encoding="utf-8", env=env)
        payload = json.loads(result.stdout)
        self.assertEqual(2, result.returncode)
        self.assertEqual("blocked", payload["status"])
        self.assertEqual("missing_token", payload["blockers"][0]["type"])

    def test_no_query_criteria_is_invalid(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = dict(os.environ)
        env["P0C_FREESOUND_TOKEN"] = "dummy"
        result = subprocess.run([PYTHON, str(SEARCH), "--output-dir", tmp.name],
                                capture_output=True, text=True, encoding="utf-8", env=env)
        self.assertEqual(2, result.returncode)
        self.assertEqual("invalid", json.loads(result.stdout)["status"])

    def run_search(self, tmp, env, *extra):
        result = subprocess.run([PYTHON, str(SEARCH), "--output-dir", tmp, *extra],
                                capture_output=True, text=True, encoding="utf-8", env=env)
        return result.returncode, json.loads(result.stdout)

    def test_terms_file_valid_contract_reaches_token_gate(self):
        # A well-formed terms card parses and only then hits the (deliberately empty)
        # token gate — proving the search-terms contract is consumable by Freesound too.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        card = Path(tmp.name) / "terms.json"
        card.write_text(json.dumps({"purpose": "bgm_search_terms",
                                    "terms": [{"term": "epic", "rationale": "r", "source": "theme"}],
                                    "filters": {"durationMinSec": 120}}), encoding="utf-8")
        env = dict(os.environ)
        env["P0C_FREESOUND_TOKEN"] = ""
        code, payload = self.run_search(tmp.name, env, "--terms-file", str(card), "--no-download")
        self.assertEqual(2, code)
        self.assertEqual("missing_token", payload["blockers"][0]["type"])

    def test_terms_file_rejects_foreign_or_empty_contract(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = dict(os.environ)
        env["P0C_FREESOUND_TOKEN"] = "dummy"
        foreign = Path(tmp.name) / "foreign.json"
        foreign.write_text(json.dumps({"purpose": "something_else", "terms": []}), encoding="utf-8")
        code, payload = self.run_search(tmp.name, env, "--terms-file", str(foreign))
        self.assertEqual(2, code)
        self.assertEqual("invalid", payload["status"])
        self.assertIn("bgm_search_terms", payload["errors"][0]["error"])
        both = Path(tmp.name) / "empty.json"
        both.write_text(json.dumps({"purpose": "bgm_search_terms", "terms": []}), encoding="utf-8")
        code, payload = self.run_search(tmp.name, env, "--terms-file", str(both))
        self.assertEqual(2, code)
        self.assertIn("no terms", payload["errors"][0]["error"])

    def test_query_and_terms_file_are_mutually_exclusive(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = dict(os.environ)
        env["P0C_FREESOUND_TOKEN"] = "dummy"
        card = Path(tmp.name) / "terms.json"
        card.write_text(json.dumps({"purpose": "bgm_search_terms",
                                    "terms": [{"term": "epic", "rationale": "r", "source": "theme"}]}), encoding="utf-8")
        code, payload = self.run_search(tmp.name, env, "--query", "x", "--terms-file", str(card))
        self.assertEqual(2, code)
        self.assertIn("exactly one", payload["errors"][0]["rule"])


class RecommendTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.reports = self.root / "reports"
        self.reports.mkdir()

    def run_script(self, args):
        return subprocess.run([PYTHON, str(RECOMMEND), *args], capture_output=True, text=True,
                              encoding="utf-8")

    def write_report(self, sha, tempo, duration_ms, lufs=-18.0, segments=4, curve=None):
        report = {
            "schemaVersion": "0.1", "skill": "music-expert",
            "cacheKey": {"sha256": sha},
            "source": {"sha256": sha, "decodedDurationMs": duration_ms},
            "tempoBpm": tempo, "beatsMs": [], "onsetsMs": [], "hitPoints": [{"tMs": 0, "kind": "beat"}],
            "energySegments": [{"startMs": i * 1000, "endMs": (i + 1) * 1000, "energyMean": 0.1} for i in range(segments)],
            "energyCurve": curve or [], "loudness": {"integratedLufs": lufs},
        }
        (self.reports / f"BGM-分析报告-{sha[:8]}.json").write_text(json.dumps(report), encoding="utf-8")

    def test_anchored_profile_ranks_by_energy_shape_similarity(self):
        anchor = [0.1, 0.2, 0.9, 0.2] * 4
        self.write_report("B1" * 32, 120.0, 60_000, curve=anchor)
        self.write_report("B2" * 32, 120.0, 60_000, curve=[0.9, 0.1, 0.2, 0.8] * 4)
        self.write_candidates([self.candidate("off-shape", "B2" * 32), self.candidate("on-shape", "B1" * 32)])
        profile = self.root / "profile.json"
        profile.write_text(json.dumps({"targetDurationSec": 30, "minSegments": 2, "maxIntegratedLufs": -14,
                                       "styleBrief": {"bpm": 120.0, "energyShape": anchor}}), encoding="utf-8")
        out = self.root / "rec.json"
        self.run_script(["--profile", str(profile), "--candidates", str(self.root / "pool.json"),
                         "--reports-dir", str(self.reports), "--output", str(out)])
        data = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual("on-shape", data["ranked"][0]["title"])  # 同 BPM/时长/响度，形状近者赢
        self.assertIn("energy_similarity=1.0", data["ranked"][0]["notes"])
        self.assertIn("bpm_proximity=1.0", data["ranked"][0]["notes"])

    def write_candidates(self, entries):
        (self.root / "pool.json").write_text(json.dumps({"candidates": entries}), encoding="utf-8")

    def candidate(self, title, sha, license_type="cc0"):
        return {"title": title, "sha256": sha, "provenance": "freesound_api",
                "licenseType": license_type, "distributionBoundary": "internal_test",
                "decodeProbe": {"status": "passed", "engine": "ffmpeg"}}

    def test_ranks_and_passes(self):
        self.write_report("AA" * 32, 120.0, 60_000)
        self.write_report("BB" * 32, 80.0, 5_000)
        self.write_candidates([self.candidate("good", "AA" * 32), self.candidate("off", "BB" * 32)])
        profile = self.root / "profile.json"
        profile.write_text(json.dumps({"targetDurationSec": 30, "bpmRange": [110, 130], "minSegments": 2, "maxIntegratedLufs": -14}), encoding="utf-8")
        out = self.root / "rec.json"
        result = self.run_script(["--profile", str(profile), "--candidates", str(self.root / "pool.json"),
                                  "--reports-dir", str(self.reports), "--min-score", "0.9", "--min-pass", "1",
                                  "--output", str(out)])
        payload = json.loads(result.stdout)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        data = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual("good", data["ranked"][0]["title"])
        self.assertEqual(1, len(data["passing"]))
        self.assertTrue(data["sufficiency"]["enough"])
        self.assertEqual("1:00.000", data["ranked"][0]["durationDisplay"])

    def test_uncleared_pool_scores_acoustically_under_internal_test_profile(self):
        self.write_report("A1" * 32, 120.0, 60_000)
        self.write_candidates([self.candidate("netease-audition", "A1" * 32,
                                              license_type="uncleared-platform-catalog")])
        profile = self.root / "profile.json"
        profile.write_text(json.dumps({"targetDurationSec": 30, "bpmRange": [110, 130], "minSegments": 2,
                                       "maxIntegratedLufs": -14, "distributionBoundary": "internal_test"}), encoding="utf-8")
        out = self.root / "rec.json"
        self.run_script(["--profile", str(profile), "--candidates", str(self.root / "pool.json"),
                         "--reports-dir", str(self.reports), "--min-score", "0.9", "--output", str(out)])
        data = json.loads(out.read_text(encoding="utf-8"))
        top = data["ranked"][0]
        self.assertGreaterEqual(top["score"], 0.9)  # 内测画像内不压分，按声学原分排
        self.assertIn("uncleared_internal_test_only", top["notes"])
        self.assertTrue(top["infringementRisk"])
        self.assertIn("侵权", data["licenseWarning"])
        echo = out.parent / "BGM-推荐回显-v0.1.md"
        self.assertTrue(echo.is_file())
        self.assertIn("⚠ 未清权", echo.read_text(encoding="utf-8"))

    def test_echo_denominator_labels_and_rerun_versioning(self):  # Issues ⑩ ⑬
        self.write_report("A3" * 32, 120.0, 60_000)
        self.write_candidates([self.candidate("cand", "A3" * 32)])
        profile = self.root / "profile.json"
        profile.write_text(json.dumps({"targetDurationSec": 30, "minSegments": 2,
                                       "maxIntegratedLufs": -14}), encoding="utf-8")
        out = self.root / "rec.json"
        args = ["--profile", str(profile), "--candidates", str(self.root / "pool.json"),
                "--reports-dir", str(self.reports), "--output", str(out)]
        self.run_script(args)
        echo = (out.parent / "BGM-推荐回显-v0.1.md").read_text(encoding="utf-8")
        self.assertIn("通过 1/1（充分性阈值 3）", echo)  # 分母=受评池，阈值单列，不再"通过 6/3"
        self.run_script(args)  # 改画像重跑=必然多轮
        self.assertTrue((out.parent / "BGM-推荐回显-v0.2.md").is_file())
        self.assertIn("v0.2", (out.parent / "BGM-推荐回显-v0.2.md").read_text(encoding="utf-8"))
        self.assertTrue((out.parent / "BGM-推荐回显-v0.1.md").is_file())  # 旧轮证据保留

    def test_uncleared_pool_penalized_under_stricter_boundary(self):
        self.write_report("A2" * 32, 120.0, 60_000)
        self.write_candidates([self.candidate("netease-audition", "A2" * 32,
                                              license_type="uncleared-platform-catalog")])
        profile = self.root / "profile.json"
        profile.write_text(json.dumps({"targetDurationSec": 30, "bpmRange": [110, 130], "minSegments": 2,
                                       "maxIntegratedLufs": -14, "distributionBoundary": "commercial"}), encoding="utf-8")
        out = self.root / "rec.json"
        self.run_script(["--profile", str(profile), "--candidates", str(self.root / "pool.json"),
                         "--reports-dir", str(self.reports), "--output", str(out)])
        data = json.loads(out.read_text(encoding="utf-8"))
        top = data["ranked"][0]
        self.assertLess(top["score"], 0.35)  # 商用边界：未清权重罚，不得为对外分发背书
        self.assertIn("license_weighted_down", top["notes"])

    def test_anchored_mode_demotes_out_of_shape_track(self):
        # 半速氛围曲 vs 锚定高燃曲线：即使 BPM 区间内，能量形状差异要拉低总分（zaku 自测教训）
        anchor = [0.2, 0.3, 0.95, 0.3] * 4
        self.write_report("A1" * 32, 112.0, 60_000, curve=anchor)
        self.write_report("A2" * 32, 96.0, 60_000, curve=[0.5, 0.52, 0.48, 0.51] * 4)
        self.write_candidates([self.candidate("flat", "A2" * 32), self.candidate("match", "A1" * 32)])
        profile = self.root / "profile.json"
        profile.write_text(json.dumps({"targetDurationSec": 30, "bpmRange": [90, 135], "minSegments": 2,
                                       "maxIntegratedLufs": -14, "styleBrief": {"bpm": 112.0, "energyShape": anchor}}), encoding="utf-8")
        out = self.root / "rec.json"
        self.run_script(["--profile", str(profile), "--candidates", str(self.root / "pool.json"),
                         "--reports-dir", str(self.reports), "--output", str(out)])
        data = json.loads(out.read_text(encoding="utf-8"))
        match, flat = data["ranked"][0], data["ranked"][1]
        self.assertEqual("match", match["title"])
        self.assertLess(flat["score"], 0.8)
        self.assertGreater(match["score"] - flat["score"], 0.1)  # 必须有区分度，不能再并列满分

    def test_short_candidate_is_penalized_not_passed(self):
        self.write_report("CC" * 32, 120.0, 3_000)
        self.write_candidates([self.candidate("short", "CC" * 32)])
        profile = self.root / "profile.json"
        profile.write_text(json.dumps({"targetDurationSec": 60, "bpmRange": [110, 130]}), encoding="utf-8")
        out = self.root / "rec.json"
        self.run_script(["--profile", str(profile), "--candidates", str(self.root / "pool.json"),
                         "--reports-dir", str(self.reports), "--min-score", "0.9", "--min-pass", "3", "--output", str(out)])
        data = json.loads(out.read_text(encoding="utf-8"))
        self.assertFalse(data["sufficiency"]["enough"])
        self.assertTrue(data["sufficiency"]["gapAction"])

    def test_unanalyzed_candidate_is_quarantined(self):
        self.write_candidates([self.candidate("no-report", "DD" * 32)])
        profile = self.root / "profile.json"
        profile.write_text(json.dumps({"targetDurationSec": 30}), encoding="utf-8")
        out = self.root / "rec.json"
        self.run_script(["--profile", str(profile), "--candidates", str(self.root / "pool.json"),
                         "--reports-dir", str(self.reports), "--output", str(out)])
        data = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(1, len(data["unanalyzed"]))
        self.assertEqual(0, len(data["ranked"]))

    def test_profile_style_tags_reward_vocabulary_overlap(self):
        self.write_report("EE" * 32, 120.0, 60_000)
        self.write_report("FF" * 32, 120.0, 60_000)
        matched = self.candidate("on-theme", "EE" * 32)
        matched["styleTags"] = ["epic", "orchestral"]
        raw = self.candidate("raw-tags", "FF" * 32)
        raw["tags"] = ["cinematic", "drums", "totallyweird"]
        self.write_candidates([raw, matched])
        profile = self.root / "profile.json"
        profile.write_text(json.dumps({"targetDurationSec": 30, "styleTags": ["epic", "orchestral"]}), encoding="utf-8")
        out = self.root / "rec.json"
        result = self.run_script(["--profile", str(profile), "--candidates", str(self.root / "pool.json"),
                                  "--reports-dir", str(self.reports), "--output", str(out)])
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        data = json.loads(out.read_text(encoding="utf-8"))
        ranked = {item["title"]: item for item in data["ranked"]}
        self.assertEqual(1.0, ranked["on-theme"]["score"])
        self.assertIn("tags 2/2", ranked["on-theme"]["notes"])
        # foreign raw tags are normalized through the same vocabulary; "totallyweird" drops out
        self.assertEqual(["epic", "percussive"], ranked["raw-tags"]["styleTags"])
        self.assertAlmostEqual(0.95, ranked["raw-tags"]["score"])
        self.assertIn("tags 1/2", ranked["raw-tags"]["notes"])

    def test_unmappable_profile_tag_is_invalid(self):
        self.write_report("EE" * 32, 120.0, 60_000)
        self.write_candidates([self.candidate("x", "EE" * 32)])
        profile = self.root / "profile.json"
        profile.write_text(json.dumps({"targetDurationSec": 30, "styleTags": ["vibes"]}), encoding="utf-8")
        result = self.run_script(["--profile", str(profile), "--candidates", str(self.root / "pool.json"),
                                  "--reports-dir", str(self.reports), "--output", str(self.root / "rec.json")])
        self.assertEqual(2, result.returncode)
        payload = json.loads(result.stdout)
        self.assertEqual("invalid", payload["status"])
        self.assertEqual("profile.styleTags", payload["errors"][0]["field"])

    def test_no_candidates_is_blocked(self):
        profile = self.root / "profile.json"
        profile.write_text(json.dumps({"targetDurationSec": 30}), encoding="utf-8")
        result = self.run_script(["--profile", str(profile), "--candidates", str(self.root / "missing.json"),
                                  "--reports-dir", str(self.reports), "--output", str(self.root / "rec.json")])
        self.assertEqual(2, result.returncode)
        self.assertEqual("no_candidates", json.loads(result.stdout)["blockers"][0]["type"])


class SsrfGuardTest(unittest.TestCase):
    """Mimosa L3 (2026-09-21): every outbound fetch must pass the URL allowlist guard."""

    @classmethod
    def setUpClass(cls):
        import importlib
        sys.path.insert(0, str(SKILL / "scripts"))
        cls.fs = importlib.import_module("music_search_freesound")
        cls.ne = importlib.import_module("music_search_netease")

    def test_freesound_only_official_https(self):
        for url in ("http://freesound.org/x", "https://evil.com/x",
                    "https://freesound.org.evil.cn/x", "https://169.254.169.254/latest/meta-data/",
                    "file:///etc/passwd"):
            self.assertIsNotNone(self.fs.guard_url(url), url)
        self.assertIsNone(self.fs.guard_url("https://freesound.org/data/previews/a.mp3"))

    def test_freesound_download_refuses_without_network(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        error = self.fs.download("file:///etc/passwd", Path(tmp.name) / "x.mp3")
        self.assertIn("SSRF guard", error)

    def test_netease_allowlists_and_loopback_exception(self):
        g = self.ne.guard_url
        for url in ("https://evil.com/x", "http://169.254.169.254/", "file:///etc/passwd",
                    "https://not126.net.evil.cn/p.mp3"):
            self.assertIsNotNone(g(url, self.ne.DOWNLOAD_ALLOWED_HOSTS), url)
        self.assertIsNone(g("https://music.163.com/api", self.ne.SEARCH_ALLOWED_HOSTS))
        self.assertIsNone(g("https://ws-stream-126kt.netease.com/p.mp3", self.ne.DOWNLOAD_ALLOWED_HOSTS))
        # loopback http stays allowed for the discard-port test suites
        self.assertIsNone(g("http://127.0.0.1:9/search", self.ne.SEARCH_ALLOWED_HOSTS))


if __name__ == "__main__":
    unittest.main()
