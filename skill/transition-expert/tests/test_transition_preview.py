import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[2]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


preview_script = load_script("transition_preview")
directive_script = load_script("transition_directive")


HOST_PROFILE = {"skill": "transition-expert", "purpose": "transition_host_profile",
                "xfade": {"available": True, "transitions": ["fade", "fadeblack"]},
                "capabilities": {"fade": True, "dissolve": True, "wipe": False, "fadeBlackBoundary": True}}


def base_plan() -> dict:
    # 与 test_transition_directive 同夹具：两段叠化+黑场出（深检可过的合法计划）。
    return {
        "projectId": "p", "timelineDurationMs": 13000,
        "segments": [
            {"segmentId": "seg-001", "assetId": "a1", "startMs": 1000, "endMs": 5000,
             "outputStartMs": 0, "outputEndMs": 4000, "narrationStartMs": 200, "narrationEndMs": 3500,
             "transitionInstruction": "叠化", "transitionDurationMs": 500},
            {"segmentId": "seg-002", "assetId": "a2", "startMs": 500, "endMs": 5500,
             "outputStartMs": 4000, "outputEndMs": 9000, "narrationStartMs": 4300, "narrationEndMs": 8500,
             "transitionInstruction": "叠化", "transitionDurationMs": 500},
            {"segmentId": "seg-003", "assetId": "a3", "startMs": 2000, "endMs": 6000,
             "outputStartMs": 9000, "outputEndMs": 13000, "narrationStartMs": 9300, "narrationEndMs": 12000,
             "transitionInstruction": "黑场出", "transitionDurationMs": 800},
        ],
    }


def base_evidence() -> dict:
    return {"sourceEvidence": [
        {"assetId": "a1", "relativePath": "src/a1.mp4", "sha256": "A1", "sourceProbe": {"durationMs": 10000}},
        {"assetId": "a2", "relativePath": "src/a2.mp4", "sha256": "A2", "sourceProbe": {"durationMs": 8000}},
        {"assetId": "a3", "relativePath": "src/a3.mp4", "sha256": "A3", "sourceProbe": {"durationMs": 6000}},
    ]}


def directive_of(plan):
    return directive_script.build_directive(plan, base_evidence(), HOST_PROFILE)


class WindowArithmeticTests(unittest.TestCase):
    """窗口只准取自批准裁切（网格+指令 extras），数字全部钉死。"""

    def test_dissolve_windows_parts_and_join_offsets(self):
        plan = base_plan()
        items = preview_script.build_preview_items(plan, directive_of(plan), 1200)
        self.assertEqual(3, len(items))
        first = items[0]
        self.assertEqual("seg-001→seg-002", first["boundary"])
        self.assertEqual([2550, 5450], first["windowMs"])          # [S−D/2−C, S+D/2+C]
        self.assertEqual(1700, first["clipLenMs"])                 # D+2C 混合后=2900ms 输出
        # from=前段裁剪文件末 (D+C)，to=后段裁剪文件头 (D+C)——都在 extras 之内
        self.assertEqual(3550, first["parts"][0]["startMs"])       # 5000 + tailExtra 250 − 1700
        self.assertEqual(250, first["parts"][1]["startMs"])        # 500 − headExtra 250
        self.assertEqual({"durationMs": 500, "offsetMs": 1200}, first["join"])
        self.assertIsNone(items[2]["join"])
        self.assertEqual({"t": "out", "stMs": 1200, "dMs": 800}, items[2]["fade"])

    def test_context_clamped_by_grid_never_beyond_crop(self):
        plan = base_plan()
        # 重排网格：段一只剩 600ms（原 4000），其后整体前移 3400ms
        plan["segments"][0]["outputEndMs"] = 600
        for seg in plan["segments"][1:]:
            seg["outputStartMs"] -= 3400
            seg["outputEndMs"] -= 3400
        plan["timelineDurationMs"] = 9600
        items = preview_script.build_preview_items(plan, directive_of(plan), 1200)
        first = items[0]
        self.assertEqual(350, first["clipLenMs"] - 500)          # C=min(1200, 600−D/2=350)
        self.assertEqual([0, 1200], first["windowMs"])
        self.assertEqual(850, first["parts"][0]["lenMs"])        # 每侧裁剪头尾 D+C
        self.assertEqual(4400, first["parts"][0]["startMs"])     # 5000+tail 250−850，仍在批准裁切内
        for part in first["parts"]:
            self.assertGreaterEqual(part["startMs"], 0)

    def test_black_out_context_reserves_full_duration(self):
        plan = base_plan()
        plan["segments"][2]["outputEndMs"] = 12200   # 末段网格只剩 3200ms：黑场 800 全额占用
        plan["timelineDurationMs"] = 12200
        items = preview_script.build_preview_items(plan, directive_of(plan), 1200)
        tail = items[-1]
        self.assertEqual("黑场出", tail["type"])
        self.assertEqual(800 + 1200, tail["clipLenMs"])          # min(1200, 3200−800)=1200
        self.assertEqual([12200 - 800 - 1200, 12200], tail["windowMs"])
        self.assertEqual({"t": "out", "stMs": 1200, "dMs": 800}, tail["fade"])


class BlockedPathTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.out = self.root / "预览小样"

    def write(self, name, payload):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def call(self, plan, evidence, host_profile, extra=()):
        # 素材包与占位源文件真实存在且哈希自洽：让对账走到该走的门槛
        # （fps 缺失等），而不是被更早的"源文件缺失"截胡。
        source_assets = []
        for entry in base_evidence()["sourceEvidence"]:
            file_path = self.root / entry["relativePath"]
            file_path.parent.mkdir(parents=True, exist_ok=True)
            if not file_path.exists():
                file_path.write_bytes(entry["assetId"].encode())
            source_assets.append({"assetId": entry["assetId"], "relativePath": entry["relativePath"],
                                  "sha256": hashlib.sha256(file_path.read_bytes()).hexdigest().upper()})
        argv = ["transition_preview.py", "--plan", str(self.write("plan.json", plan)),
                "--evidence", str(self.write("evidence.json", evidence)),
                "--material-pack", str(self.write("material-pack.json", {"sourceAssets": source_assets})),
                "--output-dir", str(self.out)]
        if host_profile is not None:
            argv += ["--host-profile", str(self.write("host.json", host_profile))]
        argv += list(extra)
        stdout = io.StringIO()
        backup = sys.argv
        sys.argv = argv
        try:
            with contextlib.redirect_stdout(stdout):
                try:
                    code = preview_script.main()
                except SystemExit as exit_signal:
                    code = exit_signal.code
        finally:
            sys.argv = backup
        return code, json.loads(stdout.getvalue())

    def test_no_ffmpeg_is_structured_blocked_with_disclosure(self):
        with mock.patch.object(preview_script.shutil, "which", return_value=None):
            code, payload = self.call(base_plan(), base_evidence(), HOST_PROFILE, extra=("--fps", "30"))
        self.assertEqual(2, code)
        self.assertEqual("blocked_previews", payload["status"])
        self.assertIn("未见过的效果", payload["disclosure"])

    def test_validation_failure_blocks_before_render(self):
        plan = base_plan()
        plan["segments"][1]["narrationStartMs"] = 4000   # 窗口 [3750,4250) 压口播
        code, payload = self.call(plan, base_evidence(), HOST_PROFILE, extra=("--fps", "30"))
        self.assertEqual(2, code)
        self.assertEqual("blocked_previews", payload["status"])
        self.assertIn("口播停顿", payload["reason"])
        self.assertFalse(self.out.exists() and any(self.out.iterdir()))

    def test_missing_fps_refused_not_guessed(self):
        code, payload = self.call(base_plan(), base_evidence(), HOST_PROFILE)
        self.assertEqual(2, code)
        self.assertEqual("blocked_previews", payload["status"])
        self.assertIn("fps", payload["reason"])


