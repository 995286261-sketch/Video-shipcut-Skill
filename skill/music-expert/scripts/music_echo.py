#!/usr/bin/env python3
"""Deterministic node-style echo card for a《BGM 分析报告》.

Fixed template in the spirit of the editing skill's review cards: a short
"what was done" header, one global-facts line, then a per-segment TABLE
(段｜区间｜能量｜音乐结构｜对剪辑的意义). Every number comes straight from the
report JSON; the structure/meaning columns are rule-generated tiers (档位) from
energy ratios — a machine draft for the human reviewer, never a guess that
invents musical facts. Rendered without any analysis runtime so cache hits
can regenerate the card for free.
"""
from __future__ import annotations

from pathlib import Path

SEGMENT_HEADERS = ("段", "区间", "能量", "音乐结构", "对剪辑的意义")

MEANING_BY_TIER = {
    "high": "高潮区：信息密度最高的画面、最快剪辑节奏放这里",
    "mid": "推进铺垫；卡点密度回升，转场可加密",
    "steady": "稳定叙事区；柔和衔接为主",
    "low": "低谷留白；节奏放慢，适合总结/换气句",
    "outro": "尾段归零；成片淡出对齐本段起点最顺",
}


def mmss(ms: int) -> str:
    minutes, remainder = divmod(int(ms), 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{minutes}:{seconds:02d}.{millis:03d}"


def cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def tier_of(energy: float, top: float, last_index: int, index: int) -> str:
    ratio = energy / top if top > 0 else 0.0
    if ratio >= 0.9:
        return "high"
    if ratio >= 0.6:
        return "mid"
    if ratio >= 0.3:
        return "steady"
    return "outro" if index == last_index else "low"


def label_segments(segments: list[dict]) -> list[tuple[str, str, str]]:
    """Returns per-segment (energyText, structureText, meaningText)."""
    top = max(seg["energyMean"] for seg in segments)
    last = len(segments) - 1
    high_seen = 0
    labeled = []
    for index, seg in enumerate(segments):
        tier = tier_of(seg["energyMean"], top, last, index)
        energy_text = f"{seg['energyMean']:.3f}"
        if tier == "high":
            high_seen += 1
            structure = "主高潮（全曲最高能量）" if high_seen == 1 else f"次高潮 {high_seen}（能量 ≥ 主高潮 90%）"
            meaning = MEANING_BY_TIER["high"]
        elif tier == "mid":
            structure, meaning = "推进段", MEANING_BY_TIER["mid"]
        elif tier == "steady":
            structure, meaning = "平稳段", MEANING_BY_TIER["steady"]
        elif tier == "outro":
            structure, meaning = "尾段归零", MEANING_BY_TIER["outro"]
        else:
            structure, meaning = "低谷/收口", MEANING_BY_TIER["low"]
        if index == 0:
            structure = "开场·" + structure
        labeled.append((energy_text, structure, meaning))
    return labeled


def render_card(report: dict, report_path: Path | None = None) -> str:
    source = report.get("source") or {}
    segments = report.get("energySegments") or []
    loudness = report.get("loudness") or {}
    beats = sorted(report.get("beatsMs") or [])
    intervals = sorted(beats[i + 1] - beats[i] for i in range(len(beats) - 1))
    median_interval = intervals[len(intervals) // 2] if intervals else 0
    hits_by_kind = {}
    for point in report.get("hitPoints") or []:
        hits_by_kind[point.get("kind", "?")] = hits_by_kind.get(point.get("kind", "?"), 0) + 1
    kind_names = {"beat": "拍点", "accent": "离拍重音"}
    hit_text = f"卡点 {sum(hits_by_kind.values())}（" + " + ".join(
        f"{v} {kind_names.get(k, k)}" for k, v in sorted(hits_by_kind.items())) + "）"
    lines = [f"# BGM 分析回显 — {Path(source.get('path', '')).name or '未知曲目'}", ""]
    lines += [f"- 做了什么：ffmpeg 全量解码核验 → librosa 节奏/起音/能量分析 → ebur128 响度实测（版本 {report.get('analysisVersion')}）；同文件重跑命中缓存不重算"]
    if source.get("mediaKind") == "video-with-audio":
        lines.append("- 来源：音轨抽自视频，本卡数字是**解说混音后的事实**，不是乐曲本体——人声会多计卡点、"
                     "逐句 ducking 会压平能量起伏；需要干净乐曲数据时请用纯音频文件重新分析，"
                     "或按接线方案走人声分离预处理")
    lines += [f"- 全局事实：{mmss(source.get('decodedDurationMs', 0))} ｜ {report.get('tempoBpm')} BPM"
              f"（拍间隔中位 {median_interval}ms）｜ {hit_text}"
              f" ｜ 积分响度 {loudness.get('integratedLufs')} LUFS"]
    if loudness.get("truePeakDbtp") is None:
        lines.append("- 注：true peak 本次未测得（ebur128 输出缺项）；混音前如需限峰请另测")
    lines += ["", "## 分段分析", "",
              "此卡的数字与《BGM 分析报告》JSON 同源；\"音乐结构/对剪辑的意义\"两列为能量档位规则的机械草稿，供人工复核修正。",
              "",
              "| " + " | ".join(SEGMENT_HEADERS) + " |",
              "|" + "|".join("---" for _ in SEGMENT_HEADERS) + "|"]
    for index, (seg, (energy_text, structure, meaning)) in enumerate(zip(segments, label_segments(segments)), start=1):
        lines.append(f"| {index} | {mmss(seg['startMs'])}–{mmss(seg['endMs'])} | {cell(energy_text)} | {cell(structure)} | {cell(meaning)} |")
    top_energy = max((seg["energyMean"] for seg in segments), default=0.0)
    high_count = sum(1 for seg in segments if top_energy > 0 and seg["energyMean"] >= 0.9 * top_energy)
    lines += ["", f"结构读法：{len(segments)} 段，其中高能量段 {high_count} 个。"
              + ("多高潮结构：按片内高潮次数选择段截取或调整轨偏移。" if high_count >= 2 else "单一高潮结构：高潮句用 --climax-sentence 交给对齐器即可。"),
              "", "## 产物", ""]
    if report_path is not None:
        lines.append(f"- 分析报告：`{report_path}`")
    lines.append(f"- 对齐（可选）：`music_align.py --report <本报告> …` 产出《BGM-对齐建议》与《BGM-对齐回显》")
    return "\n".join(lines) + "\n"


def echo_path_for(report_path: Path) -> Path:
    name = report_path.name.replace("BGM-分析报告-", "BGM-分析回显-")
    if name.endswith(".json"):
        name = name[: -len(".json")] + ".md"
    return report_path.with_name(name)


def write_card_for(report_path: Path) -> Path:
    import json
    report = json.loads(report_path.read_text(encoding="utf-8"))
    echo = echo_path_for(report_path)
    echo.write_text(render_card(report, report_path), encoding="utf-8")
    return echo
