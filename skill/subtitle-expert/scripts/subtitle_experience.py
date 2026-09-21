#!/usr/bin/env python3
"""字幕经验库唯一写入口（experience/subtitles/）——照音乐经验库同一纪律：
Agent 不手改 JSON，只走本命令；一条档案一个事实主题，记录只增不删。

三条红线（README 全文）：
1. 库=建议层，不是批准：query 输出永远标注"推荐≠批准"，G3 每次必须重新出合同、
   重新过 `subtitle_validate_layout.py`、重新过门禁（g0-followups-not-inherited 教训）。
2. 呈现层事实才入库：record-layout 只抽 lanes.narration 的排版参数白名单字段，
   cue 时刻/断句文本等每项目语义判断**永不入库**（脚本层面就进不去）。
3. 未验证的不写：font 的 usable/rejected 判定必须带 --evidence（㉛ 预检/目视实据）；
   layout 必须带 --approval（G3 门禁批准文件路径）；renderer 只存探测报告派生事实。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# 库根不硬编码：显式 --library 参数优先（插件可迁移标准），其次环境变量
# SUBTITLE_EXPERIENCE_HOME / MUSIC_EXPERT_* 同族惯例；都没有才回落到仓内默认位置。
NARRATION_WHITELIST = ("fontsize", "maxLines", "autoWrap", "topPct", "bottomPct", "marginL", "marginR", "marginV")


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def fail(message: str) -> None:
    print(json.dumps({"status": "invalid", "error": message}, ensure_ascii=False))
    raise SystemExit(2)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def load(path: Path, label: str) -> dict:
    if not path.is_file() or path.stat().st_size == 0:
        fail(f"{label} missing or empty: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def library_root() -> Path:
    if os.environ.get("SUBTITLE_EXPERIENCE_HOME"):
        return Path(os.environ["SUBTITLE_EXPERIENCE_HOME"])
    return Path(__file__).resolve().parents[3] / "experience" / "subtitles"


LIBRARY = library_root()  # main() 里可被 --library 覆盖


def store(folder: str, key: str, build) -> dict:
    root = LIBRARY / folder
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{key}.json"
    record = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    record = build(record)
    record["schemaVersion"] = "0.1"
    record["updatedBy"] = "subtitle_experience.py"
    record["updatedAt"] = now()
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {"status": "recorded", "file": str(path)}


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text.strip()).strip("-")


def normalise_resolution(resolution):
    """把 list/dict/str 形状的分辨率归一为 "WxH"（合同与档案历史上三种写法都出现过）。"""
    if isinstance(resolution, str):
        parts = re.split(r"[x×*]", resolution.strip())
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            return f"{parts[0]}x{parts[1]}"
        return None
    if isinstance(resolution, (list, tuple)) and len(resolution) == 2:
        return f"{resolution[0]}x{resolution[1]}"
    if isinstance(resolution, dict):
        w, h = resolution.get("width"), resolution.get("height")
        if w and h:
            return f"{w}x{h}"
    return None


def cmd_record_font(args) -> dict:
    if args.verdict not in ("usable", "blocked", "rejected"):
        fail("--verdict ∈ usable|blocked|rejected")
    if args.verdict in ("usable", "rejected") and not (args.evidence or "").strip():
        fail(f"verdict={args.verdict} 必须带 --evidence（㉛ 预检结论/交付目视实据）——未验证的不写")
    if args.font_file:
        font = Path(args.font_file)
        if not font.is_file() or font.stat().st_size == 0:
            fail(f"font file not found/empty: {font}（未见过本体不入库）")
        head = {"kind": "font", "identity": "file", "fontFile": font.name, "sha256": sha256(font)}
        key = slug(font.stem) + "-" + sha256(font)[:12]
    else:
        # libass 路线按 family 名经系统字体服务解析（CoreText/fontconfig），宿主上可能
        # 根本没有独立 ttf/ttc 文件（09-21 实测：本机无 PingFang.ttc，family "PingFang SC"
        # 照常渲染交付）。此类档案身份=family+usage，证据只能来自真实渲染/交付。
        if not (args.font_family or "").strip():
            fail("record-font 需要 --font-file（drawtext 路线）或 --font-family（libass 路线）之一")
        if args.usage != "libass":
            fail("family 档案只登记 libass 路线（drawtext 必须指到具体文件，fontfile 参数）")
        head = {"kind": "font", "identity": "family", "fontFamily": args.font_family.strip()}
        key = "family-" + slug(args.font_family)

    def build(existing):
        record = existing or {**head, "records": []}
        record["records"].append({"at": now(), "usage": args.usage, "verdict": args.verdict,
                                  "evidence": args.evidence, "project": args.project, "note": args.note})
        return record
    return store("fonts", key, build)


def cmd_record_layout(args) -> dict:
    contract = load(Path(args.contract), "G3 字幕布局合同")
    approval = Path(args.approval)
    if not approval.is_file() or approval.stat().st_size == 0:
        fail(f"门禁批准文件缺失/空: {approval}——未批准过的排版不入库（红线 1）")
    lane = contract.get("lanes", {}).get("narration")
    if not isinstance(lane, dict) or "fontsize" not in lane or "maxLines" not in lane:
        fail("合同缺 lanes.narration.fontsize/maxLines，无可入库的呈现层参数")
    profile = {field: lane[field] for field in NARRATION_WHITELIST if field in lane}
    resolution = normalise_resolution(contract.get("resolution"))
    key = f"{slug(resolution or 'res')}-{slug(str(profile['fontsize']))}px"

    def build(existing):
        record = existing or {"kind": "layout", "resolution": resolution, "narration": profile, "projects": [], "approvals": []}
        project = contract.get("projectId", args.project or "unknown")
        if project not in record["projects"]:
            record["projects"].append(project)
        record["approvals"].append({"at": now(), "file": str(approval), "contract": str(Path(args.contract))})
        return record
    return store("layouts", key, build)


def cmd_record_renderer(args) -> dict:
    profile = load(Path(args.profile), "渲染器能力档")
    if profile.get("purpose") != "subtitle_renderer_profile" or profile.get("skill") != "subtitle-expert":
        fail("不是 subtitle_probe_renderer.py 产出的能力档（红线 3：只存探测派生事实）")
    host = profile.get("host", {})
    # 档案跟机器走（system-machine-release）：能力档是宿主事实，换机必须重探重录。
    key = slug(f"{host.get('system')}-{host.get('machine')}-{host.get('release')}")
    if (profile.get("autoWrap") or {}).get("value") and not (profile.get("autoWrap") or {}).get("evidence"):
        fail("能力档 autoWrap=true 却无证据——探测脚本本身就该拒了，库里同样不收")

    def build(existing):
        record = existing or {"kind": "renderer", "host": host, "ffmpeg": profile.get("ffmpeg"),
                              "autoWrap": profile.get("autoWrap"), "observations": []}
        record["observations"].append({"at": now(), "file": str(Path(args.profile))})
        return record
    return store("renderer", key, build)


def cmd_query(args) -> dict:
    folder = {"font": "fonts", "layout": "layouts", "renderer": "renderer"}[args.kind]
    root = LIBRARY / folder
    hits = []
    for path in sorted(root.glob("*.json")) if root.is_dir() else []:
        record = json.loads(path.read_text(encoding="utf-8"))
        if args.resolution and record.get("kind") == "layout":
            res = normalise_resolution(record.get("resolution")) or ""
            if args.resolution.lower() != res.lower():
                continue
        hits.append({"file": path.name, "record": record})
    miss = bool(args.resolution) and not hits and args.kind == "layout"
    if miss:  # 分辨率没有精确档：给全量近邻档供人/模型挑参照，绝不空手假装命中
        hits = [{"file": path.name, "record": json.loads(path.read_text(encoding="utf-8"))}
                for path in sorted(root.glob("*.json"))]
    return {"status": "completed", "kind": args.kind, "count": len(hits), "resolutionMiss": miss, "hits": hits,
            "disclaimer": "推荐≠批准：G3 必须重新出布局合同、过 subtitle_validate_layout.py、过门禁后才生效；库永不携带 cue 时刻与文本。"}


def main() -> int:
    global LIBRARY
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", type=Path, help="库根目录（默认取 SUBTITLE_EXPERIENCE_HOME，再回落仓内 experience/subtitles）")
    sub = parser.add_subparsers(dest="command", required=True)
    font = sub.add_parser("record-font")
    font.add_argument("--font-file", help="字体文件路径（drawtext 路线，身份=文件 SHA）")
    font.add_argument("--font-family", help="family 名（libass 路线，身份=family，宿主解析事实随记录走）")
    font.add_argument("--usage", required=True, choices=("drawtext", "libass"))
    font.add_argument("--verdict", required=True)
    font.add_argument("--evidence")
    font.add_argument("--project")
    font.add_argument("--note")
    layout = sub.add_parser("record-layout")
    layout.add_argument("--contract", required=True)
    layout.add_argument("--approval", required=True)
    layout.add_argument("--project")
    renderer = sub.add_parser("record-renderer")
    renderer.add_argument("--profile", required=True)
    query = sub.add_parser("query")
    query.add_argument("--kind", required=True, choices=("font", "layout", "renderer"))
    query.add_argument("--resolution", help="过滤 layout 档案，如 1920x1080")
    args = parser.parse_args()
    if args.library:
        LIBRARY = args.library
    handler = {"record-font": cmd_record_font, "record-layout": cmd_record_layout,
               "record-renderer": cmd_record_renderer, "query": cmd_query}[args.command]
    print(json.dumps(handler(args), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
