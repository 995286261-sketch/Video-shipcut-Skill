#!/usr/bin/env python3
"""Build the machine mix contract G4 must execute for a BGM bed (N6).

Architecture (user 2026-09-10): domain capability lives in specialists, node
skills only sequence nodes. G4's assemble script therefore no longer decides
"gain −18dB + boolean sidechain" on its own; it consumes *this* contract.
The contract is derived exclusively from artifacts that already passed their
own gates — the approved G3 plan (bgmPlan), the music_align alignment artifact,
and the physical BGM file on disk — and it re-verifies the whole hash chain
(plan.alignmentSha256 == alignment file, plan.audioSha256 == alignment report
cache key == sha256 of the file being mixed). Any mismatch is a hard block:
G4 can only render what G3 approved, and the ducking depth that §6-② deferred
to pre-G4 decision becomes an explicit, echoed parameter here.

Outputs `BGM-混音合同-v0.1.json` (machine, consumed by g4_assemble.py
--bgm-mix-contract) and `BGM-混音合同回显-v0.1.md` (human echo card).
Deterministic, pure-stdlib.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

SCHEMA_VERSION = "0.1"
PURPOSE = "bgm_mix_contract"


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True))


def fail_exit(errors: list[dict], code: int = 2) -> None:
    emit({"status": "invalid", "errors": errors})
    raise SystemExit(code)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def normalized_ref(value: str) -> str:
    return value.replace("\\", "/").lstrip("./")


def fmt_tc(ms: int) -> str:
    minutes, remainder = divmod(ms, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{minutes:02}:{seconds:02}.{millis:03}"


def load_json(path: Path, label: str, errors: list[dict]) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        errors.append({"field": label, "error": f"cannot read {path.name}: {error}"})
        return None
    if not isinstance(value, dict):
        errors.append({"field": label, "error": f"{path.name} must contain a JSON object"})
        return None
    return value


def merge_duck_segments(ducking: list[dict], timeline_ms: int, errors: list[dict]) -> list[dict]:
    """Validate per-sentence ducking windows, then merge contiguous ones: ducking
    that spans the whole narration is one automation region, not fifteen."""
    segments: list[dict] = []
    for entry in ducking:
        if not isinstance(entry, dict):
            errors.append({"field": "ducking", "error": "entry must be an object"})
            continue
        start, end = entry.get("fromMs"), entry.get("toMs")
        if not isinstance(start, int) or not isinstance(end, int) or end <= start:
            errors.append({"field": "ducking", "error": f"invalid window for {entry.get('sentenceId')}"})
            continue
        if start < 0 or end > timeline_ms:
            errors.append({"field": "ducking", "error": f"window {start}–{end}ms outside timeline 0–{timeline_ms}ms"})
            continue
        segments.append({"fromMs": start, "toMs": end, "sentenceId": entry.get("sentenceId")})
    segments.sort(key=lambda item: (item["fromMs"], item["toMs"]))
    merged: list[dict] = []
    for segment in segments:
        if merged and segment["fromMs"] <= merged[-1]["toMs"]:
            merged[-1]["toMs"] = max(merged[-1]["toMs"], segment["toMs"])
            merged[-1]["sentenceIds"].append(segment["sentenceId"])
        else:
            merged.append({"fromMs": segment["fromMs"], "toMs": segment["toMs"], "sentenceIds": [segment["sentenceId"]]})
    return merged


def build_card(contract: dict, source: dict) -> str:
    lines = [
        f"# BGM 混音合同 v{SCHEMA_VERSION} — {contract['projectId']}",
        "",
        f"- BGM 文件：`{contract['bgmAudio']['path']}`（SHA-256 `{contract['bgmAudio']['sha256'][:16]}…`，与 G3 计划 bgmPlan.audioSha256 对账一致）",
        f"- 依据链：计划 `{Path(contract['evidence']['planRef']).name}` × 对齐产物 `{Path(contract['evidence']['alignmentRef']).name}`（哈希见合同 evidence）",
        "",
        "## 混音参数（G4 必须逐字执行，改数=重跑本脚本）",
        "",
        f"- 轨偏移：{contract['trackOffsetMs']}ms（{fmt_tc(contract['trackOffsetMs'])} 起读轨）",
        f"- 垫底音量：{contract['bedGainDb']:g} dB｜口播段 ducking 追加压低 {contract['duckReductionDb']:g} dB（§6-② 拍板参数）",
        *( [f"- 可听性守卫：轨原响 {contract['predictedLufs']['trackIntegratedLufs']} LUFS → 口播段在位预估 **{contract['predictedLufs']['bedDuckedLufs']} LUFS**（人声目标 {contract['predictedLufs']['narrationTargetLufs']:g}，允许窗 {contract['predictedLufs']['windowLufs'][0]}~{contract['predictedLufs']['windowLufs'][1]} LUFS；出窗本合同拒绝生成）"] if contract.get("predictedLufs") else [] ),
        f"- 淡入 {contract['fades']['fadeInMs']}ms｜淡出起 {fmt_tc(contract['fades']['fadeOutStartMs'])} 长 {contract['fades']['fadeOutMs']}ms",
        f"- ducking 区间：{len(contract['ducking'])} 句 → 合并后 {len(contract['duckSegments'])} 段自动化",
        "",
        "| 段 | from | to | 覆盖句 |",
        "|---|---|---|---|",
    ]
    for index, segment in enumerate(contract["duckSegments"], 1):
        lines.append(f"| {index} | {fmt_tc(segment['fromMs'])} | {fmt_tc(segment['toMs'])} | {'、'.join(str(s) for s in segment['sentenceIds'])} |")
    lines += [
        "",
        "## 纪律",
        "",
        "- 本合同是 G3 批准内容的机器翻译：偏移/淡入淡出/ducking 窗口全部取自对齐产物并与计划哈希对账，任何不一致即 blocked，禁止手改合同绕过；",
        "- G4 只执行不决策：想改音量/深度/淡变，重跑本脚本换参数并留变更记录；",
        f"- 参数：bedGainDb={contract['bedGainDb']:g}, duckReductionDb={contract['duckReductionDb']:g}（来源：本次调用参数，默认 -12 / 6；可听窗守卫出窗即拒）",
        "",
        "## 产物",
        "",
        f"- 机器合同：`{source['contractPath']}`",
        f"- 本卡：`{source['cardPath']}`",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path, help="approved G3 剪辑计划 JSON (bgmPlan consumer)")
    parser.add_argument("--alignment", required=True, type=Path, help="music-expert BGM-对齐建议-v0.2.json")
    parser.add_argument("--bgm-audio", required=True, type=Path, help="physical BGM file to be mixed")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--bed-gain-db", type=float, default=-12.0, help="steady BGM bed gain (default -12; zaku lesson: -18+12 stacked to inaudibility)")
    parser.add_argument("--duck-reduction-db", type=float, default=6.0, help="extra dB reduction applied to the bed while a sentence is speaking (§6-② decision, default 6)")
    parser.add_argument("--narration-target-lufs", type=float, default=-14.0, help="voice loudness target used by the audibility guard (default -14)")
    args = parser.parse_args()

    errors: list[dict] = []
    if not -40.0 <= args.bed_gain_db <= -3.0:
        errors.append({"field": "bedGainDb", "error": "must sit between -40 and -3 dB"})
    if not 0.0 < args.duck_reduction_db <= 24.0:
        errors.append({"field": "duckReductionDb", "error": "must sit between 0 (exclusive) and 24 dB"})
    plan = load_json(args.plan, "plan", errors)
    alignment = load_json(args.alignment, "alignment", errors)
    if errors:
        fail_exit(errors)
    try:
        bgm_sha = sha256(args.bgm_audio)
    except OSError as error:
        fail_exit([{"field": "bgmAudio", "error": f"cannot read BGM file: {error}"}])

    # --- hash-chain reconciliation against the approved plan ---------------
    if plan.get("node") != "G3" or plan.get("status") != "approved_for_g4":
        errors.append({"field": "plan", "error": "plan must be an approved (approved_for_g4) G3 plan"})
    bgm_plan = plan.get("bgmPlan")
    if not isinstance(bgm_plan, dict):
        errors.append({"field": "plan.bgmPlan", "error": "plan carries no bgmPlan — nothing to mix"})
    if alignment.get("purpose") != "bgm_alignment":
        errors.append({"field": "alignment", "error": "not a music_align alignment artifact"})
    if errors:
        fail_exit(errors)

    alignment_sha = sha256(args.alignment)
    if alignment_sha != bgm_plan.get("alignmentSha256"):
        errors.append({"field": "alignmentSha256", "error": "alignment artifact does not match the plan's bgmPlan hash chain — rerun music_align, never hand-edit"})
    if normalized_ref(str(bgm_plan.get("alignmentRef", ""))) != normalized_ref(str(args.alignment)):
        errors.append({"field": "alignmentRef", "error": "the alignment file passed is not the one the plan references"})
    if bgm_plan.get("audioSha256") != bgm_sha:
        errors.append({"field": "audioSha256", "error": "BGM file does not match the plan's bgmPlan.audioSha256 — wrong take or tampered asset"})
    cache_key = alignment.get("inputs", {}).get("reportCacheKey", {})
    if cache_key.get("sha256") != bgm_sha:
        errors.append({"field": "reportCacheKey", "error": "BGM file does not match the hash the analysis report was built from"})

    inner = alignment.get("alignment", {})
    timeline_ms = plan.get("timelineDurationMs")
    if inner.get("timelineMs") != timeline_ms:
        errors.append({"field": "timelineMs", "error": f"alignment timeline {inner.get('timelineMs')} != plan {timeline_ms}"})
    if bgm_plan.get("trackOffsetMs") != inner.get("offsetMs"):
        errors.append({"field": "trackOffsetMs", "error": "plan trackOffsetMs disagrees with the alignment artifact"})
    fades = bgm_plan.get("fades")
    if fades != alignment.get("fades"):
        errors.append({"field": "fades", "error": "plan fades disagree with the alignment artifact"})
    if not isinstance(fades, dict) or not all(isinstance(fades.get(k), int) for k in ("fadeInMs", "fadeOutStartMs", "fadeOutMs")):
        errors.append({"field": "fades", "error": "fades must carry integer fadeInMs/fadeOutStartMs/fadeOutMs"})
    else:
        if fades["fadeOutStartMs"] + fades["fadeOutMs"] > timeline_ms:
            errors.append({"field": "fades", "error": f"fade-out [{fades['fadeOutStartMs']},{fades['fadeOutStartMs'] + fades['fadeOutMs']})ms exceeds timeline {timeline_ms}ms"})
    ducking = alignment.get("ducking")
    if not isinstance(ducking, list):
        errors.append({"field": "ducking", "error": "alignment artifact carries no ducking list"})
        ducking = []
    merged = merge_duck_segments(ducking, timeline_ms or 0, errors) if not errors else []

    # --- audibility guard (zaku lesson, 2026-09-10) --------------------------
    # A bed that is technically "in the mix" but 25 LU under the voice is the
    # same failure as no BGM at all — and no human has to catch it by ear:
    # the analysis report already measured the track loudness, so the predicted
    # in-place level is arithmetic. Outside the audible-under-voice window the
    # contract refuses to exist; fix the parameters, not the listener.
    predicted = None
    report_path = alignment.get("inputs", {}).get("report")
    report = load_json(Path(report_path), "report", []) if report_path else None
    track_lufs = (report or {}).get("loudness", {}).get("integratedLufs")
    if not isinstance(track_lufs, (int, float)):
        errors.append({"field": "mixAudibility", "error": "cannot audit the mix: the analysis report referenced by the alignment artifact carries no measured loudness.integratedLufs"})
    else:
        bed_full = track_lufs + args.bed_gain_db
        bed_ducked = bed_full - args.duck_reduction_db
        low = args.narration_target_lufs - 18.0
        high = args.narration_target_lufs - 6.0
        if not low <= bed_ducked <= high:
            errors.append({"field": "mixAudibility", "error": f"predicted in-place BGM during narration is {bed_ducked:.1f} LUFS vs voice target {args.narration_target_lufs:g} LUFS — outside the audible window [{low:.1f}, {high:.1f}] LUFS (BGM would be inaudible or drowning the voice). Adjust --bed-gain-db/--duck-reduction-db."})
        predicted = {"trackIntegratedLufs": track_lufs, "bedFullLufs": round(bed_full, 1), "bedDuckedLufs": round(bed_ducked, 1),
                     "narrationTargetLufs": args.narration_target_lufs, "windowLufs": [round(low, 1), round(high, 1)]}
    if errors:
        fail_exit(errors)

    contract = {
        "schemaVersion": SCHEMA_VERSION,
        "skill": "music-expert",
        "purpose": PURPOSE,
        "projectId": plan.get("projectId"),
        "bgmAudio": {"path": str(args.bgm_audio), "sha256": bgm_sha},
        "evidence": {
            "planRef": str(args.plan), "planSha256": sha256(args.plan),
            "alignmentRef": str(args.alignment), "alignmentSha256": alignment_sha,
        },
        "timelineMs": timeline_ms,
        "trackOffsetMs": inner.get("offsetMs"),
        "bedGainDb": args.bed_gain_db,
        "duckReductionDb": args.duck_reduction_db,
        "fades": fades,
        "ducking": ducking,
        "duckSegments": merged,
        "mixMode": "duck-table",
        "predictedLufs": predicted,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    contract_path = args.output_dir / "BGM-混音合同-v0.1.json"
    card_path = args.output_dir / "BGM-混音合同回显-v0.1.md"
    contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    card_path.write_text(build_card(contract, {"contractPath": str(contract_path), "cardPath": str(card_path)}), encoding="utf-8")
    emit({"status": "completed", "contract": str(contract_path), "card": str(card_path),
          "trackOffsetMs": contract["trackOffsetMs"], "bedGainDb": contract["bedGainDb"],
          "duckReductionDb": contract["duckReductionDb"], "duckSegments": len(merged)})
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        emit({"status": "invalid", "errors": [{"field": "runtime", "error": str(error)}]})
        raise SystemExit(2)