class LavfiEndToEndTests(unittest.TestCase):
    """真渲染：三色源小片走完整 CLI——时长对账、公式入册、版本自增、无中间件残留。"""

    def setUp(self):
        if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
            self.skipTest("宿主无 ffmpeg：预览本应走 blocked_previews（见 BlockedPathTests）")
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "src").mkdir()
        self.out = self.root / "预览小样"
        durations = {"a1": 10, "a2": 8, "a3": 6}
        colors = {"a1": "red", "a2": "green", "a3": "blue"}
        source_assets = []
        for asset_id, seconds in durations.items():
            path = self.root / "src" / f"{asset_id}.mp4"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                            "-i", f"color=c={colors[asset_id]}:s=320x240:r=30",
                            "-t", str(seconds), "-c:v", "libx264", "-an", str(path)], check=True)
            source_assets.append({"assetId": asset_id, "relativePath": f"src/{asset_id}.mp4",
                                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest().upper()})
        self.pack = self.root / "material-pack.json"
        self.pack.write_text(json.dumps({"sourceAssets": source_assets}, ensure_ascii=False), encoding="utf-8")
        evidence = {"sourceEvidence": [
            {**entry, "sha256": entry["sha256"],
             "sourceProbe": {"durationMs": durations[entry["assetId"]] * 1000}}
            for entry in source_assets]}
        self.evidence = self.root / "evidence.json"
        self.evidence.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")
        self.plan = self.root / "plan.json"
        self.plan.write_text(json.dumps(base_plan(), ensure_ascii=False), encoding="utf-8")
        self.host = self.root / "host.json"
        self.host.write_text(json.dumps(HOST_PROFILE, ensure_ascii=False), encoding="utf-8")

    def run_cli(self):
        stdout = io.StringIO()
        backup = sys.argv
        sys.argv = ["transition_preview.py", "--plan", str(self.plan), "--evidence", str(self.evidence),
                    "--host-profile", str(self.host), "--material-pack", str(self.pack),
                    "--output-dir", str(self.out), "--fps", "30"]
        try:
            with contextlib.redirect_stdout(stdout):
                code = preview_script.main()
        finally:
            sys.argv = backup
        return code, json.loads(stdout.getvalue())

    def test_render_three_clips_manifest_and_parity(self):
        code, payload = self.run_cli()
        self.assertEqual(0, code, payload)
        self.assertEqual(3, payload["previews"])
        manifest = json.loads(Path(payload["manifest"]).read_text(encoding="utf-8"))
        self.assertFalse(manifest["audio"])
        self.assertEqual(hashlib.sha256(self.plan.read_bytes()).hexdigest().upper(), manifest["planSha256"])
        for entry in manifest["previews"]:
            clip = self.out / entry["file"]
            self.assertTrue(clip.exists())
            self.assertEqual(entry["sha256"], hashlib.sha256(clip.read_bytes()).hexdigest().upper())
            # 期望总长=成片窗口跨度（叠化 D+2C / 黑场 D+C），由窗口算术直接推出
            self.assertEqual(entry["windowMs"][1] - entry["windowMs"][0], entry["expectLenMs"])
            self.assertAlmostEqual(entry["expectLenMs"], entry["probedLenMs"], delta=160)
        dissolve = next(e for e in manifest["previews"] if e["type"] == "叠化")
        flat = " ; ".join(" ".join(a) for a in dissolve["renderArgs"])
        # 防幻觉宪法入册：与小样同场留证——公式与成片路径同式（settb ㉒ + xfade fade）
        self.assertIn("settb=AVTB", flat)
        self.assertIn("xfade=transition=fade:duration=0.500:offset=1.200", flat)
        tail = next(e for e in manifest["previews"] if e["type"] == "黑场出")
        self.assertIn("fade=t=out:st=1.200:d=0.800", " ".join(tail["renderArgs"][-1]))
        # 中间件必须清干净（renderArgs 可逐字重建，产物区只留清单+成片小样）
        leftovers = [p.name for p in self.out.iterdir() if "-from." in p.name or "-to." in p.name or "-only." in p.name]
        self.assertEqual([], leftovers)

    def test_viewer_page_generated_and_self_contained(self):
        # 用户 09-23 拍板：卡下统一附一页看全部——观看页与清单同场同版号生成
        code, payload = self.run_cli()
        self.assertEqual(0, code, payload)
        manifest = json.loads(Path(payload["manifest"]).read_text(encoding="utf-8"))
        self.assertEqual("转场-预览观看页-v0.1.html", manifest["viewerPage"])
        page = Path(payload["viewerPage"])
        self.assertTrue(page.exists())
        html = page.read_text(encoding="utf-8")
        for entry in manifest["previews"]:
            self.assertIn(entry["boundary"], html)
            self.assertIn(f'src="{entry["file"]}"', html)  # 裸文件名相对引用（与清单同目录）
        self.assertIn("无声", html)
        self.assertIn(manifest["disclaimer"], html)
        self.assertIn(manifest["planSha256"][:12], html)  # 计划哈希绑定可见：改版即换页

    def test_rerun_increments_manifest_and_keeps_history(self):
        _, first = self.run_cli()
        first_manifest = Path(first["manifest"])
        self.assertEqual("转场-预览清单-v0.1.json", first_manifest.name)
        first_bytes = first_manifest.read_bytes()
        _, second = self.run_cli()
        self.assertEqual("转场-预览清单-v0.2.json", Path(second["manifest"]).name)
        self.assertEqual(first_bytes, first_manifest.read_bytes())  # ㉘ 永不覆盖
        self.assertTrue((self.out / "转场-预览观看页-v0.1.html").exists())   # 旧页留盘作审计
        self.assertTrue((self.out / "转场-预览观看页-v0.2.html").exists())   # 与清单同版号自增

    def test_tampered_source_blocked(self):
        (self.root / "src" / "a2.mp4").write_bytes(b"x")   # 源被改动=哈希失配
        code, payload = self.run_cli()
        self.assertEqual(2, code)
        self.assertEqual("blocked_previews", payload["status"])
        self.assertIn("哈希", payload["reason"])
        self.assertFalse(any(self.out.glob("*.mp4")))


