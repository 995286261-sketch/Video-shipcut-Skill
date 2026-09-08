import glob
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skill/local-video-render/scripts/g4_assemble.py"
PYTHON = sys.executable

CAPTIONS_ASS = """[Script Info]
ScriptType: v4.00+
PlayResX: 320
PlayResY: 240
WrapStyle: 1

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: NarrMain,PingFang SC,14,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,1,0,2,20,20,58,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:01.90,NarrMain,,0,0,0,,装配测试字幕。
"""


class G4AssembleTests(unittest.TestCase):
    def setUp(self):
        self.ffmpeg = shutil.which("ffmpeg")
        self.ffprobe = shutil.which("ffprobe")
        if not self.ffmpeg or not self.ffprobe:
            self.skipTest("ffmpeg and ffprobe are required")
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.segments = self.root / "clean-segments"
        self.segments.mkdir()
        for name, color in (("seg-001.mp4", "green"), ("seg-002.mp4", "blue")):
            subprocess.run(
                [self.ffmpeg, "-y", "-f", "lavfi", "-i", f"color=c={color}:s=320x240:r=24", "-t", "1", "-c:v", "libx264", "-an", str(self.segments / name)],
                check=True, capture_output=True,
            )
        self.narration = self.root / "narration.wav"
        subprocess.run([self.ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(self.narration)], check=True, capture_output=True)
        self.manifest = self.root / "manifest.json"
        self.manifest.write_text(json.dumps({
            "schemaVersion": "0.2", "node": "G4", "projectId": "demo-001", "status": "prepared_for_render",
            "timelineDurationMs": 2000,
            "segments": [
                {"segmentId": "s1", "order": 1, "timeline": {"startMs": 0, "endMs": 1000}, "output": {"filename": "seg-001.mp4"}},
                {"segmentId": "s2", "order": 2, "timeline": {"startMs": 1000, "endMs": 2000}, "output": {"filename": "seg-002.mp4"}},
            ],
        }), encoding="utf-8")
        self.output = self.root / "final" / "master.mp4"

    def tearDown(self):
        self.temp.cleanup()

    def run_assemble(self, extra=()):
        return subprocess.run(
            [PYTHON, str(SCRIPT), "--manifest", str(self.manifest), "--segments-dir", str(self.segments),
             "--narration-audio", str(self.narration), "--output", str(self.output), *extra],
            capture_output=True, text=True, encoding="utf-8",
        )

    def stream_kinds(self, path):
        probe = subprocess.run([self.ffprobe, "-v", "error", "-show_entries", "stream=codec_type", "-of", "json", str(path)], capture_output=True, text=True, check=True)
        return {stream["codec_type"] for stream in json.loads(probe.stdout)["streams"]}

    def test_assembles_video_and_narration_with_record(self):
        result = self.run_assemble()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertTrue(self.output.is_file() and self.output.stat().st_size > 0)
        self.assertEqual({"video", "audio"}, self.stream_kinds(self.output))
        record = json.loads((self.root / "final" / "master-装配记录-v0.1.json").read_text(encoding="utf-8"))
        self.assertEqual("assembled", record["status"])
        self.assertEqual(2, len(record["segments"]))
        self.assertTrue(record["outputSha256"])
        self.assertEqual(2000, record["timelineDurationMs"])

    def test_burns_subtitles_and_mixes_ducked_bgm(self):
        filters = subprocess.run([self.ffmpeg, "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        if " subtitles " not in filters:
            self.skipTest("ffmpeg build lacks the libass subtitles filter")
        bgm = self.root / "bgm.wav"
        subprocess.run([self.ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=1", str(bgm)], check=True, capture_output=True)
        ass = self.root / "captions.ass"
        ass.write_text(CAPTIONS_ASS, encoding="utf-8")
        result = self.run_assemble(("--subtitle-ass", str(ass), "--bgm-audio", str(bgm), "--bgm-duck"))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual({"video", "audio"}, self.stream_kinds(self.output))
        summary = json.loads(result.stdout)
        record = json.loads(Path(summary["record"]).read_text(encoding="utf-8"))
        self.assertTrue(record["subtitleAss"]["sha256"])
        self.assertTrue(record["bgmAudio"]["ducked"])

    def test_missing_segment_is_rejected(self):
        (self.segments / "seg-002.mp4").unlink()
        result = self.run_assemble()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("rendered segment is missing or empty", result.stdout)

    def test_short_narration_is_rejected(self):
        short = self.root / "short.wav"
        subprocess.run([self.ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5", str(short)], check=True, capture_output=True)
        self.narration = short
        result = self.run_assemble()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("shorter than the timeline", result.stdout)

    def test_cover_is_composited_and_recorded(self):
        font = next((Path(candidate) for pattern in ("/System/Library/Fonts/Supplemental/*.ttf", "/System/Library/Fonts/*.ttf") for candidate in glob.glob(pattern)), None)
        if not font:
            self.skipTest("no TrueType font available for drawtext")
        image = self.root / "cover-source.png"
        subprocess.run([self.ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=gray:s=320x240", "-frames:v", "1", str(image)], check=True, capture_output=True)
        cover_out = self.root / "final" / "cover.jpg"
        contract = self.root / "cover.json"
        contract.write_text(json.dumps({"imagePath": str(image), "fontFile": str(font), "title": "装配封面测试", "output": str(cover_out), "fontsize": 28}, ensure_ascii=False), encoding="utf-8")
        result = self.run_assemble(("--cover", str(contract)))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertTrue(cover_out.is_file() and cover_out.stat().st_size > 0)
        record = json.loads(Path(json.loads(result.stdout)["record"]).read_text(encoding="utf-8"))
        self.assertEqual(str(cover_out.resolve()), record["cover"])


if __name__ == "__main__":
    unittest.main()
