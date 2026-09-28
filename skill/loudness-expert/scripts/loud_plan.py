"""响度专员唯一入口②：线性归一化规划（规划口径）。

用法：loud_plan.py --input <源> --output-dir <目录>
        （目标二选一，缺省不许猜：--profile video|podcast 或
          --target-lufs+--true-peak+--lra-target 三件套全给）
        [--project-id <ID>]
产物：《响度-归一化计划-v0.N.json》——loudnorm pass1 实测 + linear=true
前提对账。可行→逐字执行链 chain；不可行→blocked + 可修数值出路（提 TP/降目标/
先压缩）；天花板 ceilingLufs 永远给出（G2 配音披露的数据源）。
拦截口径：有问题就卡住（blocked 仍落盘摊开，exit 1），绝不静默回退 dynamic。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import loud_core  # noqa: E402


def resolve_profile(args) -> dict:
    """目标档显式化（⑧ 口径：不许从不知道哪里冒出来的默认值）。"""
    explicit = [args.target_lufs, args.true_peak, args.lra_target]
    given = sum(1 for value in explicit if value is not None)
    if args.profile and given:
        raise ValueError("--profile 与显式三件套只能二选一（防口径含混）")
    if given and given < 3:
        raise ValueError("显式目标必须三件套齐全：--target-lufs/--true-peak/--lra-target，缺一即拒（不许半默认）")
    if args.profile:
        if args.profile not in loud_core.PROFILES:
            raise ValueError("未知目标档 {0}，可选：{1}".format(
                args.profile, "/".join(sorted(loud_core.PROFILES))))
        return dict(loud_core.PROFILES[args.profile])
    if given == 3:
        return {"integratedLufs": args.target_lufs, "truePeakDbtp": args.true_peak,
                "lraTargetLu": args.lra_target}
    raise ValueError("必须显式给目标：--profile video|podcast 或 --target-lufs+--true-peak+--lra-target")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="响度线性归一化规划（先测后批）")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--project-id", default=None)
    parser.add_argument("--profile", default=None, choices=sorted(loud_core.PROFILES))
    parser.add_argument("--target-lufs", type=float, default=None)
    parser.add_argument("--true-peak", type=float, default=None)
    parser.add_argument("--lra-target", type=float, default=None)
    args = parser.parse_args(argv)

    try:
        profile = resolve_profile(args)
    except ValueError as exc:
        loud_core.emit({"status": "error", "error": str(exc)}, 1)

    src = Path(args.input)
    if not src.is_file():
        loud_core.emit({"status": "error", "error": "输入文件不存在: {0}".format(src)}, 1)
    if not loud_core.ffmpeg_available():
        loud_core.emit({"status": "capability_missing",
                        "capability": loud_core.capability_missing()}, 2)

    measured = loud_core.measure_loudnorm_pass1(src, profile)
    if measured is None:
        loud_core.emit({"status": "error",
                        "error": "loudnorm pass1 未产出实测 JSON（探测失败，非结果）"}, 1)

    verdict = loud_core.linear_feasibility(measured, profile)
    status = "ready" if verdict["feasible"] else "blocked_" + "+".join(verdict["blockedReasons"])

    out_path, version = loud_core.next_versioned(Path(args.output_dir),
                                                 "响度-归一化计划", ".json")
    doc = loud_core.artifact_header("loud_plan", args.project_id, src)
    doc.update({"version": version, "output": str(out_path), "status": status,
                "targetProfile": profile, "measured": measured,
                "gainDb": verdict["gainDb"], "estimatedTruePeak": verdict["estimatedTruePeak"],
                "ceilingLufs": verdict["ceilingLufs"],
                "blockedReasons": verdict["blockedReasons"], "exits": verdict["exits"],
                "chain": loud_core.linear_chain(profile, measured) if verdict["feasible"] else None,
                "chainNote": ("linear=true 前提已在本文件对账通过；执行者逐字使用 chain、"
                              "不许改参数。若执行环境实测与 inputI/inputTp 不符（源变了），"
                              "chain 即作废必须重规划——回退 dynamic 视同违规。"),
                "sha256": loud_core.sha256_file(src),
                "plannedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    loud_core.emit(doc, 0 if verdict["feasible"] else 1)


if __name__ == "__main__":
    main()
