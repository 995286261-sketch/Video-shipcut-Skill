#!/usr/bin/env python3
"""Validate the canonical G2 review-decision schema consumed by G3."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED_REFERENCES = ("approvedNarrationRef", "factCitationRef", "voiceBriefRef")


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


def validate(decision: dict, project_root: Path) -> None:
    if decision.get("schemaVersion") != "0.1":
        fail("G2 decision schemaVersion must be 0.1")
    if decision.get("node") != "G2":
        fail("G2 decision must belong to node G2")
    if not isinstance(decision.get("projectId"), str) or not decision["projectId"].strip():
        fail("G2 decision requires projectId")
    if decision.get("status") != "approved_for_g3":
        fail("G2 decision is not approved_for_g3")
    for field in REQUIRED_REFERENCES:
        require_file(decision.get(field), field, project_root)
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
