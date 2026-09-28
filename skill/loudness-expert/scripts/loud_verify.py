"""响度专员唯一入口③：成片验收审计（验收口径）。

用法：loud_verify.py --plan <响度-归一化计划-v0.N.json> --master <成片文件>
        --output-dir <目录> [--project-id <ID>] [--tolerance-lu <LU，默认=合同 1.0>]
产物：《响度-验收审计-v0.N.json》——独立 ebur128 复测 master 对账 plan 目标：
|ΔI| ≤ 容差 且 TP ≤ 上限+余量 → passed；否则 failed（点名数字与出路）。
纪律：plan 身份不符/plan 非 ready/文件缺失一律拒（exit 1）；容差是合同工程常数
并如实写进报告，不是隐藏默认。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import loud_core  # noqa: E402


def judge(plan_doc: dict, measured: dict, tolerance_lu: float) -> list:
    profile = plan_doc["targetProfile"]
    checks = []
    dev = measured["integratedLufs"] - profile["integratedLufs"]
    checks.append({"check": "integratedWithinTolerance",
                   "pass": abs(dev) <= tolerance_lu,
                   "detail": "实测 {0:.1f} vs 目标 {1:.1f}，偏差 {2:+.1f} LU（容差 ±{3} LU）".format(
                       measured["integratedLufs"], profile["integratedLufs"], dev, tolerance_lu)})
    tp_over = measured["truePeakDbtp"] - profile["truePeakDbtp"]
    checks.append({"check": "truePeakWithinCeiling",
                   "pass": tp_over <= loud_core.TP_SLACK_DB,
                   "detail": "实测 TP {0:.1f} vs 上限 {1:.1f} dBTP（防回退余量 {2}）".format(
                       measured["truePeakDbtp"], profile["truePeakDbtp"], loud_core.TP_SLACK_DB)})
    return checks


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="响度成片验收审计")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--master", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--project-id", default=None)
    parser.add_argument("--tolerance-lu", type=float, default=None,
                        help="覆盖合同容差（须给理由，报告如实记来源）")
    args = parser.parse_args(argv)

    plan_path = Path(args.plan)
    master_path = Path(args.master)
    if not plan_path.is_file():
        loud_core.emit({"status": "error", "error": "plan 文件不存在: {0}".format(plan_path)}, 1)
    if not master_path.is_file():
        loud_core.emit({"status": "error", "error": "master 文件不存在: {0}".format(master_path)}, 1)
    plan_doc = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan_doc.get("skill") != loud_core.SKILL_ID or plan_doc.get("purpose") != "loud_plan":
        loud_core.emit({"status": "error", "error": "plan 不是本专员的 loud_plan 产物（身份不符拒收）"}, 1)
    if plan_doc.get("status") != "ready":
        loud_core.emit({"status": "error",
                        "error": "plan status={0} 非 ready——blocked 的规划不许拿去验收，走 exits 出路后重规划".format(
                            plan_doc.get("status"))}, 1)
    if not loud_core.ffmpeg_available():
        loud_core.emit({"status": "capability_missing",
                        "capability": loud_core.capability_missing()}, 2)

    tolerance = args.tolerance_lu if args.tolerance_lu is not None else loud_core.DEFAULT_TOLERANCE_LU
    tolerance_source = "CLI 显式覆盖" if args.tolerance_lu is not None else "合同默认"

    measured = loud_core.measure_ebur128(master_path)
    if measured["integratedLufs"] is None or measured["truePeakDbtp"] is None:
        loud_core.emit({"status": "error", "error": "master ebur128 探测失败", "raw": measured}, 1)
    checks = judge(plan_doc, measured, tolerance)
    status = "passed" if all(item["pass"] for item in checks) else "failed"

    out_path, version = loud_core.next_versioned(Path(args.output_dir),
                                                 "响度-验收审计", ".json")
    doc = loud_core.artifact_header("loud_verify", args.project_id, master_path)
    doc.update({"version": version, "output": str(out_path), "status": status,
                "planRef": str(plan_path), "planVersion": plan_doc.get("version"),
                "toleranceLu": tolerance, "toleranceSource": tolerance_source,
                "tpSlackDb": loud_core.TP_SLACK_DB,
                "masterMeasured": measured, "checks": checks,
                "masterSha256": loud_core.sha256_file(master_path),
                "failNote": (None if status == "passed" else
                             "failed 不是重跑一次碰运气——偏差来自源天花板/混音口径/回退三成因，逐条排查见合同 §5"),
                "verifiedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    loud_core.emit(doc, 0 if status == "passed" else 1)


if __name__ == "__main__":
    main()
