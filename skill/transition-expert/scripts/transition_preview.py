#!/usr/bin/env python3
"""G3 转场试装预览：批准前，从源素材实渲染每个转场边界的低清无声小样。

防幻觉宪法（用户 2026-09-23 批准方案）：预览不新写一套"长得像"的效果。
- 门槛与算术全部复用既有代码：先跑 transition_validate_plan.validate_plan
  （不过检=blocked，与 directive 同门槛），再用 transition_directive.build_directive
  拿完全相同的 extras/boundaries/masterFades——所见即所批由同一入口保证。
- 滤镜公式与 G4 成片路径同式：g4_render 的裁剪/缩放链、g4_assemble
  build_video_chain 的 xfade/settb 段、fade_layers 的黑场公式在此原样内联——
  跨专员零 import 是插件四标准，故公式为"故意同式复制"，由
  tests/test_transition_preview.py::FormulaParityTests 逐片段断言与
  g4_assemble 模板一致（同 TRANSITION_MODES / next_versioned_path 先例）。
- 窗口纪律：小样只取 [S−D/2−C, S+D/2+C]，C=min(context, 两侧成片段长−D/2)——
  永不展示批准裁切之外的画面；手柄刚好=D/2 时小样即 D 长的混合窗本身。
- 纯画面无声（卡上如实声明）；缺 ffmpeg/素材 sha 变更 → 结构化
  blocked_previews + 披露句，供编排如实上卡（硬门禁唯一豁免，不许静默跳卡）。
产物：《转场-预览清单-v<M.N>.json》（next_versioned_path 自增、永不覆盖，㉘）
逐条绑定渲染 argv 原样与成片哈希，杜绝"当年怎么生成的没人知道"（09-22 手工
小样无记录的教训）。源素材只读。
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

VALIDATOR = Path(__file__).with_name("transition_validate_plan.py")
DIRECTIVE = Path(__file__).with_name("transition_directive.py")
MANIFEST_PREFIX = "转场-预览清单"
VIEWER_PREFIX = "转场-预览观看页"
CLIP_PREFIX = "转场预览"
CONTEXT_MS = 1200        # 上下文秒数上限（用户裁决：约两秒低清小样）
PREVIEW_WIDTH = 854      # 降分辨率不改混合语义（观感由 xfade 公式决定）
PREVIEW_CRF = "28"       # 草稿档；成片仍是 crf 20
DISCLOSURE = "本机无法生成预览：你批准的是未见过的效果（原因见 reason）"


def next_versioned_path(output_dir: Path, prefix: str) -> Path:
    """产物版本自动递增、永不覆盖（issue ㉘）；旧产物留盘作审计。
    （与 transition_directive/transition_probe_host 故意重复此 10 行——专员脚本
    保持零依赖单文件，同 LAYOUT_TIERS 双文件模式。）"""
    import re
    pattern = re.compile(rf"^{re.escape(prefix)}-v(\d+)\.(\d+)\.json$")
    best = (0, 0)
    for candidate in output_dir.glob(prefix + "-v*.json"):
        match = pattern.match(candidate.name)
        if match:
            best = max(best, (int(match.group(1)), int(match.group(2))))
    if best == (0, 0):
        return output_dir / f"{prefix}-v0.1.json"
    return output_dir / f"{prefix}-v{best[0]}.{best[1] + 1}.json"


def load_sibling(name: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def probe_source_size(binary: str, path: Path):
    """ffprobe 首个视频流宽高（同 g4_render.probe_canvas 立场：量出来的，不猜）。"""
    result = subprocess.run(
        [binary, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", str(path)],
        capture_output=True, text=True, check=True)
    stream = (json.loads(result.stdout).get("streams") or [{}])[0]
    width, height = stream.get("width"), stream.get("height")
    if not width or not height:
        raise ValueError(f"无法探测源画面尺寸：{path.name}（能力可以缺、事实不能编）")
    return int(width), int(height)


def probe_duration_ms(binary: str, path: Path) -> int:
    result = subprocess.run(
        [binary, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True)
    return round(float(json.loads(result.stdout)["format"]["duration"]) * 1000)


# ---- 滤镜公式：与 G4 成片路径同式（故意复制，FormulaParityTests 锁同构） ----

def render_vf(preview_w: int, preview_h: int, fps: int, crop_bottom_ratio: float = 0.0) -> str:
    """g4_render L146-149 同形：crop（可选）→scale→pad→setsar→fps。"""
    crop = f"crop=iw:trunc(ih*{1 - crop_bottom_ratio}):0:0," if crop_bottom_ratio else ""
    return (crop + f"scale={preview_w}:{preview_h}:force_original_aspect_ratio=decrease,"
            f"pad={preview_w}:{preview_h}:(ow-iw)/2:(oh-ih)/2:color=0x101418,setsar=1,fps={fps}")


def xfade_join_filter(fps: int, duration_s: str, offset_s: str) -> str:
    """g4_assemble.build_video_chain L180-202 的单元形状：逐输入 fps/format/setsar
    统一 → junction 两侧 settb=AVTB（㉒）→ xfade。"""
    return ("[0:v]fps=fps={fps},format=yuv420p,setsar=1[segv0];"
            "[1:v]fps=fps={fps},format=yuv420p,setsar=1[segv1];"
            "[segv0]settb=AVTB[xc0m];[segv1]settb=AVTB[xc0s];"
            "[xc0m][xc0s]xfade=transition=fade:duration={d}:offset={o}[vcat0];"
            "[vcat0]format=yuv420p[v]").format(fps=fps, d=duration_s, o=offset_s)


def black_fade_filter(fade: str, st_s: str, d_s: str) -> str:
    """g4_assemble L548-554 fade_layers 同式：fade=t=in/out:st=…:d=…。"""
    return f"fade=t={fade}:st={st_s}:d={d_s}"


# ---- 窗口算术：输入全部来自 build_directive 的产物，不另起炉灶 ----

def build_preview_items(plan: dict, directive: dict, context_ms: int) -> list:
    ordered = sorted(plan["segments"], key=lambda s: s.get("outputStartMs", 0))
    grid = {s["segmentId"]: s for s in ordered}
    extras = {e["segmentId"]: e for e in directive["segments"]}

    def context_of(seg_id: str, duration_ms: int) -> int:
        seg = grid[seg_id]
        room = (seg["outputEndMs"] - seg["outputStartMs"]) - duration_ms // 2
        return max(0, min(context_ms, room))

    items = []
    for boundary in directive["boundaries"]:
        a, b = boundary["fromSegmentId"], boundary["toSegmentId"]
        duration = int(boundary["durationMs"])
        seg_a, seg_b = grid[a], grid[b]
        context = min(context_of(a, duration), context_of(b, duration))
        half = duration // 2
        clip_len = duration + context
        window = [seg_a["outputEndMs"] - half - context, seg_a["outputEndMs"] + (duration - half) + context]
        a_src = seg_a["startMs"] if isinstance(seg_a.get("startMs"), int) else seg_a["source"]["startMs"]
        a_end = seg_a["endMs"] if isinstance(seg_a.get("endMs"), int) else seg_a["source"]["endMs"]
        b_src = seg_b["startMs"] if isinstance(seg_b.get("startMs"), int) else seg_b["source"]["startMs"]
        b_end = seg_b["endMs"] if isinstance(seg_b.get("endMs"), int) else seg_b["source"]["endMs"]
        items.append({
            "boundary": f"{a}→{b}", "type": "叠化", "durationMs": duration,
            "windowMs": window, "clipLenMs": clip_len,
            "parts": [
                {"role": "from", "assetId": seg_a["assetId"],
                 "startMs": a_end + extras[a]["tailExtraMs"] - clip_len, "lenMs": clip_len},
                {"role": "to", "assetId": seg_b["assetId"],
                 "startMs": b_src - extras[b]["headExtraMs"], "lenMs": clip_len},
            ],
            "join": {"durationMs": duration, "offsetMs": context},
        })
    total = directive["timelineDurationMs"]
    master = directive.get("masterFades") or {}

    def context_of_full(seg_id: str, duration_ms: int) -> int:
        """黑场档独占成片网格 D 全长（非 D/2），上下文上限=段长−D。"""
        seg = grid[seg_id]
        return max(0, min(context_ms, (seg["outputEndMs"] - seg["outputStartMs"]) - duration_ms))

    if int(master.get("fadeInMs") or 0) > 0:
        first, duration = ordered[0], int(master["fadeInMs"])
        context = context_of_full(first["segmentId"], duration)
        start = first["startMs"] if isinstance(first.get("startMs"), int) else first["source"]["startMs"]
        items.append({"boundary": "成片首", "type": "黑场入", "durationMs": duration,
                      "windowMs": [0, duration + context], "clipLenMs": duration + context,
                      "parts": [{"role": "only", "assetId": first["assetId"],
                                 "startMs": start, "lenMs": duration + context}],
                      "join": None, "fade": {"t": "in", "stMs": 0, "dMs": duration}})
    if int(master.get("fadeOutMs") or 0) > 0:
        last, duration = ordered[-1], int(master["fadeOutMs"])
        context = context_of_full(last["segmentId"], duration)
        end = last["endMs"] if isinstance(last.get("endMs"), int) else last["source"]["endMs"]
        items.append({"boundary": "成片尾", "type": "黑场出", "durationMs": duration,
                      "windowMs": [total - duration - context, total], "clipLenMs": duration + context,
                      "parts": [{"role": "only", "assetId": last["assetId"],
                                 "startMs": end - duration - context, "lenMs": duration + context}],
                      "join": None, "fade": {"t": "out", "stMs": context, "dMs": duration}})
    return items


# ---- 源解析与渲染 ----

def resolve_sources(evidence: dict, pack: dict, pack_root: Path) -> dict:
    """assetId -> {path, sha256}；evidence 与 material-pack 双向对账 + 文件实测哈希，
    任何不一致=素材已变更（源只读红线）。"""
    pack_assets = {a["assetId"]: a for a in pack.get("sourceAssets", []) if isinstance(a, dict)}
    resolved = {}
    for entry in evidence.get("sourceEvidence", []):
        asset_id = entry.get("assetId")
        if not asset_id or asset_id not in pack_assets:
            continue
        pack_entry = pack_assets[asset_id]
        if str(entry.get("relativePath") or "") != str(pack_entry.get("relativePath") or ""):
            raise ValueError(f"{asset_id}：证据清单与素材包 relativePath 不一致，先重跑证据核对")
        path = pack_root / pack_entry["relativePath"]
        if not path.exists():
            raise ValueError(f"{asset_id}：源文件缺失 {path}")
        resolved[asset_id] = {"path": path, "sha256": str(pack_entry.get("sha256") or "").upper(),
                              "evidenceSha": str(entry.get("sha256") or "").upper()}
    return resolved


def verify_sources(sources: dict) -> None:
    cache = {}
    for asset_id, info in sources.items():
        expected = {info["sha256"], info["evidenceSha"]} - {""}
        if not expected:
            raise ValueError(f"{asset_id}：素材包与证据均未登记 sha256，无法验身（不猜）")
        actual = cache.get(asset_id) or sha256(info["path"])
        cache[asset_id] = actual
        if actual not in expected:
            raise ValueError(f"{asset_id}：源素材哈希与登记不符（已变更？），预览拒绝渲染——先重验素材")


def run_checked(cmd: list, out: Path) -> None:
    subprocess.run(cmd, capture_output=True, check=True)
    if not out.exists() or out.stat().st_size == 0:
        raise ValueError(f"ffmpeg 退出 0 但产物缺失/为空：{out.name}")


def render_item(item: dict, sources: dict, ffmpeg: str, ffprobe: str, out_dir: Path,
                version: str, fps: int, canvas, crop_bottom_ratio: float) -> dict:
    preview_w, preview_h = canvas
    stem = f"{CLIP_PREFIX}-{item['boundary'].replace('→', 'to').replace('成片首', 'head').replace('成片尾', 'tail')}-{version}"
    vf = render_vf(preview_w, preview_h, fps, crop_bottom_ratio)
    args_log = []
    temps = []
    for part in item["parts"]:
        source = sources[part["assetId"]]
        clip = out_dir / f"{stem}-{part['role']}.mp4"
        cmd = ["ffmpeg", "-y", "-v", "error",
               "-ss", f"{part['startMs'] / 1000:.3f}", "-i", str(source["path"]),
               "-t", f"{part['lenMs'] / 1000:.3f}", "-map", "0:v:0",
               "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", PREVIEW_CRF,
               "-an", "-movflags", "+faststart", str(clip)]
        cmd[0] = ffmpeg
        run_checked(cmd, clip)
        temps.append(clip)
        args_log.append(cmd)
    if item["join"]:
        output = out_dir / f"{stem}.mp4"
        duration_s = f"{item['join']['durationMs'] / 1000:.3f}"
        offset_s = f"{item['join']['offsetMs'] / 1000:.3f}"
        cmd = [ffmpeg, "-y", "-v", "error", "-i", str(temps[0]), "-i", str(temps[1]),
               "-filter_complex", xfade_join_filter(fps, duration_s, offset_s),
               "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "veryfast",
               "-crf", PREVIEW_CRF, "-movflags", "+faststart", str(output)]
    else:
        output = out_dir / f"{stem}.mp4"
        fade = item["fade"]
        st_s = f"{fade['stMs'] / 1000:.3f}"
        d_s = f"{fade['dMs'] / 1000:.3f}"
        cmd = [ffmpeg, "-y", "-v", "error", "-i", str(temps[0]),
               "-vf", f"{vf},{black_fade_filter(fade['t'], st_s, d_s)}",
               "-map", "0:v:0", "-an", "-c:v", "libx264", "-preset", "veryfast",
               "-crf", PREVIEW_CRF, "-movflags", "+faststart", str(output)]
    args_log.append(cmd)
    run_checked(cmd, output)
    for temp in temps:
        temp.unlink()  # 中间件不入库：renderArgs 已全量入册，可逐字重建
    return {"boundary": item["boundary"], "type": item["type"],
            "durationMs": item["durationMs"], "windowMs": item["windowMs"],
            "file": output.name,  # 相对清单所在目录（门禁对账按此拼接）
            "probedLenMs": probe_duration_ms(ffprobe, output),
            # 输出时长=窗口跨度：叠化 2×(D+C)−D=D+2C；黑场 D+C
            "expectLenMs": item["windowMs"][1] - item["windowMs"][0],
            "sha256": sha256(output), "renderArgs": args_log}


def mmss(ms: int) -> str:
    minutes, rest = divmod(int(ms), 60000)
    seconds, millis = divmod(rest, 1000)
    return f"{minutes}:{seconds:02d}.{millis:03d}"


def build_viewer_html(manifest: dict) -> str:
    """自包含观看页（用户 09-23 拍板：审批卡下统一附一页看全部）。
    与清单同目录落盘→<video src> 用裸文件名相对引用；数据全部取自清单，
    本页不重算任何窗口算术（防幻觉宪法：呈现层零算术）。"""
    markers = "①②③④⑤⑥⑦⑧⑨⑩"
    entries = []
    for index, entry in enumerate(manifest["previews"], 1):
        window = entry["windowMs"]
        marker = markers[index - 1] if index <= len(markers) else str(index)
        heading = (f"{marker} {entry['boundary']} ｜ {entry['type']} · {mmss(entry['durationMs'])} ｜ "
                   f"成片窗口 {mmss(window[0])}–{mmss(window[1])}")
        video = entry["file"]
        note = (f"实测时长 {mmss(entry['probedLenMs'])}（批准窗口 {mmss(window[1] - window[0])}）"
                f"｜ 无声小样，混合公式与成片逐字同式")
        entries.append(f'<div class="card"><h2>{heading}</h2>\n'
                       f'<video controls preload="metadata" src="{video}"></video>\n'
                       f'<p class="note">{note}</p></div>')
    page_version = manifest.get("version", "")
    return ("<!DOCTYPE html>\n<html lang=\"zh\">\n<head>\n<meta charset=\"utf-8\">\n"
            f"<title>转场试装预览 · {manifest.get('projectId', '')} · {page_version}</title>\n<style>\n"
            " body{font-family:-apple-system,\"PingFang SC\",sans-serif;background:#101418;color:#e8eaed;"
            "margin:24px auto;max-width:960px}\n h1{font-size:20px}\n .note{color:#9aa0a6;font-size:13px;line-height:1.6}\n"
            " .card{margin:18px 0;padding:14px;background:#1a1f26;border-radius:10px}\n"
            " .card h2{font-size:15px;margin:0 0 8px}\n video{width:100%;border-radius:6px;background:#000}\n"
            "</style>\n</head>\n<body>\n"
            f"<h1>转场试装预览 · 观看页 {page_version}</h1>\n<p class=\"note\">{manifest['disclaimer']}</p>\n"
            + "\n".join(entries) + "\n"
            f"<p class=\"note\">本页与《{MANIFEST_PREFIX}-{page_version}.json》同场生成"
            f"（计划哈希 {str(manifest.get('planSha256', ''))[:12]}… 绑定；计划改版旧页自动作废，须重跑）。</p>\n"
            "</body>\n</html>\n")


def blocked(reason, status="blocked_previews") -> int:
    print(json.dumps({"status": status, "reason": reason, "disclosure": DISCLOSURE}, ensure_ascii=False))
    return 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--host-profile", type=Path, help="计划含叠化时必传（与深检/directive 同规矩）")
    parser.add_argument("--material-pack", required=True, type=Path, help="G0 material-pack.json")
    parser.add_argument("--output-dir", required=True, type=Path, help="工作台/<id>/G3-剪辑计划/预览小样/")
    parser.add_argument("--fps", type=int, help="成片帧率；计划无 fps 字段时必传（⑨ 教训：不猜）")
    parser.add_argument("--context-ms", type=int, default=CONTEXT_MS)
    parser.add_argument("--crop-bottom-ratio", type=float, default=0.0,
                        help="与 g4_render 同参：计划含底部裁切时传入，预览才与成片同幅")
    args = parser.parse_args()

    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        return blocked("宿主未安装 ffmpeg/ffprobe（PATH 不可见）")

    plan, evidence = load(args.plan), load(args.evidence)
    host_profile = load(args.host_profile) if args.host_profile else None
    if host_profile is not None and (host_profile.get("skill") != "transition-expert"
                                     or host_profile.get("purpose") != "transition_host_profile"):
        return blocked("--host-profile 不是 transition-expert 的 transition_host_profile 产物", "invalid")
    validator = load_sibling("transition_validate_plan")
    report = validator.validate_plan(plan, evidence, host_profile)
    if report.get("status") != "passed":
        return blocked(json.dumps(report.get("errors", [report.get("error")]), ensure_ascii=False))
    directive_builder = load_sibling("transition_directive")
    directive = directive_builder.build_directive(plan, evidence, host_profile)

    items = build_preview_items(plan, directive, args.context_ms)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = next_versioned_path(args.output_dir, MANIFEST_PREFIX)
    version = manifest_path.name[len(MANIFEST_PREFIX) + 1:-len(".json")]

    used_assets = {part["assetId"] for item in items for part in item["parts"]}
    manifest = {"schemaVersion": "0.2", "skill": "transition-expert", "purpose": "transition_preview",
                "generatedAt": now(), "audio": False, "version": version,
                "projectId": plan.get("projectId"),
                "inputPlan": str(args.plan), "planSha256": sha256(args.plan),
                "inputEvidence": str(args.evidence), "evidenceSha256": sha256(args.evidence),
                "hostProfile": str(args.host_profile) if args.host_profile else None,
                "hostProfileSha256": sha256(args.host_profile) if args.host_profile else None,
                "materialPack": str(args.material_pack), "materialPackSha256": sha256(args.material_pack),
                "timelineDurationMs": directive["timelineDurationMs"],
                "previews": [],
                "disclaimer": ("小样=按本卡批准参数从源素材实渲染，混合公式与成片逐字同式（代码同源）；"
                               "纯画面无声——配音/BGM 混音属 G4，节奏以 G2 口播与乐句表为准；"
                               "小样未复现源字幕遮蔽等包装层处理，只验转场观感；"
                               "通过与否不改变逐切点人工批准义务")}
    if not items:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                                 encoding="utf-8")
        print(json.dumps({"status": "completed", "manifest": str(manifest_path), "sha256": sha256(manifest_path),
                          "previews": 0, "note": "计划无转场，空清单（卡上无需预览区）"}, ensure_ascii=False))
        return 0

    pack_root = args.material_pack.parent
    try:
        pack = load(args.material_pack)
        sources = resolve_sources(evidence, pack, pack_root)
        missing = used_assets - set(sources)
        if missing:
            return blocked(f"素材包缺资产登记：{sorted(missing)}（能力可以缺、事实不能编）")
        verify_sources({key: value for key, value in sources.items() if key in used_assets})
    except (ValueError, KeyError, OSError) as error:
        return blocked(f"源素材对账失败：{error}")
    fps = args.fps if args.fps else (plan.get("fps") if isinstance(plan.get("fps"), int) else None)
    if fps is None:
        return blocked("计划无 fps 字段且未传 --fps：拒绝猜帧率（⑨ 教训）")
    first_asset = items[0]["parts"][0]["assetId"]
    try:
        width, height = probe_source_size(ffprobe, sources[first_asset]["path"])
    except (subprocess.CalledProcessError, ValueError, KeyError) as error:
        return blocked(f"源画面尺寸探测失败：{error}")
    preview_w = min(width, PREVIEW_WIDTH)
    if preview_w % 2:
        preview_w -= 1
    preview_h = max(2, round(height * preview_w / width / 2) * 2)
    canvas = (preview_w, preview_h)
    try:
        for item in items:
            manifest["previews"].append(render_item(
                item, sources, ffmpeg, ffprobe, args.output_dir, version, fps,
                canvas, args.crop_bottom_ratio))
    except (subprocess.CalledProcessError, ValueError) as error:
        detail = error.stderr.decode("utf-8", "replace")[:500] if isinstance(error, subprocess.CalledProcessError) else str(error)
        return blocked(f"预览渲染失败（不静默跳卡）：{error.__class__.__name__}: {detail}")
    viewer_path = args.output_dir / f"{VIEWER_PREFIX}-{version}.html"
    viewer_path.write_text(build_viewer_html(manifest), encoding="utf-8")
    manifest["viewerPage"] = viewer_path.name  # 相对清单所在目录（与 previews[].file 同规矩）
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
    print(json.dumps({"status": "completed", "manifest": str(manifest_path), "sha256": sha256(manifest_path),
                      "viewerPage": str(viewer_path),
                      "previews": len(manifest["previews"]),
                      "boundaries": [p["boundary"] for p in manifest["previews"]]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "invalid", "error": str(error)}, ensure_ascii=False))
        raise SystemExit(2)
