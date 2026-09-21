#!/usr/bin/env python3
"""Deep-check a G3 plan's transition decisions against the handle-model contract.

唯一事实源：references/transition-contract.md。核心模型（用户 2026-09-21 拍板）：
- 音不动画面服从：成片输出网格是宪法，口播/字幕/BGM 坐标不因转场平移；
- 手柄回填：叠化吃切点两侧各 D/2 的源余量，段文件多切、网格不变；
- 缺料摊牌：手柄不足报出确切缺口毫秒与最大可行时长，出路归用户，G4 永不静默降级。

Batch style (issue ㉕): every violation is collected, never stop at the first.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

TRANSITION_MODES = {"硬切", "叠化", "黑场入", "黑场出", "抹开"}
TRANSITION_DURATION_MODES = {"叠化", "黑场入", "黑场出", "抹开"}
MIN_DURATION_MS = 100
MAX_DURATION_MS = 1500


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def source_identities(evidence: dict) -> dict:
    """assetId -> (source-identity key, durationMs), same shape as validate_g3_plan."""
    table = {}
    for entry in evidence.get("sourceEvidence", []):
        if not isinstance(entry, dict) or not isinstance(entry.get("assetId"), str):
            continue
        probe = entry.get("sourceProbe")
        duration = probe.get("durationMs") if isinstance(probe, dict) else None
        if not isinstance(duration, (int, float)) or isinstance(duration, bool):
            continue
        key = str(entry.get("sha256") or entry["assetId"]).lower()
        table[entry["assetId"]] = (key, int(duration))
    return table


def free_handles(segments: list, identities: dict) -> dict:
    """Per segmentId: ms of unused source before startMs / after endMs on its source identity.

    Same-source neighbour claims shrink the free zone (contract rule 4); the
    source file head/tail bounds the rest.
    """
    by_source = {}
    for segment in segments:
        info = identities.get(segment.get("assetId"))
        if not info:
            continue
        by_source.setdefault(info[0], []).append(segment)
    free = {}
    for _, group in by_source.items():
        ordered = sorted(group, key=lambda s: (s.get("startMs", 0), s.get("endMs", 0)))
        duration = identities[ordered[0].get("assetId", "")][1]
        for position, segment in enumerate(ordered):
            before = segment.get("startMs", 0) - (ordered[position - 1].get("endMs", 0) if position else 0)
            after = (ordered[position + 1].get("startMs", duration) if position + 1 < len(ordered) else duration) - segment.get("endMs", 0)
            identity_key = identities[segment["assetId"]][0]
            # 同段多次使用共享同一身份：取各次出现里最宽松的余量语义不适用，
            # 保守取最小值（任一次被占死就不能靠该源做转场）。
            existing = free.get(segment["segmentId"])
            candidate = {"identity": identity_key, "beforeMs": max(before, 0), "afterMs": max(after, 0)}
            if existing:
                candidate["beforeMs"] = min(existing["beforeMs"], candidate["beforeMs"])
                candidate["afterMs"] = min(existing["afterMs"], candidate["afterMs"])
            free[segment["segmentId"]] = candidate
    return free


def overlaps(window, other) -> int:
    return max(0, min(window[1], other[1]) - max(window[0], other[0]))


def validate_plan(plan: dict, evidence: dict, host_profile) -> dict:
    errors: list = []
    segments = plan.get("segments")
    if not isinstance(segments, list) or not segments:
        return {"status": "invalid", "errors": ["plan requires non-empty segments"]}
    ordered = sorted(segments, key=lambda s: (s.get("outputStartMs") if isinstance(s.get("outputStartMs"), int) else 0))

    # Grid invariant first: the check itself stands on a continuous 0..total grid.
    cursor = 0
    for segment in ordered:
        start, end = segment.get("outputStartMs"), segment.get("outputEndMs")
        if not isinstance(start, int) or not isinstance(end, int) or start != cursor or end <= start:
            errors.append(f"{segment.get('segmentId')} breaks the output grid ({start} != {cursor}) — 转场模型要求网格连续，先修复时间轴")
            cursor = end if isinstance(end, int) else cursor
            continue
        cursor = end
    total = cursor
    if isinstance(plan.get("timelineDurationMs"), int) and plan["timelineDurationMs"] != total:
        errors.append(f"timelineDurationMs {plan['timelineDurationMs']} != segment grid total {total}")

    identities = source_identities(evidence)
    handles = free_handles(ordered, identities)
    narration_windows = [(s.get("segmentId"), s.get("narrationStartMs"), s.get("narrationEndMs")) for s in ordered]
    cards = []
    packaging = plan.get("packagingDecisions")
    if isinstance(packaging, dict):
        cards = [(c.get("startMs"), c.get("endMs")) for c in packaging.get("chapterCards", []) if isinstance(c, dict)]

    transitions = []
    dissolve_used = any(s.get("transitionInstruction") == "叠化" for s in ordered)
    if dissolve_used:
        if host_profile is None:
            errors.append("计划含叠化但未传 --host-profile：先跑 transition_probe_host.py 生成《转场-宿主能力档》，无探测不声称（能力可以缺、事实不能编）")
        else:
            capabilities = host_profile.get("capabilities", {})
            xfade = host_profile.get("xfade", {})
            if not xfade.get("available") or not capabilities.get("dissolve"):
                errors.append("宿主能力档显示 xfade/dissolve 不可用：本宿主计划中的叠化全部 blocked，改选硬切或黑场，或换宿主重探")

    for position, segment in enumerate(ordered):
        segment_id = segment.get("segmentId")
        mode = segment.get("transitionInstruction")
        if mode is None or mode == "硬切":
            if segment.get("transitionDurationMs") is not None:
                errors.append(f"{segment_id} 硬切 must not carry transitionDurationMs")
            continue
        if mode not in TRANSITION_MODES:
            errors.append(f"{segment_id} transitionInstruction {mode!r} 不在词表（硬切/叠化/黑场入/黑场出/抹开-预留）")
            continue
        if mode == "抹开":
            errors.append(f"{segment_id} 抹开是预留档，第一批未开放（解锁须合同修订+宿主实测，见 transition-contract.md）")
            continue
        duration = segment.get("transitionDurationMs")
        if not isinstance(duration, int) or isinstance(duration, bool) or not MIN_DURATION_MS <= duration <= MAX_DURATION_MS:
            errors.append(f"{segment_id} 转场 {mode} 需整数 transitionDurationMs ∈ [{MIN_DURATION_MS},{MAX_DURATION_MS}]ms")
            continue
        start, end = segment.get("outputStartMs", 0), segment.get("outputEndMs", 0)
        last = position == len(ordered) - 1
        if mode == "黑场入" and position != 0:
            errors.append(f"{segment_id} 黑场入只允许在成片首段")
            continue
        if mode == "黑场出" and not last:
            errors.append(f"{segment_id} 黑场出只允许在成片末段")
            continue
        if mode == "叠化" and last:
            errors.append(f"{segment_id} 叠化是退场进入下一段的指令，不允许在末段（末段收束请用黑场出）")
            continue
        if mode == "黑场入":
            window = (start, start + duration)
        elif mode == "黑场出":
            window = (end - duration, end)
        else:
            half_before = duration // 2
            window = (end - half_before, end + (duration - half_before))
            next_segment = ordered[position + 1]
            need_after = duration // 2
            need_before = duration - duration // 2
            seg_duration = end - start
            next_duration = next_segment.get("outputEndMs", 0) - next_segment.get("outputStartMs", 0)
            if seg_duration < need_after or next_duration < need_before:
                errors.append(f"{segment_id}→{next_segment.get('segmentId')} 叠化 {duration}ms 需要两侧成片各留出 {duration // 2}/{duration - duration // 2}ms，但成片段长仅 {seg_duration}/{next_duration}ms")
            mine = handles.get(segment_id, {"afterMs": 0})
            theirs = handles.get(next_segment.get("segmentId"), {"beforeMs": 0})
            if mine.get("afterMs", 0) < need_after or theirs.get("beforeMs", 0) < need_before:
                feasible = 2 * min(mine.get("afterMs", 0), theirs.get("beforeMs", 0))
                errors.append(f"{segment_id}→{next_segment.get('segmentId')} 缺料摊牌：本侧手柄 {mine.get('afterMs', 0)}ms、对侧 {theirs.get('beforeMs', 0)}ms，"
                              f"叠化 {duration}ms 各需 {need_after}/{need_before}ms；最大可行 D={feasible}ms。出路：降硬切/挪切点/缩时长≤{feasible}ms（G4 永不静默降级）")
        if window[0] < 0 or window[1] > total:
            errors.append(f"{segment_id} 转场窗口 [{window[0]},{window[1]}) 超出成片网格 [0,{total})")
        for narration_id, narration_start, narration_end in narration_windows:
            if isinstance(narration_start, int) and isinstance(narration_end, int):
                hit = overlaps(window, (narration_start, narration_end))
                if hit:
                    errors.append(f"{segment_id} 转场窗口 [{window[0]},{window[1]}) 压住 {narration_id} 口播 {hit}ms——转场只能落在口播停顿里（红线：音不动画面服从）")
                    break
        for card_start, card_end in cards:
            if isinstance(card_start, int) and isinstance(card_end, int) and overlaps(window, (card_start, card_end)):
                errors.append(f"{segment_id} 转场窗口与章节卡 [{card_start},{card_end}) 交叠（包装决定为绝对网格）")
                break
        transitions.append({"boundary": f"{segment_id}→{ordered[position + 1].get('segmentId') if mode == '叠化' else '（成片边界）'}",
                            "type": mode, "durationMs": duration,
                            "windowMs": [window[0], window[1]],
                            "handlesMs": {"after": handles.get(segment_id, {}).get("afterMs"),
                                          "before": handles.get(ordered[position + 1]["segmentId"], {}).get("beforeMs")} if mode == "叠化" else None})

    if errors:
        return {"status": "invalid", "errors": errors}
    return {"status": "passed", "skill": "transition-expert", "purpose": "transition_plan_check",
            "checkedAt": now(), "timelineDurationMs": total, "gridInvariant": True,
            "transitions": transitions,
            "disclaimer": "通过=模型合法（词表/窗口/手柄/网格），不=批准：逐切点转场仍须 G3 回显卡人工批准"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path, help="G2 evidence JSON（sourceEvidence[].sourceProbe.durationMs 提供源余量事实）")
    parser.add_argument("--host-profile", type=Path, help="transition_probe_host.py 产物；计划含叠化时必传")
    args = parser.parse_args()
    plan, evidence = load(args.plan), load(args.evidence)
    host_profile = load(args.host_profile) if args.host_profile else None
    if host_profile is not None and (host_profile.get("skill") != "transition-expert" or host_profile.get("purpose") != "transition_host_profile"):
        print(json.dumps({"status": "invalid", "errors": ["--host-profile 不是 transition-expert 的 transition_host_profile 产物"]}, ensure_ascii=False))
        return 2
    report = validate_plan(plan, evidence, host_profile)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "invalid", "error": str(error)}, ensure_ascii=False))
        raise SystemExit(2)
