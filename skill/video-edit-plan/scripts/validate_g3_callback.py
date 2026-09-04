#!/usr/bin/env python3
"""Validate structured G3 review callback data before rendering Markdown."""
from __future__ import annotations

import argparse
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


def contains_placeholder(value: object) -> bool:
    if isinstance(value, str):
        return bool(PLACEHOLDER.search(value.strip()))
    if isinstance(value, dict):
        return any(contains_placeholder(item) for item in value.values())
    if isinstance(value, list):
        return any(contains_placeholder(item) for item in value)
    return False


def validate_final(callback: dict, plan: dict) -> int:
    if callback.get("columns") != FINAL_HEADERS:
        fail("final_review columns must exactly match the fixed eight-column template and order")
    if callback.get("projectId") != plan.get("projectId"):
        fail("callback projectId must match plan projectId")
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
        "sourceEndMs", "observedVisuals", "semanticStatus", "subjectStatus", "riskSummary",
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
        if plan_segment.get("visualVerification", {}).get("status") != "verified":
            fail(f"{segment_id} requires verified visualVerification in the plan")
        if plan_segment.get("semanticAlignment", {}).get("status") not in {"direct_match", "not_applicable"}:
            fail(f"{segment_id} plan semanticAlignment blocks final_review")
    if previous_end != duration:
        fail("final_review rows must continuously cover 0 through durationMs")
    if set(plan_by_id) != row_ids:
        fail("final_review must include every plan segment exactly once")
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
    args = parser.parse_args()
    callback = load(args.callback)
    if callback.get("schemaVersion") != "0.1" or callback.get("node") != "G3":
        fail("callback must be a G3 schemaVersion 0.1 artifact")
    callback_type = callback.get("callbackType")
    if callback_type == "final_review":
        if not args.plan:
            fail("final_review requires --plan for cross-checking")
        count = validate_final(callback, load(args.plan))
    elif callback_type == "semantic_selection_review":
        if args.plan:
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
