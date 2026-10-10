#!/usr/bin/env python3
"""G4 混音预检（banshee-intro-001 台账⑦，甲案用户 2026-10-10 拍板）。

问题：BGM 床深与 duck 深度是 §6-② 授权 G4 执行层自定的参数，但从来没有任何工序
预检过"按这组参数混完整片，主轨 LUFS 与真峰落在哪"——banshee 首跑因此把问题拖到
全片渲染之后的 G5 验收才暴露（主轨 −15.3 对目标 −14.0，超 ±1.0 容差），回炉代价=整条 G4 重做。
本次实测证明预检极便宜：只混音频、链路与装配逐字同源，整条时间轴每种组合几秒测完。

做法：本脚本调用 g4_assemble 的同一组函数（混音图构建、响度计划装载与分档链展开、
ebur128 口径解析、合同 §3 闸常数），对"口播+BGM"做只混音频的实测——
不是复刻一条平行链（复刻=第二事实源=幻觉面，转场试装预览同型纪律）。合同自带床/duck
组合必测（合同组合行，装配闸认这一行），另有候选组合入参可重复附加，
供编排调参搜索；机器只测量与判定，选哪组永远是编排的 §6-② 决策。

判定口径与 G5 验收闸同源（避免"预检过了 G5 又挂"的第三次命运）：综合响度对
响度计划目标档的容差默认 ±1.0 LU（合同 §3，容差入参可覆盖并如实落账）；
真峰上限+0.3 dB 余量两档共同硬闸。分档纪律与纯口播闸对称：ready（linear-verbatim）
超差=failed 不许去渲染；blocked（controlled-dynamic）综合超差=disclosed-exceedance，
可进装配但必须摊上 G4 回显卡，永不静默。LRA 只记录不判（验收闸领地不变）。

产物是装配闸的绑定凭证：g4_assemble 对报告做全量对账（口播、BGM、合同、计划四件
哈希、时间轴、目标档、容差、档位、合同组合行在场且参数逐字一致），任一漂移=过期报告罢工。
报告名带版本、拒绝覆盖——同版覆盖曾被批准文件的教训（台账⑥实跑插曲）不在本件重演。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g4_assemble as asm

LRA_PATTERN = re.compile(r"LRA:\s+(-?\d+\.?\d*)\s*LU")


def parse_lra(text: str) -> float | None:
    matches = LRA_PATTERN.findall(text)
    if not matches:
        return None
    value = float(matches[-1])
    return None if value <= -70.0 else value


def build_precheck_graph(contract_variant: dict, narration_pre: str | None) -> str:
    """同源红线：混音图直接调用 g4_assemble.audio_filter_chain——装配渲什么，这里就测什么。
    只混音频的输入序=口播 0、BGM 1（装配索引差一个视频输入前缀，函数参数化解决）。"""
    graph = asm.audio_filter_chain(0, 1, contract_variant, narration_pre)
    return graph + ";[aud]ebur128=peak=true[preout]"


def measure_combination(narration: Path, bgm: Path, contract_variant: dict, narration_pre: str | None,
                        timeline_ms: int, graph_file: Path) -> dict:
    """混音图经脚本文件参数交给 ffmpeg：参数全部以固定字面列表传递、shell=False 且不经过
    shell，命令行不携带任何由合同内容派生的字符串（安全扫描红线合规）；图本体留盘=
    每组合可审计（row.graphFile）。"""
    graph = build_precheck_graph(contract_variant, narration_pre)
    graph_file.parent.mkdir(parents=True, exist_ok=True)
    graph_file.write_text(graph + "\n", encoding="utf-8")
    offset_ms = int(contract_variant.get("trackOffsetMs") or 0)
    seek_args = ["-ss", str(round(offset_ms / 1000.0, 3))] if offset_ms else []
    duration_s = str(round(timeline_ms / 1000.0, 3))
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats",
         "-i", str(narration),
         "-stream_loop", "-1", *seek_args,
         "-i", str(bgm),
         "-filter_complex_script", str(graph_file),
         "-map", "[preout]",
         "-t", duration_s,
         "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600, shell=False)
    text = (result.stderr or "") + (result.stdout or "")
    reading = asm.parse_ebur128_summary(text)
    reading["lraLu"] = parse_lra(text)
    return reading


def judge_combination(reading: dict, profile: dict, tolerance_lu: float, strict: bool) -> dict:
    """主轨两闸（G5 同源口径）：真峰超上限+余量两档共同硬拦（限幅链路坏≠响度取舍）；
    综合响度超差按档分治——ready 罢工、blocked 如实披露。无读数=合同 §7 不出数。"""
    measured_i, measured_tp = reading.get("integratedLufs"), reading.get("truePeakDbtp")
    if measured_i is None or measured_tp is None:
        raise ValueError("混音预检测不出主轨读数（引擎异常或全静音源）——无实测不出数（合同 §7）")
    deviation = round(measured_i - float(profile["integratedLufs"]), 2)
    tp_over = round(measured_tp - float(profile["truePeakDbtp"]), 2)
    row = {"deviationLu": deviation, "truePeakOverDb": tp_over}
    if tp_over > asm.LOUDNESS_TP_SLACK_DB:
        row["verdict"] = "failed"
        row["failReason"] = ("true-peak", f"主轨真峰 {measured_tp:.1f} dBTP 超上限 {profile['truePeakDbtp']:.1f} "
                             f"加 {asm.LOUDNESS_TP_SLACK_DB} dB 余量——两档共同硬闸，限幅链路问题不是响度取舍")
    elif abs(deviation) <= tolerance_lu:
        row["verdict"] = "passed"
    elif strict:
        row["verdict"] = "failed"
        row["failReason"] = ("integrated", f"主轨实测 {measured_i:.1f} LUFS 偏离目标 {profile['integratedLufs']:.1f} "
                             f"达 {abs(deviation):.2f} LU，超容差 {tolerance_lu} LU——ready 档逐字应落点，超差即参数或链路问题")
    else:
        row["verdict"] = "disclosed-exceedance"
        row["reviewNote"] = (f"blocked 档让步幅度：主轨 {measured_i:.1f} LUFS 超容差 {abs(deviation):.2f} LU——"
                             "可进装配，但必须摊上 G4 回显卡向人确认，永不静默（与纯口播闸同纪律）。")
    return row


def parse_trial(spec: str) -> tuple[float, float]:
    try:
        bed_raw, duck_raw = spec.split(":", 1)
        bed, duck = float(bed_raw), float(duck_raw)
    except (ValueError, AttributeError):
        raise ValueError("候选组合入参需要 bedDb:duckReductionDb 形状（例如 -8:12），收到不合法的值")
    return bed, duck


def main() -> int:
    parser = argparse.ArgumentParser(description="G4 混音预检（台账⑦·甲案）：装配前只混音频实测主轨响度，同源链、绑定闸")
    parser.add_argument("--narration-audio", required=True, type=Path, help="将进入装配的放置轨（与装配口播输入同一文件）")
    parser.add_argument("--bgm-audio", required=True, type=Path, help="BGM 音频（与装配同文件）")
    parser.add_argument("--mix-contract", required=True, type=Path, help="music-expert《BGM-混音合同》（本组合的权威定义）")
    parser.add_argument("--loudness-plan", required=True, type=Path, help="loudness-expert《响度-归一化计划》——目标档与口播链的事实源")
    parser.add_argument("--output", required=True, type=Path, help="预检报告落盘路径（拒绝覆盖，重测请换版本名）")
    parser.add_argument("--trial", action="append", default=[],
                        help="附加候选组合，形状 bedDb:duckReductionDb，可重复；仅供编排调参搜索，装配闸只认合同组合行")
    parser.add_argument("--tolerance-lu", type=float, default=None,
                        help="覆盖综合响度容差（合同 §3 默认 ±1.0 LU），装配对账要求逐字一致")
    args = parser.parse_args()

    if args.output.exists():
        asm.fail("预检报告已存在——同版覆盖是禁令（台账⑥教训），重测请写新版本文件名")

    narration = asm.require_file(args.narration_audio, "narration audio")
    bgm = asm.require_file(args.bgm_audio, "BGM audio")
    contract = asm.load(asm.require_file(args.mix_contract, "BGM mix contract"))
    if contract.get("purpose") != "bgm_mix_contract" or contract.get("schemaVersion") != "0.1":
        asm.fail("混音合同入参不是 music-expert《BGM-混音合同》v0.1 产物——专员决策、节点执行，对账不许猜")
    if contract.get("bgmAudio", {}).get("sha256") != asm.sha256(bgm):
        asm.fail("BGM 文件哈希与混音合同不符——先用 music_mix_plan.py 重出合同再预检")
    timeline_ms = int(contract.get("timelineMs") or 0)
    if timeline_ms <= 0:
        asm.fail(f"混音合同 timelineMs 缺失或非法：{contract.get('timelineMs')!r}")
    narration_ms = asm.probe_duration_ms(narration)
    if narration_ms + 400 < timeline_ms:
        asm.fail(f"口播轨 {narration_ms}ms 短于时间线 {timeline_ms}ms——装配本来就会拒，先对齐再预检")

    plan = asm.load_loudness_plan(args.loudness_plan, narration, contract.get("projectId"))
    narration_pre, mode = asm.narration_chain_from_plan(plan)
    profile = plan["targetProfile"]
    strict = mode == "linear-verbatim"
    tolerance = args.tolerance_lu if args.tolerance_lu is not None else asm.LOUDNESS_TOLERANCE_LU
    tolerance_source = "CLI 显式覆盖" if args.tolerance_lu is not None else "合同 §3 默认"

    bed, duck = float(contract["bedGainDb"]), float(contract["duckReductionDb"])
    combos = [{"bedGainDb": bed, "duckReductionDb": duck, "isContractCombination": True}]
    for spec in args.trial:
        trial_bed, trial_duck = parse_trial(spec)
        if (trial_bed, trial_duck) == (bed, duck):
            continue
        combos.append({"bedGainDb": trial_bed, "duckReductionDb": trial_duck, "isContractCombination": False})

    graph_dir = args.output.parent / (args.output.stem + "-滤镜图")
    rows = []
    for index, combo in enumerate(combos, 1):
        variant = dict(contract)
        variant["bedGainDb"] = combo["bedGainDb"]
        variant["duckReductionDb"] = combo["duckReductionDb"]
        graph_path = graph_dir / f"combo-{index:02d}.filtergraph"
        reading = measure_combination(narration, bgm, variant, narration_pre, timeline_ms, graph_path)
        row = dict(combo)
        row["measuredMaster"] = {"integratedLufs": reading["integratedLufs"],
                                 "truePeakDbtp": reading["truePeakDbtp"],
                                 "lraLu": reading["lraLu"]}
        row.update(judge_combination(reading, profile, tolerance, strict))
        row["graphFile"] = str(graph_path)
        rows.append(row)

    contract_row = next(r for r in rows if r["isContractCombination"])
    status = contract_row["verdict"]
    if status == "passed":
        guidance = "主轨双闸通过——这份报告作为装配入参随 g4_assemble 进装配（报告入参见其帮助）。LRA 只记录不判，验收闸归 G5。"
    elif status == "disclosed-exceedance":
        guidance = "blocked 档让步幅度可进装配，但本合同组合行与 reviewNote 必须逐字摊上 G4 回显卡待确认，永不静默。"
    else:
        guidance = ("不要渲染。合法出路（§6-② 执行层授权范围内）：用 music_mix_plan.py 调整床深或 duck 参数"
                    "重出**新版本**合同（不覆盖旧合同），再以新合同重跑本预检；调参可用候选组合入参先做网格搜索"
                    "（本次实测每种组合几秒完成，比整轮 G4 返工便宜两个数量级）。改目标档本身属 G2 领地，不在本闸出路。")

    report = {
        "schemaVersion": "0.1",
        "node": "G4",
        "tool": "g4_mix_precheck",
        "generatedBy": str(Path(__file__).resolve()),
        "projectId": contract.get("projectId"),
        "status": status,
        "inputs": {
            "narrationAudio": {"path": str(narration), "sha256": asm.sha256(narration)},
            "bgmAudio": {"path": str(bgm), "sha256": asm.sha256(bgm)},
            "mixContract": {"path": str(args.mix_contract), "sha256": asm.sha256(args.mix_contract)},
            "loudnessPlan": {"path": str(args.loudness_plan), "sha256": asm.sha256(args.loudness_plan)},
        },
        "timelineMs": timeline_ms,
        "gateLines": {
            "targetProfile": profile,
            "toleranceLu": tolerance,
            "toleranceSource": tolerance_source,
            "tpSlackDb": asm.LOUDNESS_TP_SLACK_DB,
            "strictness": mode,
            "note": "综合响度+真峰双闸与 G5 loud_verify 同源口径；LRA 只记录不判。",
        },
        "combinations": rows,
        "guidance": guidance,
        "method": {
            "chainSource": "g4_assemble.audio_filter_chain + 响度计划分档链——与装配同一函数同一文件，非复刻平行链",
            "engine": "ffmpeg-ebur128",
            "audioOnly": True,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "report": str(args.output),
                      "contractCombination": {"bedGainDb": bed, "duckReductionDb": duck},
                      "measuredMaster": contract_row["measuredMaster"],
                      "deviationLu": contract_row["deviationLu"], "truePeakOverDb": contract_row["truePeakOverDb"],
                      "combinationsMeasured": len(rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=True))
        raise SystemExit(2)
