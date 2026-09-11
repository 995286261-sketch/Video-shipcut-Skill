#!/usr/bin/env python3
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
LISTEN = SKILL / "scripts" / "music_listen_omni.py"
PYTHON = os.environ.get("P0C_PYTHON_BIN") or sys.executable

STUB = """#!/bin/sh
case "$1" in
  --version) echo "bl 9.9.9-stub" ;;
  auth) echo "  API key (model):  config  sk-stub" ;;
  omni)
    echo call >> "$(dirname "$0")/calls.log"
    for a in "$@"; do
      case "$a" in *boom*) echo "stub refuses DRM-ish track" >&2; exit 1 ;; esac
    done
    echo "content: |-  风格差距：与原曲同为 drift phonk，牛铃一致。贴合度 8.5。" ;;
esac
"""


class ListenTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.stub = self.root / "bl"
        self.stub.write_text(STUB, encoding="utf-8")
        self.stub.chmod(self.stub.stat().st_mode | stat.S_IEXEC)
        self.reference = self.root / "reference.mp3"
        self.reference.write_bytes(b"ID3fake")
        self.candidates = []
        entries = []
        for title, marker in (("Good Phonk", "good"), ("Boom Weird", "boom")):
            preview = self.root / f"netease-{marker}-{title}.mp3"
            preview.write_bytes(f"audio-bytes-{marker}".encode())
            self.candidates.append(preview)
            entries.append({"title": title, "neteaseId": marker, "previewPath": str(preview), "durationMs": 30_000})
        self.manifest = self.root / "pool.json"
        self.manifest.write_text(json.dumps({"candidates": entries}), encoding="utf-8")

    def run_script(self, extra=None):
        args = [str(LISTEN), "--reference", str(self.reference), "--manifest", str(self.manifest),
                "--excerpt-sec", "0", "--output", str(self.root / "notes.json")]
        result = subprocess.run([PYTHON, *args, *(extra or [])], capture_output=True, text=True, encoding="utf-8")
        return result

    def test_missing_capability_is_structured_and_never_fabricates(self):
        result = self.run_script(["--bl", str(self.root / "definitely-not-here")])
        self.assertEqual(2, result.returncode)
        payload = json.loads(result.stdout)
        self.assertEqual("blocked", payload["status"])
        self.assertEqual("capability_missing", payload["blockers"][0]["type"])
        echo = (self.root / "BGM-试听笔记回显-v0.1.md").read_text(encoding="utf-8")
        self.assertIn("没有听觉分析能力", echo)
        self.assertNotIn("贴合度", echo)  # 没听过就一个字都不写
        data = json.loads((self.root / "notes.json").read_text(encoding="utf-8"))
        self.assertEqual([], data["tracks"])

    def test_stub_model_writes_one_note_per_heard_track(self):
        result = self.run_script(["--bl", str(self.stub)])
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        data = json.loads((self.root / "notes.json").read_text(encoding="utf-8"))
        self.assertTrue(data["capability"]["available"])
        self.assertEqual("bl 9.9.9-stub", data["capability"]["audioModel"])
        self.assertEqual(1, len(data["tracks"]))  # only the good track was really heard
        self.assertIn("贴合度 8.5", data["tracks"][0]["notes"])

    def test_failed_listen_is_recorded_not_invented(self):
        self.run_script(["--bl", str(self.stub)])
        echo = (self.root / "BGM-试听笔记回显-v0.1.md").read_text(encoding="utf-8")
        self.assertIn("Boom Weird", echo)
        self.assertIn("未获得笔记", echo)
        boom_section = echo.split("## Boom Weird")[1]
        self.assertNotIn("贴合度", boom_section)  # 失败的那首没有任何虚构描述
        data = json.loads((self.root / "notes.json").read_text(encoding="utf-8"))
        self.assertEqual("Boom Weird", data["partialFailures"][0]["title"])


    def test_absolute_library_reuse_is_free_and_only_failures_retry(self):
        lib = self.root / "lib"
        lib.mkdir()
        calls = self.root / "calls.log"
        first = self.run_script(["--bl", str(self.stub), "--absolute", "--library", str(lib)])
        self.assertEqual(0, first.returncode, first.stdout + first.stderr)
        data = json.loads((self.root / "notes.json").read_text(encoding="utf-8"))
        self.assertEqual(1, len(data["tracks"]))
        self.assertFalse(data["tracks"][0]["reused"])
        self.assertEqual(2, calls.read_text().count("call"))  # good 与 boom 各真听一次
        self.run_script(["--bl", str(self.stub), "--absolute", "--library", str(lib)])
        data2 = json.loads((self.root / "notes.json").read_text(encoding="utf-8"))
        self.assertTrue(data2["tracks"][0]["reused"])  # 听过的歌零成本复用档案
        self.assertEqual(1, calls.read_text().count("call") - 2)  # 只有失败的那首重试


if __name__ == "__main__":
    unittest.main()