class FormulaParityTests(unittest.TestCase):
    """预览公式 == g4_assemble 成片公式（同仓锁同构；跨仓迁移时如实 skip）。"""

    def test_join_filter_matches_build_video_chain_fragments(self):
        assemble = REPO / "local-video-render" / "scripts" / "g4_assemble.py"
        if not assemble.exists():
            self.skipTest("local-video-render 不在旁（插件独立分发场景）：公式同构由合同与人工复审保证")
        spec = importlib.util.spec_from_file_location("g4_assemble_probe_parity", assemble)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        chain = module.build_video_chain(
            ["[0:v]fps=fps=30,format=yuv420p,setsar=1", "format=yuv420p"], [], [],
            ["a", "b"], {("a", "b"): {"transition": "fade", "durationMs": 500, "offsetMs": 1200}}, 30, True)
        mine = preview_script.xfade_join_filter(30, "0.500", "1.200")
        for fragment in ("[0:v]fps=fps=30,format=yuv420p,setsar=1[segv0]",
                         "[segv0]settb=AVTB[xc0m]", "[segv1]settb=AVTB[xc0s]",
                         "[xc0m][xc0s]xfade=transition=fade:duration=0.500:offset=1.200[vcat0]"):
            self.assertIn(fragment, chain, f"成片链缺片段：{fragment}")
            self.assertIn(fragment, mine, f"预览链缺片段：{fragment}")


if __name__ == "__main__":
    unittest.main()
