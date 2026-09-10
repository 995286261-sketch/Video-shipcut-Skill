#!/usr/bin/env python3
"""Build the BGM search-terms card: the Agent proposes terms, this script validates,
derives filters, and renders the machine contract + echo card (see
references/search-terms-contract.md).

The script NEVER invents terms or catalog hits — semantic derivation (口头偏好 >
主题翻译 > 风格简报锚定) is the Agent's job and must be justified per term via
--note "term=依据".  Terms matching the user's spoken preference are auto-tagged
``source: preference``.  Deterministic parts live here: dedupe, count bounds,
duration floor from --timeline-ms, bpmRange from --style-brief, and the JSON+card
that ``music_search_netease.py --terms-file`` consumes verbatim.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "0.1"
MIN_TERMS, MAX_TERMS = 1, 6


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True))


def fail(errors: list) -> None:
    emit({"status": "invalid", "errors": errors})
    raise SystemExit(2)


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--term", action="append", default=[], help="Agent-proposed search term (repeatable, 1-6)")
    parser.add_argument("--note", action="append", default=[], help='rationale as "term=推导依据" (required unless the term comes from --preference)')
    parser.add_argument("--preference", default=None, help="user's spoken preference text (highest-priority evidence)")
    parser.add_argument("--theme", default=None, help="G1 direction brief JSON path or free theme text")
    parser.add_argument("--style-brief", default=None, type=Path, help="optional style brief JSON (bpmRange anchor)")
    parser.add_argument("--timeline-ms", type=int, default=None, help="film duration the track must cover")
    parser.add_argument("--catalog", choices=("netease", "freesound"), default="netease")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    errors: list = []
    seen, terms = set(), []
    for raw in args.term:
        term = re.sub(r"\s+", " ", raw.strip())
        key = term.lower()
        if not term:
            continue
        if key in seen:
            continue
        seen.add(key)
        terms.append(term)
    if not (MIN_TERMS <= len(terms) <= MAX_TERMS):
        errors.append({"field": "term", "error": f"need {MIN_TERMS}-{MAX_TERMS} distinct terms, got {len(terms)}"})
    notes: dict[str, str] = {}
    for note in args.note:
        if "=" not in note:
            errors.append({"field": "note", "error": f'note must be "term=推导依据": {note!r}'})
            continue
        term, rationale = note.split("=", 1)
        notes[re.sub(r"\s+", " ", term.strip().lower())] = rationale.strip()
    preference = (args.preference or "").strip()
    preference_lower = preference.lower()

    records = []
    for term in terms:
        if preference and term.lower() in preference_lower:
            records.append({"term": term, "rationale": f"用户口头偏好原词：{preference}", "source": "preference"})
            continue
        rationale = notes.get(term.lower())
        if not rationale:
            errors.append({"field": "note", "error": f"term {term!r} lacks --note rationale (contract: 逐词写明推导依据)"})
            continue
        source = "brief" if args.style_brief and re.search(r"bpm|能量|简报", rationale) else "theme"
        records.append({"term": term, "rationale": rationale, "source": source})

    filters: dict = {"durationMinSec": None, "durationMaxSec": None, "bpmRange": None}
    if args.timeline_ms is not None:
        if args.timeline_ms <= 0:
            errors.append({"field": "timelineMs", "error": "must be positive"})
        else:
            filters["durationMinSec"] = math.ceil(args.timeline_ms / 1000)
    if args.style_brief is not None:
        try:
            brief = load_json(args.style_brief)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            errors.append({"field": "styleBrief", "error": str(error)[:200]})
            brief = None
        if brief is not None:
            range_value = brief.get("bpmRange")
            if isinstance(range_value, list) and len(range_value) == 2:
                filters["bpmRange"] = [float(range_value[0]), float(range_value[1])]
            else:
                errors.append({"field": "styleBrief", "error": "brief carries no bpmRange"})
    theme_ref = None
    if args.theme:
        theme_ref = args.theme if Path(args.theme).is_file() else None
    if errors:
        fail(errors)

    payload = {
        "schemaVersion": SCHEMA_VERSION, "skill": "music-expert", "purpose": "bgm_search_terms",
        "catalog": args.catalog,
        "inputs": {"preference": preference or None, "themeRef": theme_ref, "themeText": None if theme_ref else args.theme,
                   "styleBriefRef": str(args.style_brief) if args.style_brief else None},
        "terms": records, "filters": filters,
        "distributionBoundary": "internal_test", "retrievedAt": now(),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    terms_path = args.output_dir / "BGM-检索词-v0.1.json"
    terms_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = ["# BGM 检索词卡 v0.1", "",
             f"- 目录：{args.catalog}｜分发边界：internal_test｜推导优先级：口头偏好 ＞ 主题翻译 ＞ 风格简报锚定",
             f"- 输入：偏好={preference or '无'}｜主题={args.theme or '无'}｜简报={str(args.style_brief) if args.style_brief else '无'}｜时间线={str(args.timeline_ms) + 'ms' if args.timeline_ms else '无'}",
             "", "| # | 检索词 | 来源 | 推导依据 |", "|---|---|---|---|"]
    for index, record in enumerate(records, 1):
        lines.append(f"| {index} | {record['term']} | {record['source']} | {record['rationale']} |")
    filter_bits = []
    if filters["durationMinSec"]:
        filter_bits.append(f"时长下限 {filters['durationMinSec']}s（轨必须盖住成片）")
    if filters["bpmRange"]:
        filter_bits.append(f"BPM {filters['bpmRange'][0]:.0f}–{filters['bpmRange'][1]:.0f}（简报锚定，进推荐打分）")
    lines += ["", f"- 过滤推导：{'；'.join(filter_bits) if filter_bits else '无'}",
              "- 纪律：词由 Agent 推导、脚本不编造曲库命中；改词=重跑本脚本；**检索词卡不设门禁口令**，真正的门禁是候选池上的「你挑一首」；网易云候选一律 uncleared-platform-catalog，试听件只用于选型。", "",
              f"- 机器合同：{terms_path}", f"- 消费：`music_search_netease.py --terms-file {terms_path}`"]
    echo_path = args.output_dir / "BGM-检索词回显-v0.1.md"
    echo_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    emit({"status": "completed", "terms": len(records), "contract": str(terms_path), "echo": str(echo_path),
          "filters": filters})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
