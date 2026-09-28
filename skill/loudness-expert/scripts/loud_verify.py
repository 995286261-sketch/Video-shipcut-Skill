"""响度专员唯一入口③：成片验收审计（验收口径）。

用法：loud_verify.py --plan <响度-归一化计划-v0.N.json> --master <成片文件>
        --output-dir <目录> [--project-id <ID>] [--tolerance-lu <LU，默认=合同 1.0>]
        [--assembly-record <G4装配记录>]（blocked 档计划验收必带，丙分档口径）
产物：《响度-验收审计-v0.N.json》——独立 ebur128 复测 master 对账 plan 目标。
三态（响度接线批四 2026-09-28，与批三 G4 分档口径同源）：
- plan ready：|ΔI| ≤ 容差 且 TP ≤ 上限+余量 → passed，否则 failed（承诺过就得达标）。
- plan blocked_*（真 TTS 源常态）：必带 --assembly-record 且与 G4 记账逐字对账
  （loudness.planRef.sha256==本计划文件哈希、mode=controlled-dynamic、targetProfile 相等）；
  达标→passed；整段超容差但 TP 合规→**disclosed-exceedance**（G2 出路卡批准过的让步幅度
  如实落账，exit 1 提醒编排：必须进 G5 卡摊开+人工 acceptedWarnings，永不静默、
  也不假装拦死）；TP 超限→failed（限幅链路坏不是响度取舍，两档共同硬闸）。
纪律：plan 身份不符/状态乱造/绑定对不上/文件缺失一律拒；容差是合同工程常数
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
    # 浮点边界豁免（与 linear_feasibility 的 +1e-9 同款）：−1.2 实测对 −1.5 上限+0.3 余量
    # 在 IEEE754 里算出 0.30000000000000004，误判超峰（批四彩排真 master 实抓，2026-09-28）。
    checks.append({"check": "truePeakWithinCeiling",
                   "pass": tp_over <= loud_core.TP_SLACK_DB + 1e-9,
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
    parser.add_argument("--assembly-record", default=None,
                        help="G4 装配记录（blocked 档计划验收必带：loudness 块 planRef 哈希/mode/targetProfile 三项对账）")
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
    plan_status = str(plan_doc.get("status") or "")
    if plan_status != "ready" and not plan_status.startswith("blocked_"):
        loud_core.emit({"status": "error",
                        "error": "plan status={0} 既非 ready 也非 blocked_*——不可验收，重跑 loud_plan".format(plan_status)}, 1)
    assembly_binding = None
    if plan_status.startswith("blocked_"):
        # 丙分档批四兑现：blocked 的让步必须有 G4 记账且以受控动态档执行，三项对不上
        # 就是"验收拿的是另一份执行"——拒装，不替谁圆场。
        if not args.assembly_record:
            loud_core.emit({"status": "error",
                            "error": "blocked 档计划验收必须带 --assembly-record（G4 装配记录）——"
                                     "blocked 的让步要能对账到记账才可入册（批四丙口径）"}, 1)
        assembly_path = Path(args.assembly_record)
        if not assembly_path.is_file():
            loud_core.emit({"status": "error", "error": "装配记录文件不存在: {0}".format(assembly_path)}, 1)
        assembly = json.loads(assembly_path.read_text(encoding="utf-8-sig"))
        loud_block = assembly.get("loudness") if isinstance(assembly.get("loudness"), dict) else {}
        problems = []
        if str((loud_block.get("planRef") or {}).get("sha256") or "").upper() != loud_core.sha256_file(plan_path):
            problems.append("装配记录登记的计划文件哈希与本次验收计划不符（计划换过/装配拿错）")
        if loud_block.get("mode") != "controlled-dynamic":
            problems.append("装配记录执行档={0!r}，blocked 计划应为 controlled-dynamic".format(loud_block.get("mode")))
        if loud_block.get("targetProfile") != plan_doc.get("targetProfile"):
            problems.append("装配记录 targetProfile 与计划 targetProfile 不逐字相等")
        if problems:
            loud_core.emit({"status": "error", "error": "blocked 档验收绑定对账失败：" + "；".join(problems)}, 1)
        assembly_binding = {"path": str(assembly_path.resolve()), "sha256": loud_core.sha256_file(assembly_path)}
    if not loud_core.ffmpeg_available():
        loud_core.emit({"status": "capability_missing",
                        "capability": loud_core.capability_missing()}, 2)

    tolerance = args.tolerance_lu if args.tolerance_lu is not None else loud_core.DEFAULT_TOLERANCE_LU
    tolerance_source = "CLI 显式覆盖" if args.tolerance_lu is not None else "合同默认"

    measured = loud_core.measure_ebur128(master_path)
    if measured["integratedLufs"] is None or measured["truePeakDbtp"] is None:
        loud_core.emit({"status": "error", "error": "master ebur128 探测失败", "raw": measured}, 1)
    checks = judge(plan_doc, measured, tolerance)
    tp_pass = next(item["pass"] for item in checks if item["check"] == "truePeakWithinCeiling")
    if all(item["pass"] for item in checks):
        status = "passed"
    elif plan_status.startswith("blocked_") and tp_pass:
        status = "disclosed-exceedance"
    else:
        status = "failed"

    out_path, version = loud_core.next_versioned(Path(args.output_dir),
                                                 "响度-验收审计", ".json")
    doc = loud_core.artifact_header("loud_verify", args.project_id, master_path)
    doc.update({"version": version, "output": str(out_path), "status": status,
                "planRef": str(plan_path), "planVersion": plan_doc.get("version"),
                "planStatus": plan_status,
                "planRefSha256": loud_core.sha256_file(plan_path),
                "assemblyRef": assembly_binding,
                "targetProfile": plan_doc.get("targetProfile"),
                "toleranceLu": tolerance, "toleranceSource": tolerance_source,
                "tpSlackDb": loud_core.TP_SLACK_DB,
                "masterMeasured": measured, "checks": checks,
                "masterSha256": loud_core.sha256_file(master_path),
                "disclosureNote": (None if status != "disclosed-exceedance" else
                                   "blocked 档合法交付形态：整片实测超容差=G2 出路卡批准过的让步幅度"
                                   "（G4 记账已摊开并经用户确认）。G5 卡必须人话摊开本数字，"
                                   "人工 acceptedWarnings 点名响度后方可关单——永不静默。"),
                "failNote": (None if status == "passed" else
                             "failed 不是重跑一次碰运气——偏差来自源天花板/混音口径/回退三成因，逐条排查见合同 §5"
                             if status == "failed" else None),
                "verifiedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    loud_core.emit(doc, 0 if status == "passed" else 1)


if __name__ == "__main__":
    main()
