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
    qa = load(bundle / "metadata-validation-report.json")
    review = load(bundle / "human-review-decision.json")
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
    manifest = {
        "schemaVersion": "0.1",
        "projectId": qa["projectId"],
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
        "status": qa.get("status"),
        "finishedAt": qa.get("finishedAt"),
        "componentRefs": {
            "traceability": "source-timecode-list.json",
            "editPlan": "edit-plan.json",
            "exportConfig": "export-config.json",
            "qa": "metadata-validation-report.json",
            "humanReview": "human-review-decision.json"
        }
    }
    if plan.get("projectId") != manifest["projectId"] or review.get("projectId") != manifest["projectId"]:
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
