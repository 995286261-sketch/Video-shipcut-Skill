#!/usr/bin/env python3
"""Align a BGM analysis report with a narration sentence timeline.

Deterministic, pure-stdlib: it joins the《BGM 分析报告》(energySegments/hitPoints)
with the G2-style voice brief (sentence startMs/durationMs) and emits a machine
JSON plus a node-style review echo card (markdown, m:ss.mmm timecodes) covering:
track offset suggestion, climax mapping, sentence-boundary beat snapping with
honest miss reporting, ducking/fade intervals, a machine phrase table placed on
the output timeline, and a per-sentence layoutTier *draft* (segment-energy
quantiles, adjustable). It never forces alignment: narration durations are
authoritative (antiFill discipline), the card only suggests where cut points
may ride on musical accents, and layoutTier drafts are mechanical proposals
the G3 final eight-column review re-decides row by row (thin-harness rule).

Blueprint mode (N9, 2026-09-10): with --blueprint there is no script yet —
it emits the beat grid, phrase windows, per-phrase sentence budget hints and
suggested cut boundaries so G2 can *write the narration to the music* instead
of forcing the music onto a frozen script. Blueprint timecodes are design
intent only; measured TTS durations remain the single source of fact and G3
alignment (this script's default mode) verifies the draft against the grid.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCHEMA_VERSION = "0.2"
LAYOUT_TIERS = ("快切", "推进", "常规", "留白")


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True))


def fail_exit(errors: list[dict], code: int = 2) -> None:
    emit({"status": "invalid", "errors": errors})
    raise SystemExit(code)


def mmss(ms: int) -> str:
    minutes, remainder = divmod(int(ms), 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{minutes}:{seconds:02d}.{millis:03d}"


def load_json(path: Path, label: str) -> dict:
    if not path.is_file():
        fail_exit([{"field": label, "rule": "file not found", "detail": str(path)}])
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        fail_exit([{"field": label, "rule": "invalid json", "detail": str(error)}])
        return {}


def sentence_bounds(brief: dict, timeline_ms: int) -> list[dict]:
    bounds = []
    for sentence in brief.get("sentences", []):
        start, duration = sentence.get("startMs"), sentence.get("durationMs")
        if not isinstance(start, int) or not isinstance(duration, int) or duration <= 0:
            fail_exit([{"field": "voiceBrief", "rule": "every sentence needs integer startMs/durationMs",
                        "detail": str(sentence.get("sentenceId"))}])
        end = start + duration
        if end > timeline_ms:
            fail_exit([{"field": "timelineMs", "rule": "a sentence ends after the timeline",
                        "detail": f"{sentence.get('sentenceId')} ends at {end}ms > {timeline_ms}ms"}])
        bounds.append({"sentenceId": sentence.get("sentenceId"), "startMs": start, "endMs": end})
    if not bounds:
        fail_exit([{"field": "voiceBrief", "rule": "sentences must be a non-empty list"}])
    return bounds


def pick_offset(track_ms: int, timeline_ms: int, segments: list[dict], bounds: list[dict],
                climax_sentence: str | None) -> dict:
    top = max(segments, key=lambda seg: seg["energyMean"])
    top_center = (top["startMs"] + top["endMs"]) // 2
    max_offset = track_ms - timeline_ms
    if climax_sentence:
        anchor = next((item for item in bounds if item["sentenceId"] == climax_sentence), None)
        if anchor is None:
            fail_exit([{"field": "climaxSentence", "rule": "unknown sentenceId", "detail": climax_sentence}])
        center = (anchor["startMs"] + anchor["endMs"]) // 2
        raw = top_center - center
        offset = max(0, min(max_offset, raw))
        deviation = offset - raw
        basis = f"climax sentence {climax_sentence} center {mmss(center)} ← top-energy segment center {mmss(top_center)}"
    else:
        offset, deviation, raw = 0, 0, 0
        basis = "default: no --climax-sentence given, bed starts at track 0:00.000"
    window = [max(0, top["startMs"] - offset), min(timeline_ms, top["endMs"] - offset)]
    overlaps = []
    for item in bounds:
        lo, hi = max(item["startMs"], window[0]), min(item["endMs"], window[1])
        if hi > lo:
            overlaps.append({"sentenceId": item["sentenceId"], "overlapMs": hi - lo})
    anchor_id = max(overlaps, key=lambda item: item["overlapMs"])["sentenceId"] if overlaps else None
    return {"offsetMs": offset, "rawOffsetMs": raw, "clampedDeviationMs": deviation,
            "basis": basis, "topEnergySegment": top, "topSegmentOnTimeline": window,
            "climaxAnchorSentence": anchor_id, "coveredSentences": overlaps}


def snap_boundaries(bounds: list[dict], hit_points: list[dict], offset_ms: int,
                    timeline_ms: int, tolerance_ms: int) -> tuple[list[dict], list[dict]]:
    track_times = sorted(point["tMs"] for point in hit_points)
    snapped, missed = [], []
    for item in bounds:
        for boundary, role in ((item["startMs"], "start"), (item["endMs"], "end")):
            if role == "end" and item is bounds[-1]:
                continue
            candidates = [(abs(track - offset_ms - boundary), track) for track in track_times
                          if 0 <= track - offset_ms <= timeline_ms]
            if not candidates:
                continue
            delta, track = min(candidates)
            record = {"sentenceId": item["sentenceId"], "boundary": role, "boundaryMs": boundary,
                      "hitPointTrackMs": track, "hitPointTimelineMs": track - offset_ms, "deltaMs": track - offset_ms - boundary}
            if abs(delta) <= tolerance_ms:
                snapped.append(record)
            else:
                missed.append({**record, "nearestDistanceMs": abs(delta)})
    return snapped, missed


def parse_tier_quantiles(raw: str) -> list[float]:
    try:
        parts = [float(item) for item in raw.split(",")]
    except ValueError:
        parts = []
    if len(parts) != 3 or not all(0.0 <= part <= 1.0 for part in parts) or not parts[0] > parts[1] > parts[2]:
        fail_exit([{"field": "tierQuantiles", "rule": "must be three floats high>mid>low within [0,1]", "detail": raw}])
    return parts


def quantile(sorted_values: list[float], q: float) -> float:
    pos = q * (len(sorted_values) - 1)
    low = int(pos)
    high = min(low + 1, len(sorted_values) - 1)
    frac = pos - low
    return sorted_values[low] * (1 - frac) + sorted_values[high] * frac


def shifted_segments(segments: list[dict], offset_ms: int) -> list[tuple[int, int, float]]:
    return [(seg["startMs"] - offset_ms, seg["endMs"] - offset_ms, seg["energyMean"]) for seg in segments]


def weighted_energy(shifted: list[tuple[int, int, float]], start_ms: int, end_ms: int) -> float:
    total, acc = 0, 0.0
    for seg_start, seg_end, energy in shifted:
        lo, hi = max(start_ms, seg_start), min(end_ms, seg_end)
        if hi > lo:
            total += hi - lo
            acc += (hi - lo) * energy
    return acc / total if total else 0.0


def tier_for(energy: float, cutoffs: list[float], flat: bool) -> str:
    if flat:
        return "常规"
    high, mid, low = cutoffs
    if energy >= high:
        return "快切"
    if energy >= mid:
        return "推进"
    if energy >= low:
        return "常规"
    return "留白"


def build_layout(shifted: list[tuple[int, int, float]], bounds: list[dict],
                 offset_ms: int, timeline_ms: int, quantiles: list[float]) -> dict:
    used = [seg for seg in (dict(zip(("startMs", "endMs", "energyMean"), item)) for item in shifted)
            if min(seg["endMs"], timeline_ms) > max(seg["startMs"], 0)]
    energies = sorted(seg["energyMean"] for seg in used)
    flat = not energies or (energies[-1] - energies[0]) < 1e-9
    cutoffs = [quantile(energies, q) for q in quantiles] if not flat else []
    per_sentence = []
    for item in bounds:
        energy = weighted_energy(shifted, item["startMs"], item["endMs"])
        per_sentence.append({"sentenceId": item["sentenceId"], "energyWeightedMean": round(energy, 4),
                             "layoutTierDraft": tier_for(energy, cutoffs, flat)})
    phrases = []
    for index, seg in enumerate(used, 1):
        clip_start, clip_end = max(seg["startMs"], 0), min(seg["endMs"], timeline_ms)
        phrases.append({
            "phraseId": f"P{index}",
            "trackStartMs": seg["startMs"] + offset_ms, "trackEndMs": seg["endMs"] + offset_ms,
            "timelineStartMs": clip_start, "timelineEndMs": clip_end,
            "energyMean": round(seg["energyMean"], 4),
            "layoutTierDraft": tier_for(seg["energyMean"], cutoffs, flat),
            "coversSentences": [item["sentenceId"] for item in bounds
                                if min(item["endMs"], clip_end) > max(item["startMs"], clip_start)],
        })
    return {
        "tierVocabulary": list(LAYOUT_TIERS),
        "rule": {"kind": "segment-energy-quantile", "quantiles": quantiles,
                 "cutoffs": [round(c, 4) for c in cutoffs] if not flat else None,
                 "flatFallback": "常规" if flat else None},
        "note": "layoutTier 是机械草稿（§6-④）：能量分位数定档，阈值由 --tier-quantiles 可调；"
                "最终档位以 G3 八列终审回显为准，用户可逐行改，改后即为计划事实",
        "perSentence": per_sentence,
        "phrasesOnTimeline": phrases,
    }


def parse_budget_map(raw: str) -> dict:
    tiers = LAYOUT_TIERS
    try:
        pairs = [item.split("-") for item in raw.split(",")]
        nums = [(int(a), int(b)) for a, b in pairs]
    except ValueError:
        nums = []
    if len(nums) != len(tiers) or any(hi <= lo or lo <= 0 for lo, hi in nums):
        fail_exit([{"field": "budgetMap",
                    "rule": "four positive 'min-max' second ranges in tier order 快切,推进,常规,留白",
                    "detail": raw}])
    return {tier: list(nums[index]) for index, tier in enumerate(tiers)}


def pick_blueprint_offset(track_ms: int, timeline_ms: int, segments: list[dict],
                          climax_position_ms: int | None) -> dict:
    top = max(segments, key=lambda seg: seg["energyMean"])
    top_center = (top["startMs"] + top["endMs"]) // 2
    if climax_position_ms is None:
        raw, offset = 0, 0
        basis = "default: no --climax-position-ms given, bed starts at track 0:00.000"
    else:
        raw = top_center - climax_position_ms
        offset = max(0, min(track_ms - timeline_ms, raw))
        basis = f"energy peak center {mmss(top_center)} placed at blueprint position {mmss(climax_position_ms)}"
        if offset != raw:
            basis += f" (clamped, deviation {offset - raw}ms)"
    window = [max(0, top["startMs"] - offset), min(timeline_ms, top["endMs"] - offset)]
    return {"offsetMs": offset, "rawOffsetMs": raw, "clampedDeviationMs": offset - raw,
            "basis": basis, "topEnergySegment": top, "topSegmentOnTimeline": window}


def beat_grid(hit_points: list[dict], offset_ms: int, timeline_ms: int) -> list[int]:
    return sorted({point["tMs"] - offset_ms for point in hit_points
                   if 0 <= point["tMs"] - offset_ms <= timeline_ms})


def build_blueprint(args, report: dict, track_ms: int):
    segments, hit_points = report["energySegments"], report["hitPoints"]
    alignment = pick_blueprint_offset(track_ms, args.timeline_ms, segments, args.climax_position_ms)
    offset = alignment["offsetMs"]
    shifted = shifted_segments(segments, offset)
    layout = build_layout(shifted, [], offset, args.timeline_ms, parse_tier_quantiles(args.tier_quantiles))
    budget = parse_budget_map(args.budget_map)
    phrases = []
    for phrase in layout["phrasesOnTimeline"]:
        lo, hi = budget[phrase["layoutTierDraft"]]
        duration_sec = (phrase["timelineEndMs"] - phrase["timelineStartMs"]) / 1000
        phrases.append({**phrase, "sentenceBudgetHintSec": [lo, hi],
                        "suggestedSentenceCount": max(1, round(duration_sec / ((lo + hi) / 2)))})
    grid = beat_grid(hit_points, offset, args.timeline_ms)
    boundaries = []
    for phrase in phrases[:-1]:
        at = phrase["timelineEndMs"]
        nearest = min(grid, key=lambda beat: abs(beat - at)) if grid else None
        boundaries.append({"atMs": at, "nearestBeatMs": nearest,
                           "deltaMs": None if nearest is None else nearest - at})
    return alignment, phrases, grid, boundaries, layout


def build_blueprint_card(report_path: Path, result: dict) -> str:
    alignment = result["alignment"]
    lines = [f"# BGM 节拍蓝图 — {alignment['trackTitle']}", ""]
    lines += [f"- 输入：分析报告 `{report_path.name}`（{alignment['tempoBpm']} BPM，轨长 {mmss(alignment['trackMs'])}）"
              f"× 目标时长 {mmss(result['timelineMs'])}（口播尚未定稿）",
              "- 蓝图是**创作输入**：供 G2 写稿/改稿把句子长在鼓点上，不是合同", ""]
    lines += ["## 轨偏移（铺法）", "",
              f"- 从音轨 {mmss(alignment['offsetMs'])} 起铺（{alignment['basis']}）", ""]
    lines += ["## 乐句窗口与句预算", "",
              "| 乐句 | 成片区间 | 能量 | 档位草稿 | 每句预算(s) | 建议句数 |", "|---|---|---|---|---|---|"]
    for phrase in result["phrases"]:
        lo, hi = phrase["sentenceBudgetHintSec"]
        lines.append(f"| {phrase['phraseId']} | {mmss(phrase['timelineStartMs'])}–{mmss(phrase['timelineEndMs'])} "
                     f"| {phrase['energyMean']:.3f} | {phrase['layoutTierDraft']} | {lo}–{hi} "
                     f"| {phrase['suggestedSentenceCount']} |")
    rule = result["tierRule"]
    quantile_note = f"{rule['quantiles']}" + (f"（切点 {rule['cutoffs']}）" if rule["cutoffs"] else "（段能量无差异，全部常规）")
    lines += ["", f"> 定档规则：段能量分位数 {quantile_note}；档位词表：{'/'.join(result['tierVocabulary'])}", ""]
    lines += ["## 鼓点栅格", "", f"- 成片轴上卡点 {len(result['beatGridMs'])} 个"]
    if result["beatGridMs"]:
        lines.append(f"- 首 {mmss(result['beatGridMs'][0])}｜末 {mmss(result['beatGridMs'][-1])}")
    lines += ["", "## 建议句边界（乐句切换处贴鼓点）", "",
              "| 边界 | 最近鼓点 | 偏差 |", "|---|---|---|"]
    for item in result["suggestedBoundaries"]:
        beat = "（无）" if item["nearestBeatMs"] is None else mmss(item["nearestBeatMs"])
        delta = "" if item["deltaMs"] is None else f"{item['deltaMs']:+d}ms"
        lines.append(f"| {mmss(item['atMs'])} | {beat} | {delta} |")
    lines += ["", "## 纪律", "", f"- {result['discipline']}", "", "## 产物", "",
              f"- 机器合同：`{result['files']['json']}`", f"- 本蓝图卡：`{result['files']['echo']}`", ""]
    return "\n".join(lines)


def run_blueprint(args, report: dict, track_ms: int) -> int:
    alignment, phrases, grid, boundaries, layout = build_blueprint(args, report, track_ms)
    result = {
        "schemaVersion": "0.1", "purpose": "bgm_blueprint", "skill": "music-expert",
        "inputs": {"report": str(args.report), "reportCacheKey": report.get("cacheKey")},
        "timelineMs": args.timeline_ms,
        "alignment": {**alignment, "trackMs": track_ms, "timelineMs": args.timeline_ms,
                      "tempoBpm": report.get("tempoBpm"),
                      "trackTitle": Path((report.get("source") or {}).get("path", "")).name},
        "phrases": phrases, "beatGridMs": grid, "suggestedBoundaries": boundaries,
        "budgetMap": parse_budget_map(args.budget_map),
        "tierRule": layout["rule"], "tierVocabulary": layout["tierVocabulary"],
        "fades": {"fadeInMs": args.fade_ms, "fadeOutStartMs": args.timeline_ms - args.fade_ms, "fadeOutMs": args.fade_ms},
        "discipline": "蓝图目标时间码是设计意图：G2 人审批准排版稿→TTS 实测时长才是事实；"
                      "G3 验证模式对账，偏差超限回 G2 改稿，禁止拉伸音频踩点",
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "BGM-节拍蓝图-v0.1.json"
    echo_path = args.output_dir / "BGM-节拍蓝图回显-v0.1.md"
    result["files"] = {"json": str(json_path), "echo": str(echo_path)}
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    echo_path.write_text(build_blueprint_card(args.report, result), encoding="utf-8")
    emit({"status": "completed", "mode": "blueprint", "offsetMs": alignment["offsetMs"],
          "phrases": len(phrases), "beats": len(grid), "json": str(json_path), "echo": str(echo_path)})
    return 0


def build_echo_card(report_path: Path, brief: dict, result: dict, args) -> str:
    alignment = result["alignment"]
    lines = [f"# BGM 对齐回显 — {alignment['trackTitle']}", ""]
    lines += [f"- 输入：分析报告 `{report_path.name}`（{alignment['tempoBpm']} BPM，轨长 {mmss(alignment['trackMs'])}）"
              f"× 配音清单 `{brief.get('projectId', '?')}`（{len(result['boundaries'])} 句）",
              f"- 成片时间轴：{mmss(args.timeline_ms)}；卡点吸附容差 ±{args.snap_tolerance_ms}ms", ""]
    lines += ["## 轨偏移建议", "",
              f"- **从音轨 {mmss(alignment['offsetMs'])} 起铺**（依据：{alignment['basis']}）"]
    if alignment["clampedDeviationMs"]:
        lines.append(f"- ⚠ 受音轨可用长度限制被夹取，偏差 {alignment['clampedDeviationMs']}ms")
    window = alignment["topSegmentOnTimeline"]
    lines += [f"- 能量最高段（轨 {mmss(alignment['topEnergySegment']['startMs'])}–{mmss(alignment['topEnergySegment']['endMs'])}，"
              f"均值 {alignment['topEnergySegment']['energyMean']:.3f}）落在成片 {mmss(window[0])}–{mmss(window[1])}，"
              f"高潮锚点句 = **{alignment['climaxAnchorSentence'] or '（无重叠句）'}**", ""]
    lines += ["## 句边界卡点吸附", "",
              "| 句 | 边界 | 成片位置 | 吸附卡点(轨→成片) | 偏差 |", "|---|---|---|---|---|"]
    for item in result["snapped"]:
        lines.append(f"| {item['sentenceId']} | {item['boundary']} | {mmss(item['boundaryMs'])} "
                     f"| {mmss(item['hitPointTrackMs'])} → {mmss(item['hitPointTimelineMs'])} "
                     f"| {item['deltaMs']:+d}ms |")
    if result["missed"]:
        lines += ["", f"**无卡点可用（偏差 > ±{args.snap_tolerance_ms}ms，保持口播原时值，不得为踩点变形）**："]
        for item in result["missed"]:
            lines.append(f"- {item['sentenceId']} {item['boundary']} @ {mmss(item['boundaryMs'])}：最近卡点距离 {item['nearestDistanceMs']}ms")
    layout = result["layout"]
    lines += ["", "## 乐句表（机器版，源：分析报告 energySegments × 轨偏移）", "",
              "| 乐句 | 音轨区间 | 成片区间 | 能量均值 | 档位草稿 | 覆盖句 |", "|---|---|---|---|---|---|"]
    for phrase in layout["phrasesOnTimeline"]:
        lines.append(f"| {phrase['phraseId']} | {mmss(phrase['trackStartMs'])}–{mmss(phrase['trackEndMs'])} "
                     f"| {mmss(phrase['timelineStartMs'])}–{mmss(phrase['timelineEndMs'])} "
                     f"| {phrase['energyMean']:.3f} | {phrase['layoutTierDraft']} "
                     f"| {'、'.join(phrase['coversSentences']) or '（无口播）'} |")
    lines += ["", "## 逐句排版档位（机械草稿，终审八列回显逐行可改）", "",
              "| 句 | 加权能量 | 草稿档位 |", "|---|---|---|"]
    for item in layout["perSentence"]:
        lines.append(f"| {item['sentenceId']} | {item['energyWeightedMean']:.3f} | {item['layoutTierDraft']} |")
    rule = layout["rule"]
    quantile_note = f"{rule['quantiles']}" + (f"（切点 {rule['cutoffs']}）" if rule["cutoffs"] else "（段能量无差异，全部回落为常规）")
    lines += ["", f"> 定档规则：成片所用段能量分位数 {quantile_note}；档位词表：{'/'.join(layout['tierVocabulary'])}", ""]
    lines += ["## ducking / 淡入淡出", "",
              f"- BGM 基底区间：{mmss(0)}–{mmss(args.timeline_ms)}；淡入 {mmss(args.fade_ms)}，"
              f"淡出 {mmss(args.timeline_ms - args.fade_ms)}–{mmss(args.timeline_ms)}",
              f"- 口播 ducking 区间：{len(result['ducking'])} 段（逐句，旁白优先压低 BGM）", ""]
    lines += ["## 产物", "",
              f"- 机器合同：`{result['files']['json']}`",
              f"- 本回显卡：`{result['files']['echo']}`", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, type=Path, help="BGM 分析报告 JSON (music_analyze.py output)")
    parser.add_argument("--voice-brief", type=Path, default=None,
                        help="alignment mode: narration manifest with sentence startMs/durationMs")
    parser.add_argument("--blueprint", action="store_true",
                        help="blueprint mode (N9): no script yet — emit beat grid, phrase windows and sentence budgets for G2 drafting")
    parser.add_argument("--timeline-ms", required=True, type=int, help="final video duration in ms")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--climax-sentence", default=None, help="alignment mode: sentenceId the top-energy passage should cover")
    parser.add_argument("--climax-position-ms", type=int, default=None,
                        help="blueprint mode: timeline position the energy peak should cover")
    parser.add_argument("--snap-tolerance-ms", type=int, default=150)
    parser.add_argument("--fade-ms", type=int, default=2000)
    parser.add_argument("--tier-quantiles", default="0.75,0.5,0.25",
                        help="layoutTier draft cutoffs as segment-energy quantiles high,mid,low (§6-④ adjustable)")
    parser.add_argument("--budget-map", default="4-6,5-7,6-8,8-12",
                        help="blueprint mode: seconds ranges per tier in order 快切,推进,常规,留白")
    args = parser.parse_args()

    if args.blueprint == (args.voice_brief is not None):
        fail_exit([{"field": "mode", "rule": "exactly one of --blueprint or --voice-brief is required"}])
    if args.blueprint and args.climax_sentence:
        fail_exit([{"field": "climaxSentence", "rule": "--climax-sentence belongs to alignment mode; blueprint uses --climax-position-ms"}])
    if not args.blueprint and args.climax_position_ms is not None:
        fail_exit([{"field": "climaxPositionMs", "rule": "--climax-position-ms belongs to blueprint mode"}])
    if args.climax_position_ms is not None and not 0 <= args.climax_position_ms <= args.timeline_ms:
        fail_exit([{"field": "climaxPositionMs", "rule": "must sit inside the timeline"}])
    if args.timeline_ms <= 0 or args.snap_tolerance_ms < 0 or args.fade_ms <= 0:
        fail_exit([{"field": "timelineMs/snapToleranceMs/fadeMs", "rule": "positive values required (tolerance ≥ 0)"}])
    report = load_json(args.report, "report")
    track_ms = (report.get("source") or {}).get("decodedDurationMs")
    segments = report.get("energySegments")
    hit_points = report.get("hitPoints")
    if not isinstance(track_ms, int) or not isinstance(segments, list) or not segments \
            or not isinstance(hit_points, list) or not hit_points:
        fail_exit([{"field": "report", "rule": "report needs source.decodedDurationMs, non-empty energySegments and hitPoints"}])
    if track_ms < args.timeline_ms:
        emit({"status": "blocked", "blockers": [{"type": "track_cannot_cover_timeline",
              "detail": f"track is {track_ms}ms but the timeline is {args.timeline_ms}ms; loop/fill is forbidden — restock a longer track or shorten the cut"}]})
        return 2

    if args.blueprint:
        return run_blueprint(args, report, track_ms)

    brief = load_json(args.voice_brief, "voiceBrief")
    tier_quantiles = parse_tier_quantiles(args.tier_quantiles)
    bounds = sentence_bounds(brief, args.timeline_ms)
    alignment = pick_offset(track_ms, args.timeline_ms, segments, bounds, args.climax_sentence)
    snapped, missed = snap_boundaries(bounds, hit_points, alignment["offsetMs"], args.timeline_ms, args.snap_tolerance_ms)
    shifted = shifted_segments(segments, alignment["offsetMs"])
    layout = build_layout(shifted, bounds, alignment["offsetMs"], args.timeline_ms, tier_quantiles)
    result = {
        "schemaVersion": SCHEMA_VERSION, "purpose": "bgm_alignment",
        "skill": "music-expert",
        "inputs": {"report": str(args.report), "voiceBrief": str(args.voice_brief),
                   "reportCacheKey": report.get("cacheKey"), "briefProjectId": brief.get("projectId")},
        "alignment": {**{key: alignment[key] for key in
                         ("offsetMs", "rawOffsetMs", "clampedDeviationMs", "basis", "topEnergySegment",
                          "topSegmentOnTimeline", "climaxAnchorSentence", "coveredSentences")},
                      "trackMs": track_ms, "timelineMs": args.timeline_ms,
                      "tempoBpm": report.get("tempoBpm"),
                      "trackTitle": Path((report.get("source") or {}).get("path", "")).name},
        "boundaries": bounds, "snapped": snapped, "missed": missed,
        "layout": layout,
        "ducking": [{"sentenceId": item["sentenceId"], "fromMs": item["startMs"], "toMs": item["endMs"]} for item in bounds],
        "fades": {"fadeInMs": args.fade_ms, "fadeOutStartMs": args.timeline_ms - args.fade_ms, "fadeOutMs": args.fade_ms},
        "discipline": "snapping is advisory only: narration durations are authoritative, never stretch or trim speech to hit accents",
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "BGM-对齐建议-v0.2.json"
    echo_path = args.output_dir / "BGM-对齐回显-v0.2.md"
    result["files"] = {"json": str(json_path), "echo": str(echo_path)}
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    echo_path.write_text(build_echo_card(args.report, brief, result, args), encoding="utf-8")
    tier_counts: dict[str, int] = {}
    for item in layout["perSentence"]:
        tier_counts[item["layoutTierDraft"]] = tier_counts.get(item["layoutTierDraft"], 0) + 1
    emit({"status": "completed", "offsetMs": alignment["offsetMs"],
          "climaxAnchor": alignment["climaxAnchorSentence"], "snapped": len(snapped), "missed": len(missed),
          "phrases": len(layout["phrasesOnTimeline"]), "tierDrafts": tier_counts,
          "json": str(json_path), "echo": str(echo_path)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
