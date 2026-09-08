"""Validate machine-checkable G1-G5 review-gate receipts."""
from __future__ import annotations

import json
from pathlib import Path

from project_layout import require_project_file

CARD_TYPES = {
    "G1": "g1_direction_review",
    "G2": "g2_evidence_narration_review",
    "G3": "g3_timeline_review",
    "G4": "g4_candidate_review",
    "G5": "g5_delivery_review",
}
REQUIRED_CHECKLIST_IDS = {
    "G1": {"direction_brief", "claims_and_boundaries", "direction_card"},
    "G2": {"fact_citation", "approved_narration", "voice_brief", "g2_card"},
    "G3": {"approved_edit_plan", "final_timeline_review", "subtitle_timeline", "bgm_decision", "g3_card"},
    "G4": {"candidate_or_export", "render_validation", "playback_review_card"},
    "G5": {"delivery_manifest", "qa_validation", "playback_review", "distribution_boundary"},
}


def load_review_gate(state_path: Path, reference: str, expected_node: str, expected_project_id: str) -> dict:
    path = require_project_file(state_path, reference, "reviewGateRef")
    try:
        receipt = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise ValueError(f"reviewGateRef must contain valid JSON: {error}") from error
    if not isinstance(receipt, dict):
        raise ValueError("reviewGateRef must contain a JSON object")
    if receipt.get("schemaVersion") != "0.1":
        raise ValueError("review gate receipt requires schemaVersion 0.1")
    if receipt.get("projectId") != expected_project_id:
        raise ValueError("review gate receipt projectId must match the active project")
    if receipt.get("node") != expected_node:
        raise ValueError(f"review gate receipt node must be {expected_node}")
    if receipt.get("cardType") != CARD_TYPES[expected_node]:
        raise ValueError(f"review gate receipt cardType must be {CARD_TYPES[expected_node]}")
    if receipt.get("reviewStatus") != "ready_for_approval":
        raise ValueError("review gate receipt must be ready_for_approval")
    if not isinstance(receipt.get("renderedAt"), str) or not receipt["renderedAt"].strip():
        raise ValueError("review gate receipt requires renderedAt")
    require_project_file(state_path, receipt.get("reviewCardRef", ""), "reviewCardRef")
    basis_refs = receipt.get("basisRefs")
    if not isinstance(basis_refs, list) or not basis_refs:
        raise ValueError("review gate receipt requires non-empty basisRefs")
    normalized_basis = []
    for reference_value in basis_refs:
        if not isinstance(reference_value, str) or not reference_value.strip():
            raise ValueError("review gate basisRefs must contain non-empty file references")
        require_project_file(state_path, reference_value, "review gate basisRef")
        normalized_basis.append(reference_value)
    checklist = receipt.get("checklist")
    if not isinstance(checklist, list):
        raise ValueError("review gate receipt requires checklist")
    required_ids = REQUIRED_CHECKLIST_IDS[expected_node]
    received = {}
    for item in checklist:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("review gate checklist items require id")
        item_id = item["id"]
        if item_id in received:
            raise ValueError(f"review gate checklist has duplicate id: {item_id}")
        received[item_id] = item
    if set(received) != required_ids:
        raise ValueError(f"review gate checklist must exactly contain: {', '.join(sorted(required_ids))}")
    for item_id in required_ids:
        item = received[item_id]
        if item.get("required") is not True or item.get("status") != "completed":
            raise ValueError(f"review gate checklist item {item_id} must be required and completed")
        evidence_ref = item.get("evidenceRef")
        if not isinstance(evidence_ref, str) or not evidence_ref.strip():
            raise ValueError(f"review gate checklist item {item_id} requires evidenceRef")
        require_project_file(state_path, evidence_ref, f"review gate evidenceRef for {item_id}")
    return {"reviewGateRef": reference, "cardType": receipt["cardType"], "basisRefs": normalized_basis, "checklistIds": sorted(required_ids), "renderedAt": receipt["renderedAt"]}


def require_basis_references(review_gate: dict, references: list[str]) -> None:
    missing = [reference for reference in references if reference not in review_gate["basisRefs"]]
    if missing:
        raise ValueError(f"review gate basisRefs must include approval references: {', '.join(missing)}")
