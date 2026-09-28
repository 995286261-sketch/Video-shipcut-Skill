#!/usr/bin/env python3
"""Validate the canonical G2 review-decision schema consumed by G3.

Schema 0.2 (响度接线工单批一, 2026-09-28): narration decisions must carry
`loudnessPlanRef` pointing at a loudness-expert 《响度-归一化计划》artifact.
This validator re-checks the artifact header, the narration source file on
disk, and its sha256 against the plan — so a G2 approval cannot close with an
undisclosed loudness ceiling, and cannot survive a re-synthesized narration
without a re-plan. Historical 0.1 decisions are not retroactive (R3 policy:
completed projects never re-run this gate).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

REQUIRED_REFERENCES = ("approvedNarrationRef", "factCitationRef", "voiceBriefRef", "loudnessPlanRef")
LOUDNESS_SKILL = "loudness-expert"
LOUDNESS_PURPOSE = "loud_plan"


def fail(message: str) -> None:
    raise ValueError(message)


def require_file(reference: object, label: str, project_root: Path) -> Path:
    if not isinstance(reference, str) or not reference.strip():
        fail(f"G2 decision requires {label}")
    path = Path(reference)
    if not path.is_absolute():
        path = project_root / path
    if not path.is_file():
        fail(f"{label} must be an existing project file, not a directory: {reference}")
    return path.resolve()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(str(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def validate_loudness_plan(decision: dict, project_root: Path) -> None:
    """响度接线批一：loudnessPlanRef 必须是指向旁白源的真实专员产物，且源未变更。

    只消费 loudness-expert 落盘产物做对账（跨专员零 import，合同 §8）；
    blocked 计划同样可以是合法披露（天花板摊开、用户在选项卡上拍了出路），
    合法与否由卡片审批留痕裁决，本函数只保证"数字来自专员实测、旁白没被换过"。
    """
    path = require_file(decision.get("loudnessPlanRef"), "loudnessPlanRef", project_root)
    try:
        plan = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        fail(f"loudnessPlanRef is not parseable JSON: {error}")
    if not isinstance(plan, dict) or plan.get("skill") != LOUDNESS_SKILL or plan.get("purpose") != LOUDNESS_PURPOSE:
        fail("loudnessPlanRef must be a loudness-expert loud_plan artifact (run loud_measure.py + loud_plan.py on the narration source first)")
    status = str(plan.get("status", ""))
    if status != "ready" and not status.startswith("blocked"):
        fail(f"loudness plan status not recognized: {status!r} (expected ready or blocked_*)")
    source = plan.get("source")
    if not isinstance(source, str) or not source.strip():
        fail("loudness plan lacks source (the narration file the ceiling was measured from)")
    source_path = Path(source)
    if not source_path.is_absolute():
        source_path = project_root / source_path
    if not source_path.is_file():
        fail(f"loudness plan narration source is missing on disk: {source}")
    if plan.get("sha256") != sha256_file(source_path):
        fail("narration changed after loudness planning (sha256 mismatch): re-synthesize, re-run loud_plan, and re-present the audition card before approval")


def validate(decision: dict, project_root: Path) -> None:
    if decision.get("schemaVersion") != "0.2":
        fail("G2 decision schemaVersion must be 0.2 (loudness wiring: decisions require loudnessPlanRef)")
    if decision.get("node") != "G2":
        fail("G2 decision must belong to node G2")
    if not isinstance(decision.get("projectId"), str) or not decision["projectId"].strip():
        fail("G2 decision requires projectId")
    if decision.get("status") != "approved_for_g3":
        fail("G2 decision is not approved_for_g3")
    for field in REQUIRED_REFERENCES:
        require_file(decision.get(field), field, project_root)
    validate_loudness_plan(decision, project_root)
    for field in ("permittedFactIds", "prohibitedTopics", "supersededDraftRefs"):
        value = decision.get(field, []) if field == "supersededDraftRefs" else decision.get(field)
        if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
            fail(f"G2 decision requires {field} to be a list of non-empty strings")
    claims = decision.get("userManuallyVerifiedClaims", [])
    if not isinstance(claims, list) or not all(isinstance(item, str) and item.strip() for item in claims):
        fail("userManuallyVerifiedClaims must be a list of non-empty strings")
    if claims:
        provenance = decision.get("provenanceRule")
        if not isinstance(provenance, str) or "not" not in provenance.lower() or "first" not in provenance.lower():
            fail("manually verified claims require a provenanceRule stating they are not first-party verified")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--decision", required=True, type=Path)
    parser.add_argument("--project-root", required=True, type=Path)
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    decision = json.loads(args.decision.read_text(encoding="utf-8-sig"))
    if not isinstance(decision, dict):
        fail("G2 decision must be a JSON object")
    validate(decision, project_root)
    print(json.dumps({"status": "completed", "projectId": decision["projectId"], "schema": "g2-approved-for-g3"}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "invalid", "error": str(error)}, ensure_ascii=True))
        raise SystemExit(2)
