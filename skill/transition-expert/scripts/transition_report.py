#!/usr/bin/env python3
"""Audit the G4 assembly record against the approved transition directive.

执行==批准的唯一物证：装配记录里的 filterGraph 逐项对账指令 boundaries
（xfade 次数/transition/duration/offset）与 masterFades（fade in/out）；
指令为空则 filterGraph 里一个 xfade 都不许多出现。产物 transition-audit.json
带 skill/purpose/sha256 身份，供 G5 交付校验握手（照 subtitle-srt-check 模式）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

REPORT_NAME = "transition-audit.json"
XFADE = re.compile(r"xfade=transition=([a-z]+):duration=([\d.]+):offset=([\d.]+)")
FADE_IN = re.compile(r"fade=t=in:st=0(?::|\.)")
FADE_OUT = re.compile(r"fade=t=out:st=([\d.]+)")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def audit(manifest: dict, record: dict, directive: dict) -> dict:
    findings = []
    if directive.get("skill") != "transition-expert" or directive.get("purpose") != "transition_directive":
        return None, ["directive 不是 transition-expert 的 transition_directive 产物"]
    bound = manifest.get("transitionDirective") or {}
    if directive["boundaries"] or directive["masterFades"]["fadeInMs"] or directive["masterFades"]["fadeOutMs"]:
        if not bound:
            findings.append("manifest 未携带 transitionDirective（转场指令未经 prepare 透传）")
        elif bound.get("sha256") != sha256_of_directive(bound.get("path"), directive):
            findings.append("manifest 登记的指令哈希与传入指令文件不一致（stale，重跑 prepare）")
    graph = str(record.get("filterGraph") or "")
    actual = XFADE.findall(graph)
    expected = [("{0:.3f}".format(b["durationMs"] / 1000), "{0:.3f}".format(b["offsetMs"] / 1000)) for b in directive["boundaries"]]
    actual_pairs = [(d, o) for _, d, o in actual]
    if len(actual) != len(directive["boundaries"]):
        findings.append(f"filterGraph xfade 次数 {len(actual)} != 指令 boundaries {len(directive['boundaries'])}（多做的转场=未批准，缺做的=静默丢失）")
    else:
        for (transition, duration, offset), boundary, pair in zip(actual, directive["boundaries"], expected):
            if transition != boundary["transition"] or (duration, offset) != pair:
                findings.append(f"xfade 执行参数与指令不符：{transition} d={duration} o={offset}，指令 {boundary['transition']} d={pair[0]} o={pair[1]}")
    fades = directive["masterFades"]
    if fades.get("fadeInMs") and not FADE_IN.search(graph):
        findings.append("指令要求片头黑场入，filterGraph 无 fade=in")
    if fades.get("fadeOutMs"):
        match = FADE_OUT.search(graph)
        want = "{0:.3f}".format((record.get("timelineDurationMs", 0) - fades["fadeOutMs"]) / 1000)
        if not match:
            findings.append("指令要求片尾黑场出，filterGraph 无 fade=out")
        elif match.group(1) != want:
            findings.append(f"fade=out 起点 {match.group(1)} != 指令推导 {want}（网格平移！）")
    if not findings and not actual and not directive["boundaries"]:
        findings = []
    return findings, None


def sha256_of_directive(path, directive: dict) -> str:
    # manifest 记录的是文件哈希；这里只在文件可读时比对，否则返回哨兵让上层报 stale。
    try:
        return sha256(Path(path))
    except (OSError, TypeError):
        return "UNREADABLE"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--assembly-record", required=True, type=Path)
    parser.add_argument("--directive", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    manifest, record, directive = load(args.manifest), load(args.assembly_record), load(args.directive)
    findings, fatal = audit(manifest, record, directive)
    if fatal:
        print(json.dumps({"status": "invalid", "error": fatal[0]}, ensure_ascii=False))
        return 2
    report = {"status": "passed" if not findings else "failed",
              "skill": "transition-expert", "purpose": "transition_check",
              "generatedAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
              "checkedAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
              "transitions": [{"boundary": f"{b['fromSegmentId']}→{b['toSegmentId']}", "transition": b["transition"],
                               "durationMs": b["durationMs"], "offsetMs": b["offsetMs"]} for b in directive["boundaries"]],
              "masterFades": directive["masterFades"],
              "gridInvariant": bool(directive.get("gridInvariant")),
              "manifest": {"path": str(args.manifest), "sha256": sha256(args.manifest)},
              "assemblyRecord": {"path": str(args.assembly_record), "sha256": sha256(args.assembly_record)},
              "directive": {"path": str(args.directive), "sha256": sha256(args.directive)},
              "master": {"path": record.get("output"), "sha256": record.get("outputSha256")},
              "errors": findings}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = args.output_dir / REPORT_NAME
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(out), "transitions": len(report["transitions"]),
                      "errors": findings}, ensure_ascii=False))
    return 0 if not findings else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "invalid", "error": str(error)}, ensure_ascii=False))
        raise SystemExit(2)
