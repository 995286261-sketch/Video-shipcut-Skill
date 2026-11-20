#!/usr/bin/env python3
"""Mechanically derive the G4 source-caption masking contract from the approved
plan + the G3 visual observation ledger (mickey-001 ㉙: 遮罩带位置必须来自逐帧观察
的 captionZones，手写转写通道退役——合同唯一生成入口=本脚本，对账不过当场罢工)。"""
import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

COLOR_RE = re.compile(r"^[A-Za-z0-9@._%\-]+$")


def fail(messages):
    if isinstance(messages, str):
        messages = [messages]
    raise ValueError("\n".join(messages))


def load(path, label):
    if not path.is_file():
        fail(f"{label} 不存在：{path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def ledger_records(ledger):
    records = ledger.get("records") if isinstance(ledger, dict) else ledger
    if not isinstance(records, list):
        fail("账本没有 records 列表")
    return [r for r in records
            if isinstance(r, dict) and r.get("analysisStatus") == "completed"
            and r.get("analysisStatus") != "superseded" and "supersededBy" not in r]


def window_records(records, segment):
    start, end = int(segment["startMs"]), int(segment["endMs"])
    return [r for r in records
            if r.get("sourceAssetId") == segment.get("assetId")
            and isinstance(r.get("sourceMs"), int) and start <= r["sourceMs"] <= end]


def build_mask(segment, records, canvas_height, margin_pct, color, errors):
    segment_id = segment["segmentId"]
    hits = [r for r in window_records(records, segment)
            if "burned_subtitle" in (r.get("riskFlags") or [])]
    if not hits:
        errors.append(
            f"段 {segment_id} 声明 mode=mask，但源窗口 [{segment['startMs']},{segment['endMs']}]ms "
            "内没有任何带 burned_subtitle 的 active 观察记录——遮罩无证据=采样缺口或无据遮罩，"
            "先按合同补测该窗口（不许默认带内存在）")
        return None
    zones = []
    for record in hits:
        caption_zones = record.get("captionZones")
        if not isinstance(caption_zones, list) or not caption_zones:
            errors.append(
                f"观察记录 {record.get('recordId')}（{segment_id} 窗口）有 burned_subtitle 却缺 "
                "captionZones——位置必须实测记录，不许默认「在带内」（㉙ 病根本体）")
            return None
        zones.extend(z for z in caption_zones if isinstance(z, dict) and z.get("yPctRange"))
    if not zones:
        errors.append(f"段 {segment_id} 的 burned_subtitle 观察均无有效 yPctRange，无法出带")
        return None
    top_pct = min(float(z["yPctRange"][0]) for z in zones) - margin_pct
    top_pct = max(0.0, min(99.0, top_pct))
    observed = [tuple(z["yPctRange"]) for z in zones]
    if any(top_pct > low for low, _ in observed):
        errors.append(f"段 {segment_id} 内部矛盾：带顶 {top_pct:.1f}% 高于观测下沿 {observed}")
        return None
    y0 = round(canvas_height * top_pct / 100.0)
    return {
        "maskId": f"m-{segment_id}",
        "segmentId": segment_id,
        "outputFromMs": int(segment["outputStartMs"]),
        "outputToMs": int(segment["outputEndMs"]),
        "bandYpx": [y0, canvas_height],
        "color": color,
        "basis": (f"机械派生自观察记录 {', '.join(str(r.get('recordId')) for r in hits)} 的 "
                  f"captionZones 观测带并集 {observed}，margin {margin_pct}pct 得带顶 {top_pct:.1f}%；"
                  f"y1=画布底缘如实反映 drawbox 画到底语义（㉚）"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path, help="已批准 G3 剪辑计划 JSON")
    parser.add_argument("--ledger", required=True, type=Path, help="G3 视觉观察账本 JSON")
    parser.add_argument("--width", required=True, type=int)
    parser.add_argument("--height", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--margin-pct", type=float, default=2.0,
                        help="带顶在观测最低下沿之上的余量百分点（默认 2）")
    parser.add_argument("--color", default="black@0.85")
    args = parser.parse_args()
    if args.output.exists():
        fail(f"拒绝覆盖既有合同：{args.output}（版本自增不覆盖，删旧重跑须显式先删）")
    if not 0 <= args.margin_pct < 50:
        fail("margin-pct 须在 [0,50)")
    if not COLOR_RE.match(args.color):
        fail(f"color 含滤镜串危险字符：{args.color!r}")
    plan = load(args.plan, "G3 计划")
    if "approved" not in str(plan.get("status") or ""):
        fail("计划状态未批准——遮罩合同只许从已批准计划投影")
    ledger = load(args.ledger, "观察账本")
    records = ledger_records(ledger)
    errors, masks = [], []
    for segment in plan.get("segments", []):
        treatment = segment.get("sourceCaptionTreatment") or {}
        mode = treatment.get("mode")
        if mode == "mask":
            mask = build_mask(segment, records, args.height, args.margin_pct, args.color, errors)
            if mask:
                masks.append(mask)
        elif mode in (None, "none"):
            contradicted = [r.get("recordId") for r in window_records(records, segment)
                            if "burned_subtitle" in (r.get("riskFlags") or [])]
            if contradicted:
                errors.append(
                    f"段 {segment.get('segmentId')} mode=none 却存在窗口内烧字观察 "
                    f"{contradicted}——批准表与账本矛盾，回 G3 改判重批，本工具不调和")
    if errors:
        fail(errors)
    seen = {m["maskId"] for m in masks}
    if len(seen) != len(masks):
        fail("maskId 重复（段 ID 冲突）")
    contract = {
        "schemaVersion": "0.1",
        "node": "G4",
        "projectId": plan.get("projectId"),
        "canvas": {"width": args.width, "height": args.height},
        "masks": masks,
        "generatedBy": ("g4_build_mask_contract.py 机械派生自批准计划 sourceCaptionTreatment + "
                        "观察账本 captionZones（㉙：手写转写通道退役，本文件唯一生成入口）"),
        "derivedFrom": {
            "plan": str(args.plan), "planSha256": sha256_file(args.plan),
            "ledger": str(args.ledger), "ledgerSha256": sha256_file(args.ledger),
            "marginPct": args.margin_pct,
        },
        "generatedAt": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "written", "output": str(args.output), "masks": len(masks),
                      "bands": {m["segmentId"]: m["bandYpx"] for m in masks}}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "invalid", "error": str(error)}, ensure_ascii=True))
        raise SystemExit(2)
