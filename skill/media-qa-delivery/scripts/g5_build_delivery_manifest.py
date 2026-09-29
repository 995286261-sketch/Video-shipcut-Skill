#!/usr/bin/env python3
"""Build the single machine-readable G5 delivery manifest from bundle records."""
import argparse
import hashlib
import json
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def artifact(path: Path) -> dict:
    return {"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest().upper()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path,
                        help="Approved G2 evidence manifest containing sourceEvidence[].")
    parser.add_argument("--output", type=Path, help="Defaults to <bundle>/delivery-manifest.json")
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    trace = load(bundle / "source-timecode-list.json")
    plan = load(bundle / "edit-plan.json")
    # ⑭ 新序列=组件→manifest（pending）→--report-out 机器质检报告→人审→封版：
    # 报告与决策文件此刻合法缺席，缺席时 status 落 pending_human_review、
    # finishedAt 依 002-⑬ 裁决允许暂缺；两者在场则照常抬值（旧序列零影响）。
    qa_path = bundle / "metadata-validation-report.json"
    review_path = bundle / "human-review-decision.json"
    qa = load(qa_path) if qa_path.is_file() else {}
    review = load(review_path) if review_path.is_file() else {}
    export = load(bundle / "export-config.json")
    evidence = load(args.evidence)
    probes = [
        {"assetId": item["assetId"], "sha256": item["sha256"], "sourceProbe": item["sourceProbe"]}
        for item in evidence.get("sourceEvidence", [])
        if item.get("assetId") and item.get("sha256") and item.get("sourceProbe")
    ]
    if not probes:
        raise ValueError("evidence must contain sourceEvidence with sourceProbe")
    timeline = bundle / "edit-timeline.md"
    if not timeline.is_file():
        raise ValueError("delivery bundle requires edit-timeline.md")
    warnings = list(plan.get("warnings", []))
    for item in review.get("acceptedWarnings", []):
        warning = "accepted_warning:" + json.dumps(item, ensure_ascii=True, sort_keys=True)
        if warning not in warnings:
            warnings.append(warning)
    project_id = qa.get("projectId") or plan.get("projectId") or trace.get("projectId")
    if not project_id:
        raise ValueError("projectId 在 qa/edit-plan/source-timecode-list 三处均缺失，manifest 无所本（⑭ 缺席容错也要有出处）")
    evidence_refs = plan.get("evidenceRefs") or []
    if not evidence_refs:
        raise ValueError("edit-plan.json 缺顶层 evidenceRefs——manifest 的审批依据清单只能从包内计划抬取；"
                         "G5 装配步须在包内计划副本补登可定位路径（G2 决定/各节点门禁收据/批准记录等），"
                         "不得留空等校验末段才点名（⑮，zaku-003 ⑭ 修复彩排当场抓出）")
    review_points = plan.get("humanReviewPoints") or []
    if not review_points:
        raise ValueError("edit-plan.json 缺顶层 humanReviewPoints——人工审核点清单同样必须在 G5 装配步补登（⑮ 同款病）")
    manifest = {
        "schemaVersion": "0.1",
        "projectId": project_id,
        "node": "G5",
        "sourceProbe": probes,
        "segments": trace.get("segments", []),
        "editPlan": plan.get("editPlan", {}),
        "artifacts": {**qa.get("artifacts", {}), "editTimeline": artifact(timeline)},
        "qaReport": "metadata-validation-report.json",
        "humanReviewPoints": plan.get("humanReviewPoints", []),
        "humanReviewDecision": "human-review-decision.json",
        "evidenceRefs": plan.get("evidenceRefs", []),
        "warnings": warnings,
        "authorization": export.get("authorization", "not_specified"),
        "distribution": export.get("distribution", "not_specified"),
        "status": qa.get("status") or "pending_human_review",
        "finishedAt": qa.get("finishedAt"),
        "componentRefs": {
            "traceability": "source-timecode-list.json",
            "editPlan": "edit-plan.json",
            "exportConfig": "export-config.json",
            "qa": "metadata-validation-report.json",
            "humanReview": "human-review-decision.json"
        }
    }
    if plan.get("projectId") != manifest["projectId"] or (review and review.get("projectId") != manifest["projectId"]) \
            or (qa and qa.get("projectId") != manifest["projectId"]):
        raise ValueError("bundle component projectId mismatch")
    output = (args.output or bundle / "delivery-manifest.json").resolve()
    if output.parent != bundle:
        raise ValueError("output must be directly inside the delivery bundle")
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "created", "manifest": str(output), "segments": len(manifest["segments"])}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=True))
        raise SystemExit(2)
