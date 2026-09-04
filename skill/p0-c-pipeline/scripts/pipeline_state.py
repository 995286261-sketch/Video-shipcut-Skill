"""Strict state operations used internally by the conversational P0-C pipeline."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from project_layout import CHATCUT_DIRECTORY, require_g4_file, require_g5_file, require_project_file

NODES = ("G0", "G1", "G2", "G3", "G4", "G5")
STATES = {"pending", "in_progress", "review_required", "blocked", "completed", "completed_with_accepted_warnings"}


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def emit(value: dict, code: int = 0) -> None:
    print(json.dumps(value, ensure_ascii=True, indent=2))
    raise SystemExit(code)


def read_state(path: Path) -> dict:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        emit({"status": "invalid", "error": "state file not found", "path": str(path)}, 2)
    except json.JSONDecodeError as error:
        emit({"status": "invalid", "error": "state file is not valid UTF-8 JSON", "detail": str(error)}, 2)
    validate_state(state)
    return state


def validate_state(state: dict) -> None:
    missing = [key for key in ("schemaVersion", "projectId", "sourcePackRef", "authorization", "distribution", "currentNode", "status", "nodes", "nextAction", "createdAt", "updatedAt") if key not in state]
    if missing:
        emit({"status": "invalid", "error": "missing required state fields", "fields": missing}, 2)
    if state["schemaVersion"] != "0.1":
        emit({"status": "invalid", "error": "unsupported schemaVersion"}, 2)
    if state["currentNode"] not in {*NODES, "completed"}:
        emit({"status": "invalid", "error": "invalid currentNode"}, 2)
    if state["status"] not in STATES:
        emit({"status": "invalid", "error": "invalid project status"}, 2)
    for node in NODES:
        value = state["nodes"].get(node)
        if not isinstance(value, dict) or value.get("status") not in STATES:
            emit({"status": "invalid", "error": "invalid node state", "node": node}, 2)


def write_state(path: Path, state: dict) -> None:
    state["updatedAt"] = now()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def node_record(status: str = "pending") -> dict:
    return {"status": status, "inputRefs": [], "artifactRefs": [], "humanReviewPoints": [], "approval": None}


def next_action(node: str) -> str:
    actions = {
        "G1": "Run G1 direction confirmation.",
        "G2": "Prepare evidence, narration, and fact review.",
        "G3": "Prepare timecoded edit plan and request user review.",
        "G4": "Build and validate local candidate; use ChatCut only if micro-adjustment is requested.",
        "G5": "Run final QA and request human playback review.",
        "completed": "Local delivery is complete. Distribution remains subject to authorization.",
    }
    return actions[node]


def command_init(args: argparse.Namespace) -> None:
    source = Path(args.source_pack).resolve()
    if not source.is_file():
        emit({"status": "invalid", "error": "source material-pack.json not found", "path": str(source)}, 2)
    try:
        pack = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        emit({"status": "invalid", "error": "source material pack is invalid JSON", "detail": str(error)}, 2)
    if pack.get("packStatus") != "complete":
        emit({"status": "blocked", "error": "material pack is not complete"}, 2)
    destination = Path(args.state)
    if destination.exists():
        emit({"status": "blocked", "error": "state file already exists", "path": str(destination)}, 2)
    timestamp = now()
    state = {
        "schemaVersion": "0.1", "projectId": args.project_id, "sourcePackRef": str(source),
        "authorization": args.authorization, "distribution": args.distribution,
        "currentNode": "G1", "status": "in_progress",
        "nodes": {"G0": {"status": "completed", "artifactRefs": [str(source)], "inputRefs": [], "humanReviewPoints": [], "approval": None}, **{node: node_record("in_progress" if node == "G1" else "pending") for node in NODES if node != "G0"}},
        "acceptedWarnings": [], "nextAction": next_action("G1"), "createdAt": timestamp, "updatedAt": timestamp,
    }
    write_state(destination, state)
    emit({"status": "created", "state": str(destination), "currentNode": "G1", "nextAction": state["nextAction"]})


def command_status(args: argparse.Namespace) -> None:
    state = read_state(Path(args.state))
    node = state["currentNode"]
    record = state["nodes"].get(node, {})
    emit({"status": state["status"], "projectId": state["projectId"], "currentNode": node, "nodeStatus": record.get("status"), "inputRefs": record.get("inputRefs", []), "artifactRefs": record.get("artifactRefs", []), "humanReviewPoints": record.get("humanReviewPoints", []), "acceptedWarnings": state.get("acceptedWarnings", []), "nextAction": state["nextAction"]})


def command_record(args: argparse.Namespace) -> None:
    state_path = Path(args.state)
    state = read_state(state_path)
    if args.node != state["currentNode"]:
        emit({"status": "blocked", "error": "can only record the current node", "currentNode": state["currentNode"]}, 2)
    record = state["nodes"][args.node]
    record["status"] = args.node_status
    for field, value in (("inputRefs", args.input_ref), ("artifactRefs", args.artifact_ref), ("humanReviewPoints", args.review_point)):
        if value:
            record[field] = value
    state["status"] = args.node_status
    state["nextAction"] = "Resolve the listed review or blocker items." if args.node_status in {"review_required", "blocked"} else next_action(args.node)
    write_state(state_path, state)
    emit({"status": "recorded", "currentNode": args.node, "nodeStatus": args.node_status})


def command_reopen(args: argparse.Namespace) -> None:
    state_path = Path(args.state)
    state = read_state(state_path)
    if state["currentNode"] != "G3":
        emit({"status": "blocked", "error": "only an active G3 project can reopen G2", "currentNode": state["currentNode"]}, 2)
    if not args.reason or not args.rework_ref:
        emit({"status": "invalid", "error": "reopen requires reason and reworkRef"}, 2)
    history = state.setdefault("amendmentHistory", [])
    history.append({"fromNode": "G3", "toNode": "G2", "reason": args.reason, "reworkRef": args.rework_ref, "reopenedAt": now()})
    g2, g3 = state["nodes"]["G2"], state["nodes"]["G3"]
    g2["status"] = "in_progress"
    g2["approval"] = None
    g2["humanReviewPoints"] = list(dict.fromkeys(g2.get("humanReviewPoints", []) + ["reapprove_g2_amendment"]))
    g3["status"] = "pending"
    g3["humanReviewPoints"] = []
    g3["approval"] = None
    state["currentNode"] = "G2"
    state["status"] = "in_progress"
    state["nextAction"] = "Amend G2 evidence or approved narration, then request renewed G2 approval."
    write_state(state_path, state)
    emit({"status": "reopened", "currentNode": "G2", "nextAction": state["nextAction"], "amendment": history[-1]})


def command_reopen_g3(args: argparse.Namespace) -> None:
    state_path = Path(args.state)
    state = read_state(state_path)
    if state["currentNode"] != "G4":
        emit({"status": "blocked", "error": "only an active G4 project can reopen G3", "currentNode": state["currentNode"]}, 2)
    if not args.reason or not args.rework_ref:
        emit({"status": "invalid", "error": "reopen-g3 requires reason and reworkRef"}, 2)
    history = state.setdefault("amendmentHistory", [])
    history.append({"fromNode": "G4", "toNode": "G3", "reason": args.reason, "reworkRef": args.rework_ref, "reopenedAt": now()})
    g3, g4 = state["nodes"]["G3"], state["nodes"]["G4"]
    g3["status"] = "in_progress"
    g3["approval"] = None
    g3["humanReviewPoints"] = list(dict.fromkeys(g3.get("humanReviewPoints", []) + ["rebuild_semantic_alignment_and_reapprove_g3"]))
    g4["status"] = "pending"
    g4["inputRefs"] = []
    g4["humanReviewPoints"] = []
    state["currentNode"] = "G3"
    state["status"] = "in_progress"
    state["nextAction"] = "Rebuild narration-to-visual semantic alignment, then request renewed G3 approval."
    write_state(state_path, state)
    emit({"status": "reopened", "currentNode": "G3", "nextAction": state["nextAction"], "amendment": history[-1]})


def command_approve(args: argparse.Namespace) -> None:
    state_path = Path(args.state)
    state = read_state(state_path)
    node = args.node
    if node != state["currentNode"]:
        emit({"status": "blocked", "error": "approval does not match current node", "currentNode": state["currentNode"]}, 2)
    if not args.approval_ref:
        emit({"status": "invalid", "error": "approvalRef is required"}, 2)
    record = state["nodes"][node]
    try:
        require_project_file(state_path, args.approval_ref, "approvalRef")
    except ValueError as error:
        emit({"status": "blocked", "error": str(error)}, 2)
    approval = {"approvalRef": args.approval_ref, "approvedAt": now()}
    if node == "G2":
        if not args.approved_narration_ref or not args.fact_decision_ref or not args.voice_decision_ref:
            emit({"status": "blocked", "error": "G2 approval requires approvedNarrationRef, factDecisionRef, and voiceDecisionRef"}, 2)
        approval.update({"approvedNarrationRef": args.approved_narration_ref, "factDecisionRef": args.fact_decision_ref, "voiceDecisionRef": args.voice_decision_ref})
    if node == "G3":
        if not args.edit_plan_ref:
            emit({"status": "blocked", "error": "G3 approval requires editPlanRef"}, 2)
        if not args.timeline_review_ref:
            emit({"status": "blocked", "error": "G3 approval requires timelineReviewRef"}, 2)
        try:
            require_project_file(state_path, args.edit_plan_ref, "G3 editPlanRef")
            require_project_file(state_path, args.timeline_review_ref, "G3 timelineReviewRef")
        except ValueError as error:
            emit({"status": "blocked", "error": str(error)}, 2)
        approval["editPlanRef"] = args.edit_plan_ref
        approval["timelineReviewRef"] = args.timeline_review_ref
    if node == "G4":
        if args.g4_output_mode == "chatcut":
            if not args.chatcut_export_ref:
                emit({"status": "blocked", "error": "G4 ChatCut branch requires a ChatCut export reference"}, 2)
            try:
                export = require_g4_file(state_path, args.chatcut_export_ref, "G4 ChatCut export")
                if CHATCUT_DIRECTORY not in export.parts:
                    raise ValueError("G4 ChatCut export must be under ChatCut-导出")
            except ValueError as error:
                emit({"status": "blocked", "error": str(error)}, 2)
            approval["chatcutExportRef"] = args.chatcut_export_ref
            record["artifactRefs"] = list(dict.fromkeys(record["artifactRefs"] + [args.chatcut_export_ref]))
        else:
            if not args.local_render_ref or not args.g4_validation_ref:
                emit({"status": "blocked", "error": "G4 local-direct branch requires localRenderRef and g4ValidationRef"}, 2)
            try:
                require_g4_file(state_path, args.local_render_ref, "G4 localRenderRef")
                require_g4_file(state_path, args.g4_validation_ref, "G4 g4ValidationRef")
            except ValueError as error:
                emit({"status": "blocked", "error": str(error)}, 2)
            approval["localRenderRef"] = args.local_render_ref
            approval["g4ValidationRef"] = args.g4_validation_ref
            record["artifactRefs"] = list(dict.fromkeys(record["artifactRefs"] + [args.local_render_ref]))
        approval["outputMode"] = args.g4_output_mode
    if node == "G5":
        if not args.delivery_manifest_ref or not args.g5_validation_ref:
            emit({"status": "blocked", "error": "G5 approval requires deliveryManifestRef and g5ValidationRef"}, 2)
        try:
            manifest = require_g5_file(state_path, args.delivery_manifest_ref, "G5 deliveryManifestRef")
            require_g5_file(state_path, args.g5_validation_ref, "G5 g5ValidationRef")
            if manifest.name != "delivery-manifest.json":
                raise ValueError("G5 deliveryManifestRef must name delivery-manifest.json")
        except ValueError as error:
            emit({"status": "blocked", "error": str(error)}, 2)
        approval["deliveryManifestRef"] = args.delivery_manifest_ref
        approval["g5ValidationRef"] = args.g5_validation_ref
        if args.accepted_warning:
            state["acceptedWarnings"] = args.accepted_warning
        elif args.accepted_warnings:
            try:
                state["acceptedWarnings"] = json.loads(args.accepted_warnings)
            except json.JSONDecodeError:
                emit({"status": "invalid", "error": "acceptedWarnings must be JSON"}, 2)
    record["approval"] = approval
    record["status"] = "completed_with_accepted_warnings" if node == "G5" and state["acceptedWarnings"] else "completed"
    index = NODES.index(node)
    if node == "G5":
        state["currentNode"] = "completed"
        state["status"] = record["status"]
    else:
        following = NODES[index + 1]
        state["currentNode"] = following
        state["nodes"][following]["status"] = "in_progress"
        state["status"] = "in_progress"
    state["nextAction"] = next_action(state["currentNode"])
    write_state(state_path, state)
    emit({"status": "approved", "approvedNode": node, "currentNode": state["currentNode"], "nextAction": state["nextAction"]})


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    sub = result.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--project-id", required=True); init.add_argument("--source-pack", required=True); init.add_argument("--state", required=True)
    init.add_argument("--authorization", required=True); init.add_argument("--distribution", required=True); init.set_defaults(func=command_init)
    status = sub.add_parser("status"); status.add_argument("--state", required=True); status.set_defaults(func=command_status)
    record = sub.add_parser("record"); record.add_argument("--state", required=True); record.add_argument("--node", choices=NODES, required=True)
    record.add_argument("--node-status", choices=sorted(STATES), required=True); record.add_argument("--input-ref", action="append"); record.add_argument("--artifact-ref", action="append"); record.add_argument("--review-point", action="append"); record.set_defaults(func=command_record)
    approve = sub.add_parser("approve"); approve.add_argument("--state", required=True); approve.add_argument("--node", choices=NODES, required=True); approve.add_argument("--approval-ref", required=True)
    approve.add_argument("--approved-narration-ref"); approve.add_argument("--fact-decision-ref"); approve.add_argument("--voice-decision-ref"); approve.add_argument("--edit-plan-ref"); approve.add_argument("--timeline-review-ref"); approve.add_argument("--g4-output-mode", choices=("local_direct", "chatcut"), default="local_direct"); approve.add_argument("--local-render-ref"); approve.add_argument("--g4-validation-ref"); approve.add_argument("--chatcut-export-ref"); approve.add_argument("--delivery-manifest-ref"); approve.add_argument("--g5-validation-ref"); approve.add_argument("--accepted-warnings"); approve.add_argument("--accepted-warning", action="append"); approve.set_defaults(func=command_approve)
    reopen = sub.add_parser("reopen"); reopen.add_argument("--state", required=True); reopen.add_argument("--reason", required=True); reopen.add_argument("--rework-ref", required=True); reopen.set_defaults(func=command_reopen)
    reopen_g3 = sub.add_parser("reopen-g3"); reopen_g3.add_argument("--state", required=True); reopen_g3.add_argument("--reason", required=True); reopen_g3.add_argument("--rework-ref", required=True); reopen_g3.set_defaults(func=command_reopen_g3)
    return result


if __name__ == "__main__":
    args = parser().parse_args()
    args.func(args)
