import glob
import hashlib
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
            "timelineDurationMs": 2000, "targetFps": 24,
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

    def set_manifest_fps(self, value):
        doc = json.loads(self.manifest.read_text(encoding="utf-8"))
        if value is None:
            doc.pop("targetFps", None)
        else:
            doc["targetFps"] = value
        self.manifest.write_text(json.dumps(doc), encoding="utf-8")

    def read_record(self):
        return json.loads((self.root / "final" / "master-装配记录-v0.1.json").read_text(encoding="utf-8"))

    def test_manifest_without_target_fps_blocks(self):
        # 转场实跑⑧乙（2026-09-24 用户裁决）：default-24 兜底已删除——没有可信帧率=罢工。
        # 旧用例"legacy manifest keeps working at 24"正是 24fps 静默降帧事故的机器化豁免。
        self.set_manifest_fps(None)
        result = self.run_assemble()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("⑧乙", json.loads(result.stdout)["error"])

    def test_fps_inherited_from_manifest_target(self):
        self.set_manifest_fps(30)
        result = self.run_assemble()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        record = self.read_record()
        self.assertEqual(30, record["fps"])
        self.assertEqual("manifest-targetFps", record["fpsSource"])

    def test_explicit_fps_overrides_manifest(self):
        self.set_manifest_fps(30)
        result = self.run_assemble(("--fps", "25"))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        record = self.read_record()
        self.assertEqual(25, record["fps"])
        self.assertEqual("explicit-override", record["fpsSource"])

    def make_bgm_and_contract(self, tamper_hash=False):
        import hashlib
        bgm = self.root / "bgm.wav"
        subprocess.run([self.ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=1", str(bgm)], check=True, capture_output=True)
        sha = hashlib.sha256(bgm.read_bytes()).hexdigest().upper()
        if tamper_hash:
            sha = "F" * 64
        contract = self.root / "mix-contract.json"
        contract.write_text(json.dumps({
            "schemaVersion": "0.1", "skill": "music-expert", "purpose": "bgm_mix_contract", "projectId": "demo-001",
            "bgmAudio": {"path": str(bgm), "sha256": sha}, "evidence": {},
            "timelineMs": 2000, "trackOffsetMs": 0, "bedGainDb": -6.0, "duckReductionDb": 3.0,
            "fades": {"fadeInMs": 200, "fadeOutStartMs": 1800, "fadeOutMs": 200},
            "ducking": [], "duckSegments": [{"fromMs": 0, "toMs": 1900, "sentenceIds": ["N01"]}],
            "mixMode": "duck-table",
        }, ensure_ascii=False), encoding="utf-8")
        return bgm, contract

    def test_burns_subtitles_and_mixes_contract_driven_bgm(self):
        filters = subprocess.run([self.ffmpeg, "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        if " subtitles " not in filters:
            self.skipTest("ffmpeg build lacks the libass subtitles filter")
        bgm, contract = self.make_bgm_and_contract()
        ass = self.root / "captions.ass"
        ass.write_text(CAPTIONS_ASS, encoding="utf-8")
        result = self.run_assemble(("--subtitle-ass", str(ass), "--bgm-audio", str(bgm), "--bgm-mix-contract", str(contract)))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual({"video", "audio"}, self.stream_kinds(self.output))
        summary = json.loads(result.stdout)
        record = json.loads(Path(summary["record"]).read_text(encoding="utf-8"))
        self.assertTrue(record["subtitleAss"]["sha256"])
        self.assertEqual(-6.0, record["bgmMix"]["bedGainDb"])
        self.assertEqual(1, len(record["bgmMix"]["duckSegments"]))
        self.assertTrue(record["bgmMix"]["contract"]["sha256"])
        # the executed graph must carry the contract's ducking automation and fades verbatim
        self.assertIn("volume=-3dB:enable='between(t,0.000,1.900)'", record["filterGraph"])
        self.assertIn("afade=t=in:st=0:d=0.200", record["filterGraph"])
        self.assertIn("afade=t=out:st=1.800:d=0.200", record["filterGraph"])
        # in-place bed level is measured, not assumed (zaku audibility guard)
        self.assertIsNotNone(record["bgmMix"]["measuredInPlaceLufs"])
        self.assertGreater(record["bgmMix"]["measuredInPlaceLufs"], -33.0)

    def test_bgm_without_mix_contract_is_rejected(self):
        bgm, _ = self.make_bgm_and_contract()
        result = self.run_assemble(("--bgm-audio", str(bgm)))
        self.assertNotEqual(0, result.returncode)
        self.assertIn("mix contract", result.stdout)

    def test_bgm_hash_mismatch_with_contract_is_rejected(self):
        bgm, contract = self.make_bgm_and_contract(tamper_hash=True)
        result = self.run_assemble(("--bgm-audio", str(bgm), "--bgm-mix-contract", str(contract)))
        self.assertNotEqual(0, result.returncode)
        self.assertIn("does not match the mix contract", result.stdout)

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

    def make_cover_pack(self):
        # ⑫：封面帧源=登记件。迷你 material-pack：一个真实 1s 视频 + 登记清单。
        pack = self.root / "material-pack"
        raw = pack / "02_原始素材"
        raw.mkdir(parents=True)
        asset = raw / "hero.mp4"
        subprocess.run([self.ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=24", "-t", "1",
                        "-c:v", "libx264", "-an", str(asset)], check=True, capture_output=True)
        digest = hashlib.sha256(asset.read_bytes()).hexdigest().upper()
        (pack / "material-pack.json").write_text(json.dumps(
            {"sourceAssets": [{"assetId": "hero-001", "relativePath": "02_原始素材/hero.mp4", "sha256": digest}]},
            ensure_ascii=False), encoding="utf-8")
        return pack, digest

    def cover_contract(self, pack, extra=None, drop=()):
        payload = {"materialPack": str(pack / "material-pack.json"), "sourceAssetId": "hero-001",
                   "sourceMs": 500, "fontFile": str(self.any_font()), "title": "装配封面测试",
                   "output": str(self.root / "final" / "cover.jpg"), "fontsize": 28}
        for field in drop:
            payload.pop(field, None)
        if extra:
            payload.update(extra)
        contract = self.root / "cover.json"
        contract.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return contract

    def test_cover_is_composited_and_recorded(self):
        # ⑫：帧由装配器从登记件机抽——合同给 assetId+源内毫秒，路径与身份由装配器对账。
        pack, digest = self.make_cover_pack()
        contract = self.cover_contract(pack, extra={"sourceTimelineMs": 500})
        result = self.run_assemble(("--cover", str(contract)))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        cover_out = Path(str(json.loads(result.stdout)["cover"]))
        self.assertTrue(cover_out.is_file() and cover_out.stat().st_size > 0)
        record = json.loads(Path(json.loads(result.stdout)["record"]).read_text(encoding="utf-8"))
        self.assertEqual(str(cover_out.resolve()), record["cover"])
        prov = record["coverProvenance"]
        self.assertEqual("hero-001", prov["sourceAssetId"])
        self.assertEqual(500, prov["sourceMs"])
        self.assertEqual(digest, prov["sourceAssetSha256"])
        self.assertEqual(64, len(prov["frameSha256"]))
        self.assertTrue(Path(prov["framePath"]).is_file())

    def test_cover_rejects_image_path_channel(self):
        pack, digest = self.make_cover_pack()
        contract = self.cover_contract(pack, extra={"imagePath": str(self.root / "ghost.png")})
        result = self.run_assemble(("--cover", str(contract)))
        self.assertNotEqual(0, result.returncode)
        self.assertIn("imagePath", result.stdout)

    def test_cover_requires_source_fields(self):
        pack, digest = self.make_cover_pack()
        for field in ("materialPack", "sourceAssetId", "sourceMs"):
            contract = self.cover_contract(pack, drop=(field,))
            result = self.run_assemble(("--cover", str(contract)))
            self.assertNotEqual(0, result.returncode)
            self.assertIn(field, result.stdout)

    def test_cover_unregistered_asset_rejected(self):
        pack, digest = self.make_cover_pack()
        contract = self.cover_contract(pack, extra={"sourceAssetId": "冷战奇迹-风格参考"})
        result = self.run_assemble(("--cover", str(contract)))
        self.assertNotEqual(0, result.returncode)
        self.assertIn("not a registered asset", result.stdout)

    def test_cover_asset_sha_drift_rejected(self):
        pack, digest = self.make_cover_pack()
        (pack / "material-pack.json").write_text(json.dumps(
            {"sourceAssets": [{"assetId": "hero-001", "relativePath": "02_原始素材/hero.mp4",
                               "sha256": "F" * 64}]}, ensure_ascii=False), encoding="utf-8")
        contract = self.cover_contract(pack)
        result = self.run_assemble(("--cover", str(contract)))
        self.assertNotEqual(0, result.returncode)
        self.assertIn("sha256 mismatch", result.stdout)

    def test_cover_source_ms_outside_asset_rejected(self):
        pack, digest = self.make_cover_pack()
        contract = self.cover_contract(pack, extra={"sourceMs": 99999})
        result = self.run_assemble(("--cover", str(contract)))
        self.assertNotEqual(0, result.returncode)
        self.assertIn("outside registered asset", result.stdout)


    # The ㉛ glyph preflight correctly refuses script-only fonts (e.g. NotoSansLepcha
    # has no Latin/CJK coverage), so "first .ttf on disk" is not a usable test font.
    # Prefer the production-approved covering fonts; glob is only a last resort.
    COVERING_FONT_CANDIDATES = ("/System/Library/Fonts/Supplemental/Songti.ttc",
                                "/System/Library/Fonts/PingFang.ttc")

    def any_font(self):
        for candidate in self.COVERING_FONT_CANDIDATES:
            path = Path(candidate)
            if path.is_file():
                return path
        font = next((Path(c) for p in ("/System/Library/Fonts/Supplemental/*.ttf", "/System/Library/Fonts/*.ttf") for c in glob.glob(p)), None)
        if not font:
            self.skipTest("no TrueType font available for drawtext")
        return font

    def test_chapter_cards_overlay_trims_subtitle_cues(self):
        if " subtitles " not in subprocess.run([self.ffmpeg, "-hide_banner", "-filters"], capture_output=True, text=True).stdout:
            self.skipTest("ffmpeg build lacks the libass subtitles filter")
        ass = self.root / "captions.ass"
        ass.write_text(CAPTIONS_ASS, encoding="utf-8")
        cards = self.root / "cards.json"
        cards.write_text(json.dumps({"fontFile": str(self.any_font()), "fontsize": 20, "yRatio": 0.06, "cards": [
            {"chapterId": "ch-01", "title": "章节卡测试", "startMs": 500, "endMs": 1000},
        ]}, ensure_ascii=False), encoding="utf-8")
        result = self.run_assemble(("--subtitle-ass", str(ass), "--chapter-cards", str(cards)))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        record = json.loads(Path(json.loads(result.stdout)["record"]).read_text(encoding="utf-8"))
        self.assertEqual(1, record["chapterCards"]["cards"])
        self.assertEqual(1, record["chapterCards"]["subtitleCuesTrimmed"])
        # yRatio pins the card to the approved layout contract's title lane instead of centre
        self.assertIn("y=h*0.0600", record["filterGraph"])
        derived = (self.root / "final" / "master-assemble-work" / "captions.ass").read_text(encoding="utf-8")
        dialogues = [line for line in derived.splitlines() if line.startswith("Dialogue:")]
        self.assertEqual(2, len(dialogues))
        self.assertIn("0:00:00.50", dialogues[0])
        self.assertIn("0:00:01.00", dialogues[1])

    def test_chapter_card_beyond_timeline_is_rejected(self):
        cards = self.root / "bad-cards.json"
        cards.write_text(json.dumps({"fontFile": str(self.any_font()), "cards": [
            {"chapterId": "ch-01", "title": "越界卡", "startMs": 1900, "endMs": 2500},
        ]}, ensure_ascii=False), encoding="utf-8")
        result = self.run_assemble(("--chapter-cards", str(cards)))
        self.assertNotEqual(0, result.returncode)
        self.assertIn("exceeds the timeline", result.stdout)

    def test_title_bar_burned_and_recorded(self):
        bar = self.root / "title-bar.json"
        bar.write_text(json.dumps({"fontFile": str(self.any_font()), "text": "NZ-666 KSHATRIYA", "fontsize": 12, "marginPct": 8}, ensure_ascii=False), encoding="utf-8")
        result = self.run_assemble(("--title-bar", str(bar)))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        record = json.loads(Path(json.loads(result.stdout)["record"]).read_text(encoding="utf-8"))
        self.assertEqual("NZ-666 KSHATRIYA", record["titleBar"]["text"])
        self.assertTrue(record["titleBar"]["sha256"])


    # --- 响度接线批三（2026-09-28，丙·分档口径用户拍板）--------------------------------
    # 握手用产物对账：loud_plan 身份头、规划源 sha、三口径镜像（G2 targetProfile ==
    # manifest.loudnessTarget == 执行链参数）；ready 逐字线性、blocked 显式受控 dynamic；
    # 偏差闸在重渲染之前 fail-fast，超差罢工附合同 §5 三成因。

    def loud_plan_doc(self, status="ready", chain="loudnorm=I=-14.0:TP=-1.5:LRA=9.0:measured_I=-22.8:measured_TP=-18.4:measured_LRA=4.1:measured_thresh=-27.0:offset=0.0:linear=true:print_format=json",
                      profile=None, blocked_reasons=None, exits=None, skill="loudness-expert", purpose="loud_plan",
                      project_id="demo-001", sha=None):
        return {
            "skill": skill, "purpose": purpose, "schemaVersion": "0.1", "projectId": project_id,
            "source": str(self.narration), "version": "v0.1", "status": status,
            "targetProfile": profile or {"integratedLufs": -14.0, "truePeakDbtp": -1.5, "lraTargetLu": 9.0},
            "measured": {"engine": "ffmpeg-loudnorm-pass1", "inputI": -22.8, "inputTp": -18.4, "inputLra": 4.1, "inputThresh": -27.0},
            "gainDb": 8.8, "estimatedTruePeak": -9.6, "ceilingLufs": -14.0,
            "blockedReasons": blocked_reasons or [], "exits": exits or [],
            "chain": chain if status == "ready" else None, "chainNote": "…",
            "sha256": sha or hashlib.sha256(self.narration.read_bytes()).hexdigest().upper(),
            "plannedAt": "2026-09-28T00:00:00Z",
        }

    def write_loud_plan(self, doc):
        path = self.root / "loud-plan.json"
        path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        return path

    def set_manifest_loudness(self, value):
        doc = json.loads(self.manifest.read_text(encoding="utf-8"))
        if value is None:
            doc.pop("loudnessTarget", None)
        else:
            doc["loudnessTarget"] = value
        self.manifest.write_text(json.dumps(doc), encoding="utf-8")

    def error_of(self, result):
        # 主处理器 ensure_ascii 打印，中文断言必须先解码，不许拿转义串硬猜。
        return json.loads(result.stdout)["error"]

    def test_loudness_plan_ready_executes_expert_chain_verbatim(self):
        # 正向走真专员 CLI：安静正弦源线性够得着 → ready；节点逐字执行、闸按纯口播落账。
        quiet = self.root / "quiet-narration.wav"
        subprocess.run([self.ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2,volume=-20dB", str(quiet)],
                       check=True, capture_output=True)
        expert = ROOT / "skill/loudness-expert/scripts/loud_plan.py"
        plan_run = subprocess.run([PYTHON, str(expert), "--input", str(quiet), "--output-dir", str(self.root / "loud-plans"),
                                   "--profile", "video", "--project-id", "demo-001"],
                                  capture_output=True, text=True, encoding="utf-8")
        if not plan_run.stdout.strip() or json.loads(plan_run.stdout).get("status") not in ("ready",):
            self.skipTest("fixture source is not linear-feasible on this ffmpeg: " + plan_run.stdout)
        plan = json.loads(plan_run.stdout)
        self.narration = quiet
        self.set_manifest_loudness(plan["targetProfile"])
        result = self.run_assemble(("--loudness-plan", str(plan["output"])))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        record = self.read_record()
        loud = record["loudness"]
        self.assertEqual("linear-verbatim", loud["mode"])
        self.assertEqual("ready", loud["planStatus"])
        self.assertIn(plan["chain"], record["filterGraph"])
        self.assertEqual(plan["targetProfile"], loud["targetProfile"])
        self.assertTrue(loud["planRef"]["sha256"])
        self.assertLessEqual(abs(loud["pureNarration"]["deviationLu"]), loud["pureNarration"]["toleranceLu"])
        self.assertEqual("合同 §3 默认", loud["pureNarration"]["toleranceSource"])
        self.assertIsNotNone(loud["loudnormStats"])
        self.assertEqual(-14.0, record["narrationAudio"]["loudness"]["targetIntegratedLufs"])

    def test_loudness_plan_blocked_runs_controlled_dynamic_with_profile_numbers(self):
        # blocked → 显式受控 dynamic：标准压缩链按目标档三参数展开（podcast −16/−2/7
        # 活证不许节点硬编码 video 常量），stats 强制落账。
        doc = self.loud_plan_doc(status="blocked_true-peak",
                                 profile={"integratedLufs": -16.0, "truePeakDbtp": -2.0, "lraTargetLu": 7.0},
                                 blocked_reasons=["true-peak"], exits=["把 TP 上限提到至少 −0.5 dBTP"])
        self.set_manifest_loudness(doc["targetProfile"])
        result = self.run_assemble(("--loudness-plan", str(self.write_loud_plan(doc))))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        record = self.read_record()
        loud = record["loudness"]
        self.assertEqual("controlled-dynamic", loud["mode"])
        self.assertEqual("blocked_true-peak", loud["planStatus"])
        self.assertIn("acompressor", record["filterGraph"])
        self.assertIn("loudnorm=I=-16", record["filterGraph"])
        self.assertIn(":TP=-2", record["filterGraph"])
        self.assertIn(":LRA=7:print_format=json", record["filterGraph"])
        self.assertIsNotNone(loud["loudnormStats"])
        # blocked 档落点两态皆合法：够得着=within-tolerance，够不着=disclosed-exceedance+摊开注记。
        pure = loud["pureNarration"]
        self.assertIn(pure["verdict"], ("within-tolerance", "disclosed-exceedance"))
        if pure["verdict"] == "disclosed-exceedance":
            self.assertIn("永不静默", pure["reviewNote"])

    def test_loudness_tolerance_override_recorded(self):
        doc = self.loud_plan_doc(status="blocked_true-peak")
        self.set_manifest_loudness(doc["targetProfile"])
        result = self.run_assemble(("--loudness-plan", str(self.write_loud_plan(doc)), "--loudness-tolerance-lu", "5"))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        pure = self.read_record()["loudness"]["pureNarration"]
        self.assertEqual(5.0, pure["toleranceLu"])
        self.assertEqual("CLI 显式覆盖", pure["toleranceSource"])

    def test_loudness_plan_foreign_header_is_refused(self):
        doc = self.loud_plan_doc(skill="music-expert")
        self.set_manifest_loudness(doc["targetProfile"])
        result = self.run_assemble(("--loudness-plan", str(self.write_loud_plan(doc))))
        self.assertEqual(2, result.returncode)
        self.assertIn("loud_plan", self.error_of(result))

    def test_loudness_plan_source_sha_drift_is_refused(self):
        # R2 同型延伸+台账⑬：换配音/放置轨进装配=计划失效罢工；
        # 文案两情形指路——先对放置轨重跑 loud_plan，逐字一致不回 G2、有变才回 G2。
        doc = self.loud_plan_doc(sha="F" * 64)
        self.set_manifest_loudness(doc["targetProfile"])
        result = self.run_assemble(("--loudness-plan", str(self.write_loud_plan(doc))))
        self.assertEqual(2, result.returncode)
        err = self.error_of(result)
        self.assertIn("规划源", err)
        self.assertIn("重跑 loud_plan", err)   # ⑬：第一拍=对放置轨重规划，非条件反射回 G2
        self.assertIn("不回 G2", err)          # ⑬：决定输入未变情形的出路必须点名
        self.assertIn("决定输入", err)         # ⑬：回 G2 仅限"任何一项变了"

    def test_loudness_plan_mirror_mismatch_is_refused(self):
        doc = self.loud_plan_doc()
        self.set_manifest_loudness({"integratedLufs": -16.0, "truePeakDbtp": -1.5, "lraTargetLu": 9.0})
        result = self.run_assemble(("--loudness-plan", str(self.write_loud_plan(doc))))
        self.assertEqual(2, result.returncode)
        self.assertIn("三口径对账", self.error_of(result))

    def test_loudness_plan_without_manifest_mirror_is_refused(self):
        doc = self.loud_plan_doc()
        self.set_manifest_loudness(None)
        result = self.run_assemble(("--loudness-plan", str(self.write_loud_plan(doc))))
        self.assertEqual(2, result.returncode)
        self.assertIn("loudnessTarget 镜像", self.error_of(result))

    def test_loudness_plan_cross_project_artifact_is_refused(self):
        doc = self.loud_plan_doc(project_id="zaku-intro-001")
        self.set_manifest_loudness(doc["targetProfile"])
        result = self.run_assemble(("--loudness-plan", str(self.write_loud_plan(doc))))
        self.assertEqual(2, result.returncode)
        self.assertIn("串项目", self.error_of(result))

    def test_loudness_plan_and_legacy_flag_are_mutually_exclusive(self):
        doc = self.loud_plan_doc()
        self.set_manifest_loudness(doc["targetProfile"])
        result = self.run_assemble(("--loudness-plan", str(self.write_loud_plan(doc)), "--normalize-narration-lufs", "-14"))
        self.assertEqual(2, result.returncode)
        self.assertIn("二选一", self.error_of(result))

    def test_normalize_narration_records_measured_loudness(self):
        result = self.run_assemble(("--normalize-narration-lufs", "-16"))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        record = json.loads(Path(json.loads(result.stdout)["record"]).read_text(encoding="utf-8"))
        self.assertIn("acompressor", record["filterGraph"])
        self.assertIn("[narr]", record["filterGraph"])
        loudness = record["narrationAudio"]["loudness"]
        self.assertEqual(-16.0, loudness["targetIntegratedLufs"])
        self.assertIsNotNone(loudness["integratedLufs"])  # measured post-render, never assumed
        self.assertIn("standard-narration-chain", loudness["chain"])

    def test_normalize_narration_rejects_out_of_range_target(self):
        result = self.run_assemble(("--normalize-narration-lufs", "-3"))
        self.assertNotEqual(0, result.returncode)
        self.assertIn("-24 and -8", result.stdout + result.stderr)

    # --- xfade 链实装（transition-expert 指令经 prepare 透传）。夹具：两个 1000ms
    # 段文件 + 2s 口播。网格 750+750、边界 D=500 ⇒ 段文件恰为网格+250 手柄的扩切
    # 产物，成片总长必须仍是 1500——重叠掉的就是手柄，网格零位移是本批宪法验收。

    def bind(self, segments_grid, boundary_offset):
        import hashlib
        directive = {"schemaVersion": "0.1", "skill": "transition-expert", "purpose": "transition_directive",
                     "gridInvariant": True, "timelineDurationMs": sum(segments_grid),
                     "segments": [{"segmentId": "s1", "headExtraMs": 0, "tailExtraMs": 250},
                                  {"segmentId": "s2", "headExtraMs": 250, "tailExtraMs": 0}],
                     "boundaries": [{"fromSegmentId": "s1", "toSegmentId": "s2", "transition": "dissolve",
                                     "durationMs": 500, "offsetMs": boundary_offset}],
                     "masterFades": {"fadeInMs": 0, "fadeOutMs": 400}}
        directive_path = self.root / "directive.json"
        directive_path.write_text(json.dumps(directive, ensure_ascii=False), encoding="utf-8")
        digest = hashlib.sha256(directive_path.read_bytes()).hexdigest().upper()
        self.manifest.write_text(json.dumps({
            "schemaVersion": "0.2", "node": "G4", "projectId": "demo-001", "status": "prepared_for_render",
            "timelineDurationMs": sum(segments_grid), "targetFps": 24,
            "segments": [
                {"segmentId": "s1", "order": 1, "timeline": {"startMs": 0, "endMs": segments_grid[0]},
                 "transition": {"headExtraMs": 0, "tailExtraMs": 250}, "output": {"filename": "seg-001.mp4"}},
                {"segmentId": "s2", "order": 2, "timeline": {"startMs": segments_grid[0], "endMs": sum(segments_grid)},
                 "transition": {"headExtraMs": 250, "tailExtraMs": 0}, "output": {"filename": "seg-002.mp4"}},
            ],
            "transitionDirective": {"path": str(directive_path), "sha256": digest, "boundaries": 1,
                                    "masterFades": {"fadeInMs": 0, "fadeOutMs": 400}},
        }), encoding="utf-8")

    def rehash_directive_registration(self):
        import hashlib
        doc = json.loads(self.manifest.read_text(encoding="utf-8"))
        doc["transitionDirective"]["sha256"] = hashlib.sha256((self.root / "directive.json").read_bytes()).hexdigest().upper()
        self.manifest.write_text(json.dumps(doc), encoding="utf-8")

    def test_golden_xfade_master_keeps_grid_and_records_execution(self):
        self.bind([750, 750], 500)
        result = self.run_assemble()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        record = json.loads(Path(json.loads(result.stdout)["record"]).read_text(encoding="utf-8"))
        # 1000+1000 段文件重叠 500 ⇒ 成片恰好等于批准网格 1500：手柄回填模型成立。
        self.assertLessEqual(abs(record["probedDurationMs"] - 1500), 400)
        self.assertIn("xfade=transition=dissolve:duration=0.500:offset=0.500", record["filterGraph"])
        self.assertIn("fade=t=out:st=1.100:d=0.400", record["filterGraph"])
        self.assertEqual({"fadeInMs": 0, "fadeOutMs": 400}, record["transitionDirective"]["masterFades"])
        self.assertEqual({"video", "audio"}, self.stream_kinds(self.output))

    def test_stale_directive_registration_is_refused(self):
        self.bind([750, 750], 500)
        doc = json.loads(self.manifest.read_text(encoding="utf-8"))
        doc["transitionDirective"]["sha256"] = "F" * 64
        self.manifest.write_text(json.dumps(doc), encoding="utf-8")
        result = self.run_assemble()
        self.assertEqual(2, result.returncode)
        self.assertIn("drifted", result.stdout + result.stderr)

    def test_unextended_segment_file_is_refused_not_silently_retried(self):
        # 网格按 1000+1000 但段文件没扩手柄：期望 1250 实得 1000 → 拒办并指回 g4_render。
        self.bind([1000, 1000], 750)
        result = self.run_assemble()
        self.assertEqual(2, result.returncode)
        joined = result.stdout + result.stderr
        # 错误 JSON 走 ensure_ascii，中文以转义形式出现：断言 ASCII 骨架 + g4_render 指路。
        self.assertIn("rendered file 1000ms", joined)
        self.assertIn("g4_render", joined)

    def test_long_chain_xfade_midway_timebase_regression(self):
        # Issue ㉒（sinjuku 27 段实片引爆）：xfade 落在长链中段时，main 输入=concat 输出
        # （tb=1/1000000）、side 输入=单段 fps 输出（tb=1/30），ffmpeg 7.0 直接拒绝。
        # 批②冒烟的 2 段夹具两侧都是 fps 直出、测不出来——本例补盲区：6 段链、叠化在第 3 边界。
        for index in range(3, 7):
            subprocess.run([self.ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=red:s=320x240:r=24", "-t", "1",
                            "-c:v", "libx264", "-an", str(self.segments / f"seg-{index:03d}.mp4")],
                           check=True, capture_output=True)
        narration = self.root / "long-narration.wav"
        subprocess.run([self.ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=6", str(narration)],
                       check=True, capture_output=True)
        grids = [1000, 1000, 750, 750, 1000, 1000]
        extras = [(0, 0), (0, 0), (0, 250), (250, 0), (0, 0), (0, 0)]
        segments, start = [], 0
        for index, grid in enumerate(grids, 1):
            segments.append({"segmentId": f"s{index}", "order": index,
                             "timeline": {"startMs": start, "endMs": start + grid},
                             "transition": {"headExtraMs": extras[index - 1][0], "tailExtraMs": extras[index - 1][1]},
                             "output": {"filename": f"seg-{index:03d}.mp4"}})
            start += grid
        directive = {"schemaVersion": "0.1", "skill": "transition-expert", "purpose": "transition_directive",
                     "gridInvariant": True, "timelineDurationMs": 5500,
                     "segments": [{"segmentId": f"s{index}", "headExtraMs": head, "tailExtraMs": tail}
                                  for index, (head, tail) in enumerate(extras, 1)],
                     "boundaries": [{"fromSegmentId": "s3", "toSegmentId": "s4", "transition": "fade",
                                     "durationMs": 500, "offsetMs": 2500}],
                     "masterFades": {"fadeInMs": 0, "fadeOutMs": 0}}
        directive_path = self.root / "directive.json"
        directive_path.write_text(json.dumps(directive, ensure_ascii=False), encoding="utf-8")
        digest = hashlib.sha256(directive_path.read_bytes()).hexdigest().upper()
        self.manifest.write_text(json.dumps({
            "schemaVersion": "0.2", "node": "G4", "projectId": "demo-001", "status": "prepared_for_render",
            "timelineDurationMs": 5500, "targetFps": 24, "segments": segments,
            "transitionDirective": {"path": str(directive_path), "sha256": digest, "boundaries": 1,
                                    "masterFades": {"fadeInMs": 0, "fadeOutMs": 0}},
        }), encoding="utf-8")
        result = subprocess.run(
            [PYTHON, str(SCRIPT), "--manifest", str(self.manifest), "--segments-dir", str(self.segments),
             "--narration-audio", str(narration), "--output", str(self.output)],
            capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        record = json.loads(Path(json.loads(result.stdout)["record"]).read_text(encoding="utf-8"))
        self.assertIn("settb=AVTB", record["filterGraph"])
        self.assertIn("xfade=transition=fade:duration=0.500:offset=2.500", record["filterGraph"])
        self.assertLessEqual(abs(record["probedDurationMs"] - 5500), 400)

    def test_directive_grid_mismatch_is_refused(self):
        self.bind([750, 750], 500)
        directive = json.loads((self.root / "directive.json").read_text(encoding="utf-8"))
        directive["timelineDurationMs"] = 9999
        (self.root / "directive.json").write_text(json.dumps(directive), encoding="utf-8")
        self.rehash_directive_registration()
        result = self.run_assemble()
        self.assertEqual(2, result.returncode)
        self.assertIn("grid", result.stdout + result.stderr)


class VideoChainGraphTests(unittest.TestCase):
    """㉒ 单元层（零 ffmpeg 依赖）：build_video_chain 的 filter 图形状合同。"""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location("g4_assemble_under_test", SCRIPT)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_xfade_junction_wraps_both_inputs_with_settb(self):
        ids = [f"seg-{index:02d}" for index in range(1, 9)]
        boundary = {"fromSegmentId": "seg-04", "toSegmentId": "seg-05",
                    "transition": "fade", "durationMs": 400, "offsetMs": 4600}
        graph = self.module.build_video_chain(["[base]"], [], [], ids,
                                              {("seg-04", "seg-05"): boundary}, 30, True)
        self.assertEqual(2, graph.count("settb=AVTB"), "xfade 两侧输入都必须先过 settb")
        self.assertIn("xfade=transition=fade:duration=0.400:offset=4.600", graph)
        self.assertEqual(6, graph.count("concat=n=2:v=1:a=0"), "非转场边界保持 concat 硬切")

    def test_no_transition_path_untouched_by_settb(self):
        # 无转场项目逐字节不变是红线：legacy 路径不得混入任何 xfade/settb 痕迹。
        graph = self.module.build_video_chain(["[0:v]", "[1:v]"], [], [], ["a", "b"], {}, 30, False)
        self.assertNotIn("settb", graph)
        self.assertNotIn("xfade", graph)


class LoudnessWiringUnitTests(unittest.TestCase):
    """批三单元层（零 ffmpeg 依赖）：偏差闸算术、分档链展开、口径解析纯函数。"""

    PROFILE = {"integratedLufs": -14.0, "truePeakDbtp": -1.5, "lraTargetLu": 9.0}

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location("g4_assemble_loudness_under_test", SCRIPT)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def gate(self, integrated, true_peak, tolerance=1.0, strict=True):
        return self.module.loudness_deviation_gate(
            {"integratedLufs": integrated, "truePeakDbtp": true_peak, "engine": "ffmpeg-ebur128"},
            self.PROFILE, tolerance, "测试口径", strict)

    def test_gate_passes_within_tolerance_and_tp_slack(self):
        verdict = self.gate(-14.9, -1.7)
        self.assertAlmostEqual(-0.9, verdict["deviationLu"])
        self.assertEqual("within-tolerance", verdict["verdict"])
        self.assertEqual(1.0, verdict["toleranceLu"])
        self.assertEqual("测试口径", verdict["toleranceSource"])

    def test_blocked_tier_discloses_exceedance_instead_of_striking(self):
        # 长天彩排实数：高峰均比 TTS 源受控动态落点 −15.6 对目标 −14，超差 1.6 LU——
        # blocked 档如实落账交人工确认（丙口径分档语义），罢工=一切真项目永久卡死=假闸。
        verdict = self.gate(-15.6, -1.7, strict=False)
        self.assertEqual("disclosed-exceedance", verdict["verdict"])
        # TP 超差是两档共同硬闸（限幅链路坏≠响度取舍），不随 strict 豁免。
        with self.assertRaises(ValueError):
            self.gate(-15.6, -1.1, strict=False)

    def test_gate_strikes_over_tolerance_with_three_causes(self):
        with self.assertRaises(ValueError) as caught:
            self.gate(-15.15, -1.7)
        message = str(caught.exception)
        self.assertIn("超容差", message)
        for cause in ("源天花板", "混音口径", "回退/链漂移"):
            self.assertIn(cause, message)

    def test_gate_strikes_when_tp_beyond_slack(self):
        with self.assertRaises(ValueError) as caught:
            self.gate(-14.0, -1.1)  # 超上限 0.4 dB，余量只许 0.3
        self.assertIn("dBTP", str(caught.exception))

    def test_gate_strikes_without_reading_never_assumes(self):
        with self.assertRaises(ValueError) as caught:
            self.gate(None, -1.7)
        self.assertIn("罢工", str(caught.exception))

    def test_chain_selection_is_tiered_by_plan_status(self):
        verbatim = self.module.narration_chain_from_plan({"status": "ready", "chain": "loudnorm=X:linear=true", "targetProfile": self.PROFILE})
        self.assertEqual(("loudnorm=X:linear=true", "linear-verbatim"), verbatim)
        chain, mode = self.module.narration_chain_from_plan(
            {"status": "blocked_true-peak", "chain": None,
             "targetProfile": {"integratedLufs": -16.0, "truePeakDbtp": -2.0, "lraTargetLu": 7.0}})
        self.assertEqual("controlled-dynamic", mode)
        self.assertIn("acompressor", chain)
        self.assertIn("loudnorm=I=-16", chain)
        self.assertIn(":TP=-2:LRA=7:print_format=json", chain)

    def test_parse_helpers_take_last_block_and_reject_sentinels(self):
        parsed = self.module.parse_ebur128_summary("I: -69.9 LUFS ... junk\nI: -14.2 LUFS\nTrue peak:\n Peak: -1.8 dBFS")
        self.assertEqual(-14.2, parsed["integratedLufs"])
        self.assertEqual(-1.8, parsed["truePeakDbtp"])
        self.assertIsNone(self.module.parse_ebur128_summary("I: -70.0 LUFS")["integratedLufs"])
        stats = self.module.parse_loudnorm_stats('noise {"input_i": -22.8, "target_i": -14.0} tail')
        self.assertEqual(-22.8, stats["input_i"])
        self.assertIsNone(self.module.parse_loudnorm_stats("no json here"))


if __name__ == "__main__":
    unittest.main()
