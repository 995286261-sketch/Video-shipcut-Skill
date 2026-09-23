#!/usr/bin/env python3
"""Derive the deterministic G4 transition-execution directive from an approved plan.

先过深检才有指令：本脚本复用 transition_validate_plan 的模型校验（含手柄/窗口/
偶数时长），任何 invalid 一律 blocked——G4 永远拿不到做不到的批准。
产物《G4-转场执行指令-v<M.N>.json》（版本自动递增、永不覆盖，issue ㉘）绑定计划+证据+能力档三哈希；g4_prepare 透传、
g4_render 按段扩切、g4_assemble 按 boundaries 链式 xfade。无转场批准也出产物
（boundaries/masterFades 全空），下游路径与旧管线一致。
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

VALIDATOR = Path(__file__).with_name("transition_validate_plan.py")
DIRECTIVE_PREFIX = "G4-转场执行指令"


def next_versioned_path(output_dir: Path, prefix: str) -> Path:
    """产物版本自动递增、永不覆盖（issue ㉘，sinjuku reopen 重跑现场）：扫描目录内
    既有 <prefix>-vM.N.json 取最大版本 +0.1；无则 v0.1。旧产物留盘作审计。
    （与 transition_probe_host 故意重复此 10 行——专员脚本保持零依赖单文件，
    同 LAYOUT_TIERS 双文件模式。）"""
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


def load_sibling_validator():
    spec = importlib.util.spec_from_file_location("transition_validate_plan", VALIDATOR)
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


def build_directive(plan: dict, evidence: dict, host_profile) -> dict:
    ordered = sorted(plan["segments"], key=lambda s: s.get("outputStartMs", 0))
    ids = [s["segmentId"] for s in ordered]
    extras = {segment_id: {"headExtraMs": 0, "tailExtraMs": 0} for segment_id in ids}
    position = {s.get("transitionInstruction") for s in ordered}
    dissolve_by_pair = {}
    for index, segment in enumerate(ordered[:-1]):
        if segment.get("transitionInstruction") == "叠化":
            duration = segment["transitionDurationMs"]
            half = duration // 2
            extras[segment["segmentId"]]["tailExtraMs"] += half
            extras[ordered[index + 1]["segmentId"]]["headExtraMs"] += duration - half
            dissolve_by_pair[(segment["segmentId"], ordered[index + 1]["segmentId"])] = duration
    master_fades = {"fadeInMs": 0, "fadeOutMs": 0}
    if ordered and ordered[0].get("transitionInstruction") == "黑场入":
        master_fades["fadeInMs"] = ordered[0]["transitionDurationMs"]
    if ordered and ordered[-1].get("transitionInstruction") == "黑场出":
        master_fades["fadeOutMs"] = ordered[-1]["transitionDurationMs"]

    boundaries = []
    run = None
    for index, segment in enumerate(ordered):
        file_len = (segment["outputEndMs"] - segment["outputStartMs"]
                    + extras[segment["segmentId"]]["headExtraMs"]
                    + extras[segment["segmentId"]]["tailExtraMs"])
        if run is None:
            run = file_len
            continue
        previous_id = ordered[index - 1]["segmentId"]
        duration = dissolve_by_pair.get((previous_id, segment["segmentId"]))
        if duration:
            # 词表"叠化"映射到 xfade fade（平滑交叉淡化）；xfade 自带 dissolve 是噪声抖动式，
            # 2026-09-22 验收003 ㉔ 实片裁决弃用（合同词表节）。
            boundaries.append({"fromSegmentId": previous_id, "toSegmentId": segment["segmentId"],
                               "transition": "fade", "durationMs": duration, "offsetMs": run - duration})
            run = run + file_len - duration
        else:
            run += file_len
    grid_total = sum(s["outputEndMs"] - s["outputStartMs"] for s in ordered)
    if run != grid_total:
        raise ValueError(f"网格不变性内部断言失败：xfade 链累计 {run}ms != 批准网格 {grid_total}ms")
    return {"schemaVersion": "0.1", "skill": "transition-expert", "purpose": "transition_directive",
            "gridInvariant": True, "timelineDurationMs": grid_total,
            "segments": [{"segmentId": segment_id, **extras[segment_id]} for segment_id in ids],
            "boundaries": boundaries, "masterFades": master_fades,
            "transitionVocabulary": sorted(str(value) for value in position if value)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--host-profile", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    plan, evidence = load(args.plan), load(args.evidence)
    host_profile = load(args.host_profile) if args.host_profile else None
    report = load_sibling_validator().validate_plan(plan, evidence, host_profile)
    if report.get("status") != "passed":
        print(json.dumps({"status": "blocked", "reason": "计划未通过转场深检，先修复再产指令",
                          "validation": report.get("errors", [report.get("error")])}, ensure_ascii=False))
        return 2
    directive = build_directive(plan, evidence, host_profile)
    directive["inputPlan"] = str(args.plan)
    directive["planSha256"] = sha256(args.plan)
    directive["inputEvidence"] = str(args.evidence)
    directive["evidenceSha256"] = sha256(args.evidence)
    directive["hostProfile"] = str(args.host_profile) if args.host_profile else None
    directive["hostProfileSha256"] = sha256(args.host_profile) if args.host_profile else None
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = next_versioned_path(args.output_dir, DIRECTIVE_PREFIX)
    out.write_text(json.dumps(directive, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "directive": str(out), "sha256": sha256(out),
                      "boundaries": len(directive["boundaries"]), "masterFades": directive["masterFades"],
                      "gridInvariant": True}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "invalid", "error": str(error)}, ensure_ascii=False))
        raise SystemExit(2)
