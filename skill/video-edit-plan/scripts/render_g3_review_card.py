#!/usr/bin/env python3
"""Render a validated G3 final-review callback as a fixed Markdown card."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


VALIDATOR = Path(__file__).with_name("validate_g3_callback.py")
spec = importlib.util.spec_from_file_location("validate_g3_callback", VALIDATOR)
if spec is None or spec.loader is None:
    raise RuntimeError("could not load validate_g3_callback.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def mmss(ms: int) -> str:
    minutes, remainder = divmod(int(ms), 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{minutes:02}:{seconds:02}.{millis:03}"


def bgm_basis_block(basis: dict) -> list[str]:
    total = basis["snappedCount"] + basis["missedCount"]
    return [
        "## BGM 依据区",
        "",
        f"- 轨偏移：从音轨 {mmss(basis['trackOffsetMs'])} 起铺（机器对齐产物，改动请重跑 music_align）",
        f"- 卡点吸附：{basis['snappedCount']}/{total}（miss 保持原时值）｜逐句 ducking：{basis['duckedSentences']} 句全覆盖",
        f"- 时间轴：{mmss(basis['timelineMs'])}｜依据文件：`{basis['alignmentRef']}`（哈希见计划 bgmPlan）",
        "",
    ]


def render(callback: dict) -> str:
    has_basis = isinstance(callback.get("bgmBasis"), dict)
    lines = [
        "# G3 剪辑计划最终回显",
        "",
        "此卡由通过校验的 G3 最终回显数据生成。机器合同保留精确毫秒；下表的输出时间和源片区间为派生的人类可读时间码。",
        "",
    ]
    if has_basis:
        lines += bgm_basis_block(callback["bgmBasis"])
    lines += [
        "| " + " | ".join(validator.FINAL_HEADERS) + " |",
        "|" + "|".join("---" for _ in validator.FINAL_HEADERS) + "|",
    ]
    for row in callback["rows"]:
        bgm_cell = f"{row['bgmPhrase']} · {row['layoutTier']}档" if "layoutTier" in row else row["bgmPhrase"]
        values = [
            row["segmentId"],
            row["outputTimecode"],
            row["narrationText"],
            row["sourceTimecode"],
            row["observedVisuals"],
            f"{row['semanticStatus']} / {row['subjectStatus']} / {row['riskSummary']}",
            bgm_cell,
            row["transitionInstruction"],
        ]
        lines.append("| " + " | ".join(cell(value) for value in values) + " |")
    lines.extend(["", "请核对全表；确认无误后，使用精确确认串：`确认 G3`。", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--callback", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--alignment", type=Path, help="music-expert BGM-对齐建议-v0.2.json for card v0.2 verification")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    callback, plan = load(args.callback), load(args.plan)
    alignment = load(args.alignment) if args.alignment else None
    validator.validate_final(callback, plan, alignment)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(callback), encoding="utf-8")
    print(json.dumps({"status": "completed", "output": str(args.output), "rows": len(callback["rows"])}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "invalid", "error": str(error)}, ensure_ascii=True))
        raise SystemExit(2)
