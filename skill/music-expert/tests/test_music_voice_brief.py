"""music_voice_brief 回归：计划落位+实测时长的机械缝合，罢工面全覆盖（台账⑭小1 甲案）。

CLI 一律进程内调用（13 工具环境先例：subprocess 变量拼装表会被安全钩子误拦）。
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import music_voice_brief  # noqa: E402


def plan_doc(segments, status="approved_for_g4", timeline=120000):
    return {"schemaVersion": "0.2", "node": "G3", "status": status, "projectId": "vb-test",
            "timelineDurationMs": timeline,
            "segments": [{"segmentId": seg["segmentId"], "narrationText": seg["narrationText"],
                          "narrationStartMs": seg["narrationStartMs"], "narrationEndMs": seg["narrationEndMs"]}
                         for seg in segments]}


def manifest_doc(sentences, voice="Samantha"):
    return {"schemaVersion": "0.1", "node": "G2", "purpose": "narration_synthesis_measured_durations",
            "voice": voice, "voiceTier": "preview_only",
            "measuredTotalDurationMs": sum(item["durationMs"] for item in sentences),
            "sentences": [{"sentenceId": item["sentenceId"], "text": item["text"],
                           "file": item["sentenceId"] + ".wav", "durationMs": item["durationMs"]}
                          for item in sentences]}


class VoiceBriefTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.out = self.root / "out"
        self.plan_path = self.root / "plan.json"
        self.manifest_path = self.root / "manifest.json"

    def tearDown(self):
        self.temp.cleanup()

    def write_inputs(self, plan, manifest):
        self.plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        self.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    def run_cli(self):
        argv = ["--plan", str(self.plan_path), "--voice-manifest", str(self.manifest_path),
                "--output-dir", str(self.out)]
        buf = io.StringIO()
        code = 0
        try:
            with contextlib.redirect_stdout(buf):
                music_voice_brief.main(argv)
        except SystemExit as exc:
            code = exc.code or 0
        return code, json.loads(buf.getvalue())

    def test_two_fragments_stitch_into_one_sentence(self):
        # banshee 实例形：seg-02a/02b 同句切分，起点取首片段、窗口到末片段
        self.write_inputs(
            plan_doc([
                {"segmentId": "seg-01", "narrationText": "Alpha.", "narrationStartMs": 0, "narrationEndMs": 3000},
                {"segmentId": "seg-02a", "narrationText": "Bravo one,", "narrationStartMs": 5000, "narrationEndMs": 7000},
                {"segmentId": "seg-02b", "narrationText": "bravo two.", "narrationStartMs": 7000, "narrationEndMs": 10000},
            ]),
            manifest_doc([
                {"sentenceId": "s01", "text": "Alpha.", "durationMs": 3000},
                {"sentenceId": "s02", "text": "Bravo one, bravo two.", "durationMs": 5000},
            ]))
        code, payload = self.run_cli()
        self.assertEqual(0, code, json.dumps(payload, ensure_ascii=False))
        self.assertEqual("completed", payload["status"])
        brief = json.loads(Path(payload["brief"]).read_text(encoding="utf-8"))
        self.assertEqual([{"sentenceId": "s01", "startMs": 0, "durationMs": 3000},
                          {"sentenceId": "s02", "startMs": 5000, "durationMs": 5000}],
                         [{"sentenceId": item["sentenceId"], "startMs": item["startMs"],
                           "durationMs": item["durationMs"]} for item in brief["sentences"]])
        self.assertEqual("v0.1", brief["artifactVersion"])

    def test_unapproved_plan_refused(self):
        self.write_inputs(plan_doc([{"segmentId": "seg-01", "narrationText": "Alpha.",
                                     "narrationStartMs": 0, "narrationEndMs": 3000}], status="draft"),
                          manifest_doc([{"sentenceId": "s01", "text": "Alpha.", "durationMs": 3000}]))
        code, payload = self.run_cli()
        self.assertEqual(2, code)
        self.assertIn("approved_for_g4", payload["errors"][0]["rule"])

    def test_window_mismatch_named_with_numbers(self):
        # 落位窗口 3000 vs 实测 4000：塞不进，点名两个数字（14 大口径禁手工调和平账）
        self.write_inputs(
            plan_doc([{"segmentId": "seg-01", "narrationText": "Alpha.", "narrationStartMs": 0,
                       "narrationEndMs": 3000}]),
            manifest_doc([{"sentenceId": "s01", "text": "Alpha.", "durationMs": 4000}]))
        code, payload = self.run_cli()
        self.assertEqual(2, code)
        errors = payload["errors"]
        self.assertEqual("narrationWindow", errors[0]["field"])
        self.assertIn("3000ms", errors[0]["rule"])
        self.assertIn("4000ms", errors[0]["rule"])

    def test_sentence_missing_placement_named(self):
        # 改稿没回炉计划：s02 在剩余片段里配不到落位，点名
        self.write_inputs(
            plan_doc([{"segmentId": "seg-01", "narrationText": "Alpha.", "narrationStartMs": 0,
                       "narrationEndMs": 3000}]),
            manifest_doc([{"sentenceId": "s01", "text": "Alpha.", "durationMs": 3000},
                          {"sentenceId": "s02", "text": "Reworded later.", "durationMs": 3000}]))
        code, payload = self.run_cli()
        self.assertEqual(2, code)
        rules = [item["rule"] for item in payload["errors"]]
        self.assertTrue(any("找不到落位" in rule for rule in rules))

    def test_leftover_fragment_named(self):
        # 删句未回炉：seg-02 的落位没人认领，两账对不平点名段 id
        self.write_inputs(
            plan_doc([{"segmentId": "seg-01", "narrationText": "Alpha.", "narrationStartMs": 0,
                       "narrationEndMs": 3000},
                      {"segmentId": "seg-02", "narrationText": "Orphan text.", "narrationStartMs": 5000,
                       "narrationEndMs": 8000}]),
            manifest_doc([{"sentenceId": "s01", "text": "Alpha.", "durationMs": 3000}]))
        code, payload = self.run_cli()
        self.assertEqual(2, code)
        rules = [item["rule"] for item in payload["errors"]]
        self.assertTrue(any("没有被任何实测句认领" in rule for rule in rules))
        self.assertTrue(any("seg-02" in item.get("detail", "") for item in payload["errors"]))

    def test_fragment_cutting_mid_sentence_refused_not_blended(self):
        # 段边界切开句子：拼接 overshoot，罢工不调和
        self.write_inputs(
            plan_doc([{"segmentId": "seg-01", "narrationText": "Alpha Beta.", "narrationStartMs": 0,
                       "narrationEndMs": 3000}]),
            manifest_doc([{"sentenceId": "s01", "text": "Alpha.", "durationMs": 3000}]))
        code, payload = self.run_cli()
        self.assertEqual(2, code)
        self.assertIn("缝合失败", payload["errors"][0]["rule"])

    def test_whitespace_only_drift_is_normed_but_letter_drift_strikes(self):
        self.write_inputs(
            plan_doc([{"segmentId": "seg-01", "narrationText": "Alpha   Beta.", "narrationStartMs": 0,
                       "narrationEndMs": 3000}]),
            manifest_doc([{"sentenceId": "s01", "text": "Alpha Beta.", "durationMs": 3000}]))
        code, payload = self.run_cli()
        self.assertEqual(0, code, json.dumps(payload, ensure_ascii=False))
        self.write_inputs(
            plan_doc([{"segmentId": "seg-01", "narrationText": "Alpha Beta!", "narrationStartMs": 0,
                       "narrationEndMs": 3000}]),
            manifest_doc([{"sentenceId": "s01", "text": "Alpha Beta.", "durationMs": 3000}]))
        code, payload = self.run_cli()
        self.assertEqual(2, code)
        self.assertIn("缝合失败", payload["errors"][0]["rule"])

    def test_rerun_appends_version_keeps_old(self):
        # 小项2 同规：自增永不覆盖
        self.write_inputs(
            plan_doc([{"segmentId": "seg-01", "narrationText": "Alpha.", "narrationStartMs": 0,
                       "narrationEndMs": 3000}]),
            manifest_doc([{"sentenceId": "s01", "text": "Alpha.", "durationMs": 3000}]))
        code, p1 = self.run_cli()
        self.assertEqual(0, code, json.dumps(p1, ensure_ascii=False))
        old_bytes = Path(p1["brief"]).read_bytes()
        code, p2 = self.run_cli()
        self.assertEqual(0, code, json.dumps(p2, ensure_ascii=False))
        self.assertIn("-v0.2.json", Path(p2["brief"]).name)
        self.assertEqual("v0.2", json.loads(Path(p2["brief"]).read_text(encoding="utf-8"))["artifactVersion"])
        self.assertEqual(old_bytes, Path(p1["brief"]).read_bytes())


if __name__ == "__main__":
    unittest.main()
