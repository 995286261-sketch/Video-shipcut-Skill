#!/usr/bin/env python3
"""Validate structured G3 review callback data before rendering Markdown."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


FINAL_HEADERS = [
    "片段 ID", "输出时间", "对应口播", "源片区间", "用途 / 实际画面观察",
    "语义匹配 / 主体状态 / 风险", "BGM 乐句", "转场指令",
]
SELECTION_HEADERS = [
    "口播槽位 ID", "输出时间", "对应口播", "候选 ID / 候选范围",
    "实际画面观察", "语义结论 / 风险", "下一步",
]
PLACEHOLDER = re.compile(r"未生成|待缩窄|候选|待定|\bnone\b|^无$", re.IGNORECASE)
# Shared controlled vocabulary with validate_g3_plan.py / music_align v0.2.
LAYOUT_TIERS = {"快切", "推进", "常规", "留白"}
# Transition vocabulary shared with validate_g3_plan.py and
# skill/transition-expert/references/transition-contract.md (duplicated by design).
TRANSITION_MODES = {"硬切", "叠化", "黑场入", "黑场出", "抹开"}
BGM_BASIS_FIELDS = ("alignmentRef", "trackOffsetMs", "timelineMs", "snappedCount", "missedCount", "duckedSentences")


def normalized_ref(value: str) -> str:
    return value.replace("\\", "/").lstrip("./")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def transition_boundary_expectations(segments: list) -> dict:
    """label -> durationMs（叠化=from→to；黑场入=成片首；黑场出=成片尾）。"""
    ordered = sorted(segments, key=lambda s: (s.get("outputStartMs") or 0))
    expected = {}
    for position, segment in enumerate(ordered):
        mode = segment.get("transitionInstruction")
        duration = segment.get("transitionDurationMs")
        if mode == "叠化" and position + 1 < len(ordered):
            expected[f"{segment['segmentId']}→{ordered[position + 1]['segmentId']}"] = duration
        elif mode == "黑场入" and position == 0:
            expected["成片首"] = duration
        elif mode == "黑场出" and position == len(ordered) - 1:
            expected["成片尾"] = duration
    return expected


def validate_transition_preview(callback: dict, plan_path: Path, plan: dict,
                                preview_path: Path, preview: dict) -> None:
    """硬门禁（用户 09-23 裁决）：计划含非硬切转场 → 卡必挂预览清单，
    逐边界一一对应、清单 planSha256==当前计划（改版即 stale）、小样文件
    sha 匹配；唯一豁免=blocked_previews 披露块原样入卡。不许静默跳卡。"""
    expected = transition_boundary_expectations(plan.get("segments", []))
    ref = callback.get("transitionPreviewRef")
    waiver = callback.get("transitionPreviewWaiver")
    if not expected:
        if ref or waiver:
            fail("无转场计划不得挂预览或豁免（转场=无，预览区应为空）")
        return
    if ref and waiver:
        fail("transitionPreviewRef 与 transitionPreviewWaiver 二选一，不得同时在场")
    if waiver:
        if not isinstance(waiver, dict) or waiver.get("status") != "blocked_previews" \
                or not str(waiver.get("disclosure", "")).strip():
            fail("豁免只认 transition_preview 的 blocked_previews 块原文（须含 status 与披露句）——渲染失败也要如实入卡，不许静默跳卡")
        return
    if not ref:
        fail(f"转场试装预览硬门禁：以下切点未附预览且无豁免披露：{sorted(expected)}——"
             f"先看后批；无 ffmpeg 等能力缺失走 blocked_previews 披露，不许静默跳卡")
    if preview is None or preview_path is None:
        fail("callback 引用了 transitionPreviewRef：必须同传 --preview <转场-预览清单.json> 供对账")
    if normalized_ref(str(ref)) != normalized_ref(str(preview_path)):
        fail("卡上 transitionPreviewRef 与 --preview 传入的清单不是同一文件")
    if preview.get("skill") != "transition-expert" or preview.get("purpose") != "transition_preview":
        fail("--preview 不是 transition_preview 的清单产物")
    if preview.get("audio") is not False:
        fail("预览清单未声明 audio:false——小样必须纯画面无声（用户裁决），带声内容属 G4 混音层")
    if preview.get("planSha256") != sha256_file(plan_path):
        fail("预览清单对应的是另一版计划（stale）：计划改过一笔就必须重跑 transition_preview，看旧样批新案=幻觉")
    entries = {str(item.get("boundary")): item for item in preview.get("previews", [])}
    if set(entries) != set(expected):
        fail(f"预览与转场边界不一一对应：缺 {sorted(set(expected) - set(entries))}、"
             f"多 {sorted(set(entries) - set(expected))}（逐切点各一条，先看后批）")
    for label, duration in expected.items():
        item = entries[label]
        if duration is not None and item.get("durationMs") != duration:
            fail(f"{label} 预览的 durationMs {item.get('durationMs')} != 计划 {duration}（样与案不符）")
        clip = preview_path.parent / str(item.get("file"))
        if not item.get("file") or not clip.exists():
            fail(f"{label} 预览小样文件缺失：{item.get('file')}")
        if sha256_file(clip) != item.get("sha256"):
            fail(f"{label} 预览小样与清单哈希不符（被改动？）：{clip.name}")


def fail(message: str) -> None:
    raise ValueError(message)


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        fail(f"{path.name} must contain a JSON object")
    return value


def nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        fail(f"{label} must be a non-empty string")
    return value.strip()


def format_review_timecode(milliseconds: int) -> str:
    if not isinstance(milliseconds, int) or milliseconds < 0:
        fail("timecode milliseconds must be a non-negative integer")
    minutes, remainder = divmod(milliseconds, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{minutes:02}:{seconds:02}.{millis:03}"


def format_review_range(start_ms: int, end_ms: int) -> str:
    return f"{format_review_timecode(start_ms)}–{format_review_timecode(end_ms)}"


def contains_placeholder(value: object) -> bool:
    if isinstance(value, str):
        return bool(PLACEHOLDER.search(value.strip()))
    if isinstance(value, dict):
        return any(contains_placeholder(item) for item in value.values())
    if isinstance(value, list):
        return any(contains_placeholder(item) for item in value)
    return False


def validate_bgm_basis(callback: dict, plan: dict, alignment: dict) -> None:
    """Card v0.2: when the plan consumes a machine BGM alignment, the callback
    must be schemaVersion 0.2 with a bgmBasis block whose numbers equal both
    the plan and the alignment artifact — the card cannot disagree."""
    if callback.get("schemaVersion") != "0.2":
        fail("plans with bgmPlan require callback schemaVersion 0.2 (BGM basis card)")
    basis = callback.get("bgmBasis")
    if not isinstance(basis, dict):
        fail("schemaVersion 0.2 final_review requires a bgmBasis block")
    missing = [field for field in BGM_BASIS_FIELDS if field not in basis]
    if missing:
        fail(f"bgmBasis missing fields: {', '.join(missing)}")
    bgm_plan = plan.get("bgmPlan", {})
    if basis["trackOffsetMs"] != bgm_plan.get("trackOffsetMs"):
        fail("bgmBasis.trackOffsetMs must equal the plan's bgmPlan.trackOffsetMs")
    if basis["timelineMs"] != plan.get("timelineDurationMs"):
        fail("bgmBasis.timelineMs must equal plan timelineDurationMs")
    if normalized_ref(str(basis["alignmentRef"])) != normalized_ref(str(bgm_plan.get("alignmentRef", ""))):
        fail("bgmBasis.alignmentRef must identify the same alignment artifact as bgmPlan.alignmentRef")
    inner = alignment.get("alignment", {})
    if basis["trackOffsetMs"] != inner.get("offsetMs") or basis["timelineMs"] != inner.get("timelineMs"):
        fail("bgmBasis offset/timeline must equal the alignment artifact numbers")
    if basis["snappedCount"] != len(alignment.get("snapped", [])) or basis["missedCount"] != len(alignment.get("missed", [])):
        fail("bgmBasis snap counts must equal the alignment artifact (rerun music_align instead of editing the card)")
    if basis["duckedSentences"] != len(alignment.get("ducking", [])):
        fail("bgmBasis.duckedSentences must equal the alignment artifact ducking count")


def validate_final(callback: dict, plan: dict, alignment: dict | None = None, *,
                   plan_path: Path | None = None, preview_path: Path | None = None,
                   preview: dict | None = None) -> int:
    if callback.get("columns") != FINAL_HEADERS:
        fail("final_review columns must exactly match the fixed eight-column template and order")
    if callback.get("projectId") != plan.get("projectId"):
        fail("callback projectId must match plan projectId")
    has_bgm = isinstance(plan.get("bgmPlan"), dict)
    if has_bgm:
        if alignment is None:
            fail("schemaVersion 0.2 final_review requires --alignment to verify the BGM basis block")
        validate_bgm_basis(callback, plan, alignment)
    elif callback.get("schemaVersion") == "0.2" and callback.get("bgmBasis"):
        fail("bgmBasis is only allowed when the plan carries bgmPlan")
    duration = callback.get("durationMs")
    if not isinstance(duration, int) or duration <= 0:
        fail("final_review requires positive integer durationMs")
    rows = callback.get("rows")
    if not isinstance(rows, list) or not rows:
        fail("final_review requires non-empty rows")
    segments = plan.get("segments")
    if not isinstance(segments, list) or not segments:
        fail("plan requires non-empty segments")
    plan_by_id = {segment.get("segmentId"): segment for segment in segments}
    if len(plan_by_id) != len(segments) or None in plan_by_id:
        fail("plan segmentId values must be unique and non-empty")
    if len(rows) != len(segments):
        fail("final_review must contain exactly one row for every plan segment")

    previous_end, row_ids = 0, set()
    required = {
        "segmentId", "outputStartMs", "outputEndMs", "narrationText", "sourceStartMs",
        "sourceEndMs", "outputTimecode", "sourceTimecode", "observedVisuals", "semanticStatus", "subjectStatus", "riskSummary",
        "bgmPhrase", "transitionInstruction",
    }
    for row in rows:
        if not isinstance(row, dict):
            fail("each final_review row must be an object")
        missing = sorted(required - set(row))
        if missing:
            fail(f"final_review row missing required fields: {', '.join(missing)}")
        if contains_placeholder(row):
            fail("final_review cannot contain candidate or unresolved placeholder text")
        segment_id = nonempty(row["segmentId"], "segmentId")
        if not re.fullmatch(r"seg-[A-Za-z0-9_-]+", segment_id):
            fail(f"final_review segmentId must be executable seg-xxx: {segment_id}")
        if segment_id in row_ids or segment_id not in plan_by_id:
            fail(f"final_review segmentId must map once to a plan segment: {segment_id}")
        row_ids.add(segment_id)
        for key in ("outputStartMs", "outputEndMs", "sourceStartMs", "sourceEndMs"):
            if not isinstance(row[key], int):
                fail(f"{segment_id} {key} must be an integer")
        if row["outputStartMs"] != previous_end or row["outputEndMs"] <= row["outputStartMs"]:
            fail(f"{segment_id} output timeline must be continuous and non-overlapping")
        previous_end = row["outputEndMs"]
        if row["sourceEndMs"] <= row["sourceStartMs"]:
            fail(f"{segment_id} source range must have exact increasing cut points")
        if row["outputTimecode"] != format_review_range(row["outputStartMs"], row["outputEndMs"]):
            fail(f"{segment_id} outputTimecode must exactly match output millisecond cut points")
        if row["sourceTimecode"] != format_review_range(row["sourceStartMs"], row["sourceEndMs"]):
            fail(f"{segment_id} sourceTimecode must exactly match source millisecond cut points")
        for key in ("narrationText", "observedVisuals", "subjectStatus", "riskSummary", "bgmPhrase", "transitionInstruction"):
            nonempty(row[key], f"{segment_id} {key}")
        if row["semanticStatus"] not in {"direct_match", "not_applicable"}:
            fail(f"{segment_id} final_review semanticStatus must be direct_match or not_applicable")
        plan_segment = plan_by_id[segment_id]
        if (row["outputStartMs"], row["outputEndMs"], row["sourceStartMs"], row["sourceEndMs"]) != (
            plan_segment.get("outputStartMs"), plan_segment.get("outputEndMs"),
            plan_segment.get("startMs"), plan_segment.get("endMs"),
        ):
            fail(f"{segment_id} callback cut points must exactly match the plan")
        if has_bgm:
            tier = row.get("layoutTier")
            if tier not in LAYOUT_TIERS:
                fail(f"{segment_id} layoutTier must be one of 快切/推进/常规/留白")
            if tier != plan_segment.get("layoutTier"):
                fail(f"{segment_id} callback layoutTier must equal the plan segment's layoutTier")
        # 002 挂空合同修复批：卡上第 8 列必须逐字等于计划侧字段（缺省=硬切）。
        # "叠化/硬切按 G4 微调"这类含糊句从此进不了批准卡——批准什么就执行什么。
        if row["transitionInstruction"] not in TRANSITION_MODES:
            fail(f"{segment_id} transitionInstruction must be one of 硬切/叠化/黑场入/黑场出"
                 f"（抹开=预留未开放）；复合或含糊指令一律拒绝")
        plan_transition = plan_segment.get("transitionInstruction") or "硬切"
        if row["transitionInstruction"] != plan_transition:
            fail(f"{segment_id} callback transitionInstruction must equal the plan segment's（计划缺省即硬切）")
        if plan_transition != "硬切" and row.get("transitionDurationMs") != plan_segment.get("transitionDurationMs"):
            fail(f"{segment_id} callback transitionDurationMs must equal the plan's transitionDurationMs")
        if plan_segment.get("visualVerification", {}).get("status") != "verified":
            fail(f"{segment_id} requires verified visualVerification in the plan")
        if plan_segment.get("semanticAlignment", {}).get("status") not in {"direct_match", "not_applicable"}:
            fail(f"{segment_id} plan semanticAlignment blocks final_review")
    if previous_end != duration:
        fail("final_review rows must continuously cover 0 through durationMs")
    if set(plan_by_id) != row_ids:
        fail("final_review must include every plan segment exactly once")
    if plan_path is None:
        # 兼容旧调用方（无文件路径无法核对 planSha256）：预览门禁必须走 CLI/渲染入口。
        if transition_boundary_expectations(plan.get("segments", [])) and callback.get("transitionPreviewWaiver") is None \
                and not callback.get("transitionPreviewRef"):
            fail("转场试装预览硬门禁：含转场计划的校验必须经 --plan 文件路径与 --preview 清单进行")
    else:
        validate_transition_preview(callback, plan_path, plan, preview_path, preview)
    return len(rows)


def validate_selection(callback: dict) -> int:
    if callback.get("columns") != SELECTION_HEADERS:
        fail("semantic_selection_review columns must match its fixed template and order")
    rows = callback.get("rows")
    if not isinstance(rows, list) or not rows:
        fail("semantic_selection_review requires non-empty rows")
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--callback", required=True, type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--alignment", type=Path, help="music-expert BGM-对齐建议-v0.2.json (required for card v0.2 with bgmBasis)")
    parser.add_argument("--preview", type=Path, help="transition_preview 的《转场-预览清单-vM.N.json》（计划含转场时必传，或以卡上豁免披露放行）")
    args = parser.parse_args()
    callback = load(args.callback)
    if callback.get("schemaVersion") not in {"0.1", "0.2"} or callback.get("node") != "G3":
        fail("callback must be a G3 schemaVersion 0.1 or 0.2 artifact")
    alignment = load(args.alignment) if args.alignment else None
    preview = load(args.preview) if args.preview else None
    callback_type = callback.get("callbackType")
    if callback_type == "final_review":
        if not args.plan:
            fail("final_review requires --plan for cross-checking")
        count = validate_final(callback, load(args.plan), alignment,
                               plan_path=args.plan, preview_path=args.preview, preview=preview)
    elif callback_type == "semantic_selection_review":
        if args.plan or alignment:
            fail("semantic_selection_review must not be presented as a final plan callback")
        count = validate_selection(callback)
    else:
        fail("callbackType must be final_review or semantic_selection_review")
    print(json.dumps({"status": "completed", "callbackType": callback_type, "rows": count}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "invalid", "error": str(error)}, ensure_ascii=True))
        raise SystemExit(2)
