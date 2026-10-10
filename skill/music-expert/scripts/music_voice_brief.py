"""口播带起点清单的唯一机械推导入口（banshee-001 台账 14 小项1，甲案，2026-10-10 用户拍板）。

用法：music_voice_brief.py --plan <批准过的 G3 剪辑计划> --voice-manifest <G2 配音实测清单>
        --output-dir <目录>
产物：《配音清单-带起点-vN.json》——music_align.py --voice-brief 的直接输入。

铁口径（14 大轴口径的机器化）：每句 startMs 只准逐字取批准计划里的成片落位
（narrationStartMs/narrationEndMs，输出轴坐标），durationMs 只准逐字取 G2 实测清单
（合成后真实长度）；两轴绝不混算——声音轨累计当起点正是 14 大抓过的错轴
（banshee v0.1 桥件返工成因），本脚本从结构上不给它留通道。
句与段的缝合：计划允许句内切分（同一句跨连续多段，banshee seg-03a/03b 实例），
本脚本按输出轴顺序把连续片段拼接回整句、与实测清单文本逐字对合——段边界切开
句子、句子配不到片段、片段剩着没人认领，都罢工点名。
对账罢工面还有：计划非批准态、落位窗口与实测时长不等（塞不进或虚位）、
起点不严格递增、实测句 id 重复。产物带两输入 sha 绑定（R2 同型）、
版本自增永不覆盖（小项2 同规）。手工桥接文件（配音清单-派生-带起点 一类）自此退役。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from versioned_output import next_versioned  # noqa: E402


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def norm(text) -> str:
    return " ".join(str(text).split())


def fail_exit(errors) -> None:
    print(json.dumps({"status": "invalid", "errors": errors}, ensure_ascii=False, indent=2))
    sys.exit(2)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="由批准计划+实测清单机械推导带起点配音清单")
    parser.add_argument("--plan", required=True, type=Path, help="approved G3 剪辑计划 JSON（逐句 narration 落位=输出轴）")
    parser.add_argument("--voice-manifest", required=True, type=Path,
                        help="local_tts G2 配音实测清单（逐句 durationMs=合成真长）")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)

    for label, path in (("plan", args.plan), ("voice-manifest", args.voice_manifest)):
        if not path.is_file():
            fail_exit([{"field": label, "rule": "文件不存在", "detail": str(path)}])
    plan = json.loads(args.plan.read_text(encoding="utf-8-sig"))
    manifest = json.loads(args.voice_manifest.read_text(encoding="utf-8-sig"))

    if plan.get("status") != "approved_for_g4":
        fail_exit([{"field": "plan.status", "rule": "计划必须是 approved_for_g4（批准落位才可代入），当前="
                         + str(plan.get("status")), "detail": str(args.plan)}])
    sentences = manifest.get("sentences")
    if not isinstance(sentences, list) or not sentences:
        fail_exit([{"field": "voice-manifest.sentences", "rule": "非空句子数组 required", "detail": str(args.voice_manifest)}])

    errors = []
    frag_segments = []
    for seg in plan.get("segments") or []:
        text = seg.get("narrationText")
        start = seg.get("narrationStartMs")
        end = seg.get("narrationEndMs")
        if text is None and start is None and end is None:
            continue
        if not isinstance(text, str) or not text.strip() or not isinstance(start, int) or not isinstance(end, int):
            errors.append({"field": f"segments[{seg.get('segmentId')}]",
                           "rule": "带落位的段必须齐 narrationText/narrationStartMs/narrationEndMs(整数)",
                           "detail": str(seg.get("segmentId"))})
            continue
        frag_segments.append({"segmentId": str(seg.get("segmentId")), "text": norm(text),
                              "start": start, "end": end})
    if errors:
        fail_exit(errors)
    frag_segments.sort(key=lambda item: (item["start"], item["end"]))

    brief_sentences = []
    seen_ids = set()
    cursor = 0
    for item in sentences:
        sid = item.get("sentenceId")
        text = item.get("text")
        duration = item.get("durationMs")
        if not isinstance(sid, str) or not isinstance(text, str) or not isinstance(duration, int):
            errors.append({"field": "voice-manifest.sentences", "rule": "每句需 sentenceId/text/durationMs(整数)",
                           "detail": str(sid)})
            continue
        if sid in seen_ids:
            errors.append({"field": "sentenceId", "rule": f"实测清单句 id 重复：{sid}", "detail": norm(text)[:40]})
            continue
        seen_ids.add(sid)
        target = norm(text)
        parts = []
        start = None
        end = None
        matched = False
        while cursor + len(parts) < len(frag_segments):
            frag = frag_segments[cursor + len(parts)]
            parts.append(frag["text"])
            if start is None:
                start = frag["start"]
            end = frag["end"]
            joined = " ".join(parts)
            if joined == target:
                cursor += len(parts)
                matched = True
                break
            if target.startswith(joined + " ") or target == joined:
                continue
            errors.append({"field": "sentenceStitch", "rule":
                           f"句 {sid} 与计划片段缝合失败：拼接得到「{joined[:60]}…」与整句不逐字相等——"
                           "段边界切开句子/文本漂移都属账面失真，改稿回 G2、改落位回 G3，本工具不调和",
                           "detail": target[:60]})
            cursor += len(parts)
            matched = False
            break
        if not matched:
            if not errors or errors[-1].get("field") != "sentenceStitch":
                errors.append({"field": "sentenceStitch", "rule":
                               f"句 {sid} 在批准计划剩余片段里找不到落位（改稿未回炉计划？）",
                               "detail": target[:60]})
            continue
        if end - start != duration:
            errors.append({"field": "narrationWindow", "rule":
                           f"落位窗口 {end - start}ms 与实测时长 {duration}ms 不等——"
                           "塞不进（窗口短）或虚位（窗口长）都禁止；改落位=回 G3 重批，改稿=重合成",
                           "detail": f"{sid} startMs={start}"})
            continue
        brief_sentences.append({"sentenceId": sid, "text": target, "startMs": start, "durationMs": duration})

    leftover = [frag["segmentId"] for frag in frag_segments[cursor:] if frag["text"]]
    if leftover:
        errors.append({"field": "sentenceStitch", "rule":
                       "计划里这些带落位片段没有被任何实测句认领（两账对不平：删句未回炉/加句未重排）",
                       "detail": ", ".join(leftover)})
    if errors:
        fail_exit(errors)

    starts = [item["startMs"] for item in brief_sentences]
    starts_sorted = sorted(starts)
    if starts != starts_sorted or any(b <= a for a, b in zip(starts, starts[1:])):
        fail_exit([{"field": "startMs", "rule": "落位起点必须按稿序严格递增（输出轴不允许并列/倒退）", "detail": str(starts)}])
    brief_sentences_sorted = sorted(brief_sentences, key=lambda item: item["startMs"])

    out_path, version = next_versioned(args.output_dir, "配音清单-带起点", ".json")
    brief = {
        "schemaVersion": "0.1",
        "node": "G3",
        "purpose": "bgm_voice_brief",
        "artifactVersion": version,
        "derivedFrom": {
            "plan": str(args.plan), "planSha256": sha256_file(args.plan),
            "voiceManifest": str(args.voice_manifest), "voiceManifestSha256": sha256_file(args.voice_manifest),
        },
        "axisNote": "startMs=成片输出轴落位（逐字取自批准计划 narrationStartMs，句内切分片段按序缝合回整句）；durationMs=合成实测（逐字取自配音清单）。14 大轴口径的机械执行，声音轨累计在本通道无处出现。",
        "voice": manifest.get("voice"),
        "voiceTier": manifest.get("voiceTier"),
        "timelineDurationMs": int(plan.get("timelineDurationMs") or 0),
        "measuredTotalDurationMs": sum(item["durationMs"] for item in brief_sentences_sorted),
        "sentences": brief_sentences_sorted,
    }
    out_path.write_text(json.dumps(brief, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "brief": str(out_path), "sentences": len(brief_sentences_sorted),
                      "artifactVersion": version}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
