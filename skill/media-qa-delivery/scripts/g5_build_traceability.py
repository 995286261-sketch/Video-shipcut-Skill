#!/usr/bin/env python3
"""G5 时间码溯源清单唯一生成入口（banshee-001 台账⑪，用户 2026-10-10 拍板甲案）。

病根：source-timecode-list.json 是交付包必检件，但流水线从无机械生成入口，
全靠编排手写。banshee 首轮手写即走样（章节键写成 clip、顶层 segments 缺失），
又因当时 G5 停在响度闸、检查本件的 validator 从未跑到，错形状在包里潜伏一整轮。
同族病先例＝zaku-003 ⑭"质检报告无生成器"（v1.12.0 已修成 --report-out 唯一正道）。

本工具行为（机器只投影，不发明）：
- 段区间逐字取自已批准 G3 计划（segmentId、assetId、源起终=计划 startMs/endMs、
  输出网格 outputStartMs/outputEndMs）；计划未批准状态=罢工。
- 资产路径与 sha256 从 G0 素材包登记反查（material-pack.json sourceAssets）；
  assetId 不在册=罢工点名（登记件之外结构上进不来，v1.19.0 ⑫ 同型纪律）。
- 版本同证：装配记录的 projectId 与 timelineDurationMs 必须逐字等于计划，
  装配段 ID 集合必须等于计划段 ID 集合——装配与计划不同版=过期罢工。
- 章节窗口是编排的编辑决定，经 chapter-windows 输入文件承载（每章 chapterId、
  outputStartMs、outputEndMs，可选 output 文件名，缺省 clips/章ID.mp4）；
  成员段=输出区间完整落入窗口的段，机械判定，无人工填表。
  窗口必须自 0 到 timelineDurationMs 连续铺满；3–5 章（交付校验器硬约束前置到此）。
- 拒绝覆盖既有文件（删旧重跑，⑭/㉘ 同源纪律）；产物带 generatedBy 出处行与
  三件输入的 path+sha256 绑定（R2 同型：来源漂移=清单过期）。

用法（参数形态以 --help 为准）：python3 g5_build_traceability.py 加
plan、assembly-record、material-pack、chapters、output 五个路径参数。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def fail(errors: list[str]) -> None:
    print(json.dumps({"status": "blocked", "errors": errors}, ensure_ascii=False))
    sys.exit(2)


def load_json(path: Path, label: str) -> dict:
    if not path.is_file():
        fail([f"{label} 不存在：{path}"])
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        fail([f"{label} 不是合法 JSON：{error}"])
    return {}


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="机械投影生成 source-timecode-list.json（台账⑪甲案：机器生成=唯一正道）")
    parser.add_argument("--plan", required=True, help="已批准 G3 计划 JSON")
    parser.add_argument("--assembly-record", required=True, dest="assembly", help="G4 装配记录 JSON（版本同证）")
    parser.add_argument("--material-pack", required=True, dest="pack", help="G0 素材包 material-pack.json（资产身份唯一来源）")
    parser.add_argument("--chapters", required=True, help="章节窗口 JSON（编排编辑决定：3–5 章连续铺满成片）")
    parser.add_argument("--output", required=True, help="包内落盘路径（拒绝覆盖）")
    args = parser.parse_args(argv)

    plan_path = Path(args.plan).resolve()
    assembly_path = Path(args.assembly).resolve()
    pack_path = Path(args.pack).resolve()
    chapters_path = Path(args.chapters).resolve()
    output_path = Path(args.output).resolve()
    if output_path.exists():
        fail([f"拒绝覆盖既有清单（⑭/㉘ 纪律：删旧重跑）：{output_path}"])

    plan = load_json(plan_path, "批准计划")
    assembly = load_json(assembly_path, "装配记录")
    pack = load_json(pack_path, "素材包登记")
    chapters_doc = load_json(chapters_path, "章节窗口")

    errors: list[str] = []
    project_id = plan.get("projectId")
    if not project_id:
        errors.append("计划缺 projectId")
    if "approved" not in str(plan.get("status") or ""):
        errors.append("计划状态未批准——溯源清单只许从已批准计划投影")
    timeline_ms = plan.get("timelineDurationMs")
    if not isinstance(timeline_ms, int) or timeline_ms <= 0:
        errors.append("计划缺合法 timelineDurationMs")
    plan_segments = plan.get("segments") or []
    if not plan_segments:
        errors.append("计划无 segments")
    if assembly.get("projectId") != project_id:
        errors.append("装配记录 projectId 与计划不一致（版本同证失败）")
    if assembly.get("timelineDurationMs") != timeline_ms:
        errors.append("装配记录 timelineDurationMs 与计划不一致——装配与计划不同版，清单过期")
    assembled_ids = {item.get("segmentId") for item in assembly.get("segments") or []}
    plan_ids = {item.get("segmentId") for item in plan_segments}
    if assembled_ids and assembled_ids != plan_ids:
        errors.append("装配段 ID 集合与计划段 ID 集合不一致——装配与计划不同版")

    assets: dict[str, dict] = {}
    for asset in pack.get("sourceAssets") or []:
        if asset.get("assetId"):
            assets[str(asset["assetId"])] = asset

    segments: list[dict] = []
    for seg in plan_segments:
        segment_id = seg.get("segmentId")
        asset_id = seg.get("assetId")
        start, end = seg.get("startMs"), seg.get("endMs")
        out_start, out_end = seg.get("outputStartMs"), seg.get("outputEndMs")
        if not segment_id or not asset_id:
            errors.append(f"计划段缺 segmentId/assetId：{segment_id}")
            continue
        if not isinstance(start, int) or not isinstance(end, int) or end <= start:
            errors.append(f"段 {segment_id} 源区间非法（起终必须是计划内整数毫秒且终>起）")
            continue
        asset = assets.get(str(asset_id))
        if not asset or not asset.get("sha256") or not asset.get("relativePath"):
            errors.append(f"段 {segment_id} 的 assetId 不在素材包登记（{asset_id}）——登记件之外结构上进不来")
            continue
        segments.append({
            "segmentId": segment_id,
            "assetId": asset_id,
            "sourceAssetPath": asset["relativePath"],
            "sourceSha256": str(asset["sha256"]).upper(),
            "sourceStartMs": start,
            "sourceEndMs": end,
            "outputStartMs": out_start,
            "outputEndMs": out_end,
        })

    raw_chapters = chapters_doc.get("chapters") if isinstance(chapters_doc, dict) else chapters_doc
    if not isinstance(raw_chapters, list) or not raw_chapters:
        errors.append("章节窗口为空——须为 3–5 章的连续铺满列表")
        fail(errors)
    if not 3 <= len(raw_chapters) <= 5:
        errors.append(f"章节数 {len(raw_chapters)} 不合合同（交付校验器硬约束 3–5 章）")
    chapters: list[dict] = []
    cursor = 0
    for chapter in raw_chapters:
        chapter_id = chapter.get("chapterId")
        win_start, win_end = chapter.get("outputStartMs"), chapter.get("outputEndMs")
        if not chapter_id or not isinstance(win_start, int) or not isinstance(win_end, int) or win_end <= win_start:
            errors.append(f"章节窗口非法：{chapter_id}")
            continue
        if "/" in str(chapter_id):
            errors.append(f"章节 ID 不得含路径分隔：{chapter_id}")
            continue
        if win_start != cursor:
            errors.append(f"章节 {chapter_id} 起点 {win_start} 不等于上一窗终点 {cursor}——窗口必须连续铺满")
        output_rel = chapter.get("output") or f"clips/{chapter_id}.mp4"
        members = [item["segmentId"] for item in segments
                   if win_start <= item.get("outputStartMs", -1) and item.get("outputEndMs", 0) <= win_end]
        if not members:
            errors.append(f"章节 {chapter_id} 内没有任何计划段落入（窗口与段网格脱节）")
        cursor = win_end
        chapters.append({"chapterId": chapter_id, "output": output_rel,
                         "outputStartMs": win_start, "outputEndMs": win_end, "segments": members})
    if isinstance(timeline_ms, int) and cursor != timeline_ms:
        errors.append(f"章节窗口止于 {cursor}ms 而成片长 {timeline_ms}ms——必须铺满全片")
    covered = {item for chapter in chapters for item in chapter["segments"]}
    orphan = sorted(set(s["segmentId"] for s in segments) - covered)
    if orphan:
        errors.append(f"这些段不属于任何章节窗口：{', '.join(orphan)}——窗口与段网格脱节")
    if errors:
        fail(errors)

    trace = {
        "schemaVersion": "0.1",
        "node": "G5",
        "projectId": project_id,
        "generatedBy": "g5_build_traceability.py 机械投影自批准计划+装配记录+素材包登记（台账⑪甲案：手写通道退役，本文件唯一生成入口）",
        "bindings": {
            "plan": {"path": str(plan_path), "sha256": sha256_of(plan_path)},
            "assemblyRecord": {"path": str(assembly_path), "sha256": sha256_of(assembly_path)},
            "materialPack": {"path": str(pack_path), "sha256": sha256_of(pack_path)},
            "chapterWindows": {"path": str(chapters_path), "sha256": sha256_of(chapters_path)},
        },
        "segments": segments,
        "chapters": chapters,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "written", "output": str(output_path), "projectId": project_id,
                      "segments": len(segments), "chapters": len(chapters)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
