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


def transition_cell(row: dict) -> str:
    mode = row["transitionInstruction"]
    duration = row.get("transitionDurationMs")
    return f"{mode} · {mmss(duration)}" if isinstance(duration, int) else mode


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


def preview_block(manifest: dict, manifest_path: Path, card_path: Path) -> list[str]:
    """转场试装预览区（批②门禁的展示面）：逐边界一链一窗口，双击即看。"""
    lines = ["## 转场试装预览（先看后批）", ""]
    lines.append("小样=按本卡批准参数从源素材实渲染，混合公式与成片逐字同式（代码同源）；"
                 "**纯画面无声**——配音/BGM 混音属 G4，节奏以口播稿与乐句表为准；"
                 "小样不复现源字幕遮蔽等包装层处理，只验转场观感。")
    lines.append("")
    card_dir = card_path.parent
    for entry in manifest.get("previews", []):
        clip = (manifest_path.parent / str(entry["file"])).resolve()
        try:
            link = clip.relative_to(card_dir.resolve()).as_posix()
        except ValueError:
            link = clip.as_posix()
        window = entry["windowMs"]
        lines.append(
            f"- {entry['boundary']} ｜ {entry['type']} · {mmss(entry['durationMs'])} ｜ "
            f"成片窗口 {mmss(window[0])}–{mmss(window[1])} ｜ ▶ [{entry['file']}]({link})（无声）")
    lines += ["", f"清单：`{manifest_path}`（哈希绑定当前计划，计划改版即失效需重跑）", ""]
    return lines


def waiver_block(waiver: dict) -> list[str]:
    return [
        "## 转场试装预览（能力豁免披露）",
        "",
        f"- {waiver.get('disclosure', '本机无法生成预览：你批准的是未见过的效果')}",
        f"- 原因：{waiver.get('reason', '未给出')}",
        "",
        "批准本卡即表示你在**没有小样**的情况下接受上述转场参数；成片观感核对仍走 G4 回放必检帧。",
        "",
    ]


def render(callback: dict, manifest: dict | None = None, manifest_path: Path | None = None,
           card_path: Path | None = None) -> str:
    has_basis = isinstance(callback.get("bgmBasis"), dict)
    has_transitions = any(row.get("transitionInstruction") not in (None, "硬切") for row in callback.get("rows", []))
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
            transition_cell(row),
        ]
        lines.append("| " + " | ".join(cell(value) for value in values) + " |")
    lines.append("")
    if has_transitions and isinstance(callback.get("transitionPreviewWaiver"), dict):
        lines += waiver_block(callback["transitionPreviewWaiver"])
    elif has_transitions and manifest is not None and manifest_path is not None and card_path is not None:
        lines += preview_block(manifest, manifest_path, card_path)
    lines.extend(["请核对全表；确认无误后，使用精确确认串：`确认 G3`。", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--callback", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--alignment", type=Path, help="music-expert BGM-对齐建议-v0.2.json for card v0.2 verification")
    parser.add_argument("--preview", type=Path, help="《转场-预览清单-vM.N.json》；计划含转场时必传（豁免披露除外）")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    callback, plan = load(args.callback), load(args.plan)
    alignment = load(args.alignment) if args.alignment else None
    preview = load(args.preview) if args.preview else None
    validator.validate_final(callback, plan, alignment,
                             plan_path=args.plan, preview_path=args.preview, preview=preview)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(callback, preview, args.preview, args.output), encoding="utf-8")
    print(json.dumps({"status": "completed", "output": str(args.output), "rows": len(callback["rows"])}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "invalid", "error": str(error)}, ensure_ascii=True))
        raise SystemExit(2)
