"""Strict state operations used internally by the conversational P0-C pipeline."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from project_layout import CHATCUT_DIRECTORY, require_g4_file, require_g5_file, require_project_file
from review_gate import load_review_gate, require_basis_references

NODES = ("G0", "G1", "G2", "G3", "G4", "G5")
STATES = {"pending", "in_progress", "review_required", "blocked", "completed", "completed_with_accepted_warnings"}


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# Issue ③: `--unicode` mirrors material_pack.py so Chinese state output stays
# readable without a decode pipe at every node. Machine consumers keep the
# default escaped form.
UNICODE_OUTPUT = False


def emit(value: dict, code: int = 0) -> None:
    print(json.dumps(value, ensure_ascii=not UNICODE_OUTPUT, indent=2))
    raise SystemExit(code)


def load_qa_report(path: Path, label: str) -> dict:
    try:
        report = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as error:
        raise ValueError(f"{label} 必须是可解析的 JSON 质检报告（门禁不得只查文件存在，Leader 反馈 R1）：{error}") from error
    if not isinstance(report, dict):
        raise ValueError(f"{label} 必须是 JSON 对象")
    return report


def validate_g4_report(report_path: Path, render_path: Path, project_id: str) -> None:
    # Leader 反馈 R1（方案 A，用户 09-23 裁决）：关单前解析 G4 质检报告——
    # status/projectId/候选成片指纹三对才放行；报告与成片非同一版=过期，逼重跑。
    report = load_qa_report(report_path, "G4 g4ValidationRef")
    if report.get("status") != "valid":
        raise ValueError(f"G4 质检报告 status={report.get('status')!r} 不可批准：只认 valid；invalid/failed 请回 G4 修复重验")
    if report.get("projectId") != project_id:
        raise ValueError(f"G4 质检报告 projectId={report.get('projectId')!r} 与当前项目 {project_id!r} 不符（张冠李戴报告不得过关）")
    candidate = report.get("candidate") if isinstance(report.get("candidate"), dict) else {}
    if not candidate.get("sha256"):
        raise ValueError("G4 质检报告未绑定候选成片指纹（candidate.sha256）：重跑 g4_validate.py --candidate <候选成片> 后再批准")
    if sha256_file(render_path) != str(candidate["sha256"]).upper():
        raise ValueError("G4 候选成片与质检报告指纹不符（报告生成后成片被重渲/改动=过期）：重跑 g4_validate.py --candidate")


G5_APPROVABLE_STATUSES = ("g5_pending_human_review", "valid")


def validate_g5_report(report_path: Path, project_id: str) -> None:
    # Leader 反馈 R1（方案 A）：关单前解析 G5 质检报告——status 可批值/projectId/
    # 逐件产物 sha256 重算比对（报告必须绑定它所验的交付包）。
    report = load_qa_report(report_path, "G5 g5ValidationRef")
    status = str(report.get("status") or "")
    if not (status in G5_APPROVABLE_STATUSES or status.startswith("completed")):
        raise ValueError(f"G5 质检报告 status={status!r} 不可批准：只放行 g5_pending_human_review/valid/completed*；invalid/failed/pending*（机器质检未完成）一律阻断")
    if report.get("projectId") != project_id:
        raise ValueError(f"G5 质检报告 projectId={report.get('projectId')!r} 与当前项目 {project_id!r} 不符")
    artifacts = report.get("artifacts") if isinstance(report.get("artifacts"), dict) else {}
    # 真实报告形状（sinjuku/tiger 实测）：值既可能是单条 {path,sha256}，
    # 也可能是逐章切片那样的列表 [{path,sha256},…]——两种都要吃下。
    entries = []
    for name in sorted(artifacts):
        value = artifacts[name]
        items = value if isinstance(value, list) else [value]
        for index, item in enumerate(items):
            entries.append((f"{name}[{index}]" if isinstance(value, list) else name, item))
    if not entries:
        raise ValueError("G5 质检报告未登记产物指纹（artifacts）：报告必须绑定交付包实物，重跑 G5 质检")
    for name, entry in entries:
        if not isinstance(entry, dict) or not entry.get("sha256") or not entry.get("path"):
            raise ValueError(f"G5 质检报告产物 {name} 缺 path/sha256 登记")
        target = report_path.parent / str(entry["path"])
        if not target.is_file():
            raise ValueError(f"G5 质检报告登记的产物 {name} 不在交付包中：{entry['path']}")
        if sha256_file(target) != str(entry["sha256"]).upper():
            raise ValueError(f"G5 交付包产物 {name} 与质检报告指纹不符（报告后产物被改动=过期）：重跑 G5 质检")


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
    return {"status": status, "inputRefs": [], "artifactRefs": [], "humanReviewPoints": [], "reviewGate": None, "approval": None}


def clear_review_gate(record: dict) -> None:
    record["reviewGate"] = None


APPROVAL_WITH_NODE = re.compile(r"^(?:确认|确定)\s*[Gg]?\s*(\d)$")
APPROVAL_BARE = re.compile(r"^(?:确认|确定)\s*了?\s*[。！!]?$")
# Issue ㉕ (sinjuku G4/G5 live runs): users type the exact token and then ask an
# unrelated question in the same message ("确认G5，那么……下一步是什么"), or phrase
# it as natural prose ("OK，那这个G4我确认了"). A natural reply is accepted only
# when it carries exactly one unconditional approval clause naming THIS node.
# Conservative by design: any conditional, negative, imperative, adversative or
# interrogative marker anywhere refuses the whole text — gate semantics must
# never be inferred from prose we are not sure about.
APPROVAL_CLAUSE_SPLIT = re.compile(r"[，,。．！!？?；;：:\n\r\t ]+")
APPROVAL_UNSAFE_MARKERS = re.compile(
    r"如果|假如|要是|万一|的话|就确认|再确认|先确认|先别|先不|等.{0,8}再|修改完|改完|修好"
    r"|不要|不确认|暂不|但|不过|除非|只有|才|帮我|请|帮忙|吗|还是|或者")


def _clause_names_only_node(clause: str, node: str) -> bool:
    digit = node[-1]
    if re.search(rf"[Gg]\s*{digit}(?![0-9])", clause) is None:
        return False
    return not any(re.search(rf"[Gg]\s*{other}(?![0-9])", clause) for other in "12345" if other != digit)


def _sentence_confirmation(node: str, text: str) -> tuple[str, bool] | None:
    clauses = [clause for clause in APPROVAL_CLAUSE_SPLIT.split(text) if clause]
    if not clauses or APPROVAL_UNSAFE_MARKERS.search(text):
        return None
    approved = [c for c in clauses if re.search(r"确认|确定", c) and _clause_names_only_node(c, node)]
    if len(approved) != 1:
        return None
    if any(re.search(r"确认|确定", c) for c in clauses if c is not approved[0]):
        return None
    return f"确认 {node}", True


def normalize_confirmation(node: str, raw: object) -> tuple[str, bool] | None:
    """Map a human reply to this node's canonical approval string, or None.

    Accepted: the exact canonical form, the no-space variants users actually
    type (确认G5 / 确认g5), the 确定 synonym (zaku G1 live run: users type
    确定G2), bare 确认/确定, and — since issue ㉕ — a natural reply whose only
    确认/确定 clause names this node unconditionally (e.g. "确认G5，那么下一步
    是什么"). Anything else (好的 / OK / 确认G for another node / conditional
    or imperative prose) is refused. The canonical string is what gets stored,
    so every downstream validator stays byte-identical."""
    expected = f"确认 {node}"
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if text == expected:
        return expected, False
    match = APPROVAL_WITH_NODE.match(text)
    if match:
        return (expected, True) if match.group(1) == node[-1] else None
    if APPROVAL_BARE.match(text):
        return expected, True
    return _sentence_confirmation(node, text)


def require_approval_token(node: str, token: str | None, response: str | None) -> tuple[str, str, str, str, bool]:
    expected = f"确认 {node}"
    token_norm = normalize_confirmation(node, token)
    if token_norm is None:
        raise ValueError(f"{node} approval 未识别为无条件批准（typed variants 与单一确认从句的自然语句自动归一、逐字原话保留；含条件/否定/他节点引用的语句拒绝）。请回精确口令：{expected}")
    response_norm = normalize_confirmation(node, response)
    if response_norm is None:
        raise ValueError(f"{node} approval 未识别为无条件批准（typed variants 与单一确认从句的自然语句自动归一、逐字原话保留；含条件/否定/他节点引用的语句拒绝）。请回精确口令：{expected}")
    return token_norm[0], response_norm[0], str(token).strip(), str(response).strip(), token_norm[1] or response_norm[1]


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
    bgm = pack.get("bgm") or {"decision": "unknown", "preference": None, "libraryPending": False, "clearCondition": None}
    bgm = {**bgm, "history": []}
    state = {
        "schemaVersion": "0.1", "projectId": args.project_id, "sourcePackRef": str(source),
        "authorization": args.authorization, "distribution": args.distribution, "bgm": bgm,
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
    review_gate = record.get("reviewGate")
    bgm = state.get("bgm") or {}
    if bgm.get("libraryPending"):
        bgm = {**bgm, "reminder": "BGM 待找乐：G1 末出检索词卡 → 找乐 → 用户挑曲 → 官方渠道取得整轨并登记 → `bgm-choice` 翻槽；G3 批准前槽必须已清"}
    emit({"status": state["status"], "projectId": state["projectId"], "currentNode": node, "nodeStatus": record.get("status"), "inputRefs": record.get("inputRefs", []), "artifactRefs": record.get("artifactRefs", []), "humanReviewPoints": record.get("humanReviewPoints", []), "reviewGate": review_gate, "reviewGateStatus": "ready" if review_gate else "missing", "acceptedWarnings": state.get("acceptedWarnings", []), "bgm": bgm, "nextAction": state["nextAction"]})


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def command_bgm_choice(args: argparse.Namespace) -> None:
    """Flip the G0 BGM slot with evidence. Pending never clears by talking; it
    clears by a registered file (provided) or the user's deliberate no-BGM call."""
    state_path = Path(args.state)
    state = read_state(state_path)
    bgm = state.get("bgm") or {"decision": "unknown", "preference": None, "libraryPending": False, "clearCondition": None}
    if args.decision == "provided" and not (args.evidence and args.evidence.strip()):
        emit({"status": "blocked", "error": "翻槽到 provided 必须携带登记证据（music-expert 登记记录路径 + 许可说明）"}, 2)
    if args.decision == "provided":
        # Issues ⑱/㉔: slot closure is only real when the registration record, the
        # physical audio, the material-pack manifest and the full-track analysis all
        # agree. Chat memory must never flip this slot.
        evidence_path = Path(args.evidence.strip())
        if not evidence_path.is_file():
            emit({"status": "blocked", "error": f"bgm-choice 证据文件不存在：{evidence_path}（登记记录必须已落盘）"}, 2)
        try:
            registration = json.loads(evidence_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as error:
            emit({"status": "blocked", "error": f"bgm-choice 证据不是合法登记记录 JSON：{error}"}, 2)
            return
        audio_path = Path(registration.get("audioPath", ""))
        recorded_sha = (registration.get("sha256") or "").upper()
        if not audio_path.is_file() or not recorded_sha or sha256_file(audio_path).upper() != recorded_sha:
            emit({"status": "blocked", "error": "bgm-choice 证据未与音频配对：登记记录的 audioPath 不存在或 SHA-256 与盘上字节不符"}, 2)
        pack = Path(state.get("sourcePackRef", ""))
        if not pack.is_file():
            emit({"status": "blocked", "error": f"bgm-choice 时素材包 manifest 未就位：{pack}（先完成 register 再翻槽）"}, 2)
        pack_doc = json.loads(pack.read_text(encoding="utf-8-sig"))
        assets = [a for a in pack_doc.get("audioAssets", []) if (a.get("sha256") or "").upper() == recorded_sha]
        if not assets:
            emit({"status": "blocked", "error": "bgm-choice 时 material-pack 尚无该音频登记（sha 未入册）：register 未跑或登记未回填"}, 2)
        if not any(a.get("bgmAnalysis") for a in assets) and not (registration.get("analysisRef") or "").strip():
            emit({"status": "blocked", "error": "槽关单必须已登记整轨分析报告（㉔）：跑 music_analyze 并回填 audioAssets[].bgmAnalysis 或登记记录 analysisRef 后再翻槽"}, 2)
    history = bgm.setdefault("history", [])
    history.append({"at": now(), "from": bgm.get("decision"), "to": args.decision,
                    "evidence": args.evidence, "note": args.note})
    bgm.update({"decision": args.decision, "libraryPending": args.decision == "use_library_later",
                "evidence": args.evidence if args.decision == "provided" else None})
    if args.preference:
        bgm["preference"] = args.preference
    state["bgm"] = bgm
    state["updatedAt"] = now()
    write_state(state_path, state)
    emit({"status": "recorded", "action": "bgm-choice", "decision": args.decision, "libraryPending": bgm["libraryPending"]})


def command_record(args: argparse.Namespace) -> None:
    state_path = Path(args.state)
    state = read_state(state_path)
    if args.node != state["currentNode"]:
        emit({"status": "blocked", "error": "can only record the current node", "currentNode": state["currentNode"]}, 2)
    record = state["nodes"][args.node]
    if args.node_status != "review_required" or record.get("status") != "review_required":
        clear_review_gate(record)
    record["status"] = args.node_status
    for field, value in (("inputRefs", args.input_ref), ("artifactRefs", args.artifact_ref), ("humanReviewPoints", args.review_point)):
        if value:
            record[field] = value
    state["status"] = args.node_status
    state["nextAction"] = "Resolve the listed review or blocker items." if args.node_status in {"review_required", "blocked"} else next_action(args.node)
    write_state(state_path, state)
    emit({"status": "recorded", "currentNode": args.node, "nodeStatus": args.node_status})


def command_record_review(args: argparse.Namespace) -> None:
    state_path = Path(args.state)
    state = read_state(state_path)
    if args.node != state["currentNode"]:
        emit({"status": "blocked", "error": "can only record review for the current node", "currentNode": state["currentNode"]}, 2)
    record = state["nodes"][args.node]
    if record["status"] != "review_required":
        emit({"status": "blocked", "error": "review gate can only be recorded while node is review_required", "nodeStatus": record["status"]}, 2)
    try:
        record["reviewGate"] = load_review_gate(state_path, args.review_gate_ref, args.node, state["projectId"])
    except ValueError as error:
        emit({"status": "blocked", "error": str(error)}, 2)
    write_state(state_path, state)
    emit({"status": "review_recorded", "currentNode": args.node, "reviewGate": record["reviewGate"], "nextAction": f"Present the registered card and wait for the exact response 确认 {args.node}."})


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
    clear_review_gate(g2)
    g2["approval"] = None
    g2["humanReviewPoints"] = list(dict.fromkeys(g2.get("humanReviewPoints", []) + ["reapprove_g2_amendment"]))
    g3["status"] = "pending"
    clear_review_gate(g3)
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
    # 验收003-㉗：G4 关单进入 G5 后同样可能需要回退 G3（批准范围分歧等），
    # 原实现只允许 currentNode==G4，跨节点回退无合法路径。允许 G4/G5，回退时连带重置 G5。
    if state["currentNode"] not in ("G4", "G5"):
        emit({"status": "blocked", "error": "only an active G4/G5 project can reopen G3", "currentNode": state["currentNode"]}, 2)
    if not args.reason or not args.rework_ref:
        emit({"status": "invalid", "error": "reopen-g3 requires reason and reworkRef"}, 2)
    history = state.setdefault("amendmentHistory", [])
    history.append({"fromNode": state["currentNode"], "toNode": "G3", "reason": args.reason, "reworkRef": args.rework_ref, "reopenedAt": now()})
    if state["currentNode"] == "G5":
        g5 = state["nodes"]["G5"]
        g5["status"] = "pending"
        clear_review_gate(g5)
        g5["approval"] = None
        g5["inputRefs"] = []
        g5["humanReviewPoints"] = []
    g3, g4 = state["nodes"]["G3"], state["nodes"]["G4"]
    g3["status"] = "in_progress"
    clear_review_gate(g3)
    g3["approval"] = None
    g3["humanReviewPoints"] = list(dict.fromkeys(g3.get("humanReviewPoints", []) + ["rebuild_semantic_alignment_and_reapprove_g3"]))
    g4["status"] = "pending"
    clear_review_gate(g4)
    g4["approval"] = None
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
    if record.get("status") != "review_required":
        emit({"status": "blocked", "error": "approval requires the node to be review_required", "nodeStatus": record.get("status")}, 2)
    if not record.get("reviewGate"):
        emit({"status": "blocked", "error": "approval requires a recorded review gate"}, 2)
    # Issue 002-⑦: the receipt file may have changed after record-review. Compare the live
    # receipt against the frozen snapshot BEFORE blaming a missing basisRef on stale data.
    try:
        fresh_gate = load_review_gate(state_path, record["reviewGate"]["reviewGateRef"], node, state["projectId"])
    except ValueError as error:
        emit({"status": "blocked", "error": f"review gate receipt no longer valid: {error}"}, 2)
    if fresh_gate != record["reviewGate"]:
        emit({"status": "blocked",
              "error": "review gate receipt changed since record-review (renderedAt/basisRefs/checklist); re-run record-review before approving"}, 2)
    if node in ("G2", "G3") and (state.get("bgm") or {}).get("libraryPending"):
        emit({"status": "blocked", "error": f"{node} 批准被 BGM 待找乐槽拦住：音乐须在首个消费节点前在场（N9 顺序）。挑曲→官方渠道取得整轨→登记→bgm-choice 翻槽后再批"}, 2)
    try:
        approval_token, approval_response, token_verbatim, response_verbatim, normalized = require_approval_token(
            node, args.approval_token, args.approval_response)
        require_project_file(state_path, args.approval_ref, "approvalRef")
        require_basis_references(record["reviewGate"], [args.approval_ref])
    except ValueError as error:
        emit({"status": "blocked", "error": str(error)}, 2)
    approval = {"approvalRef": args.approval_ref, "reviewGateRef": record["reviewGate"]["reviewGateRef"], "approvalToken": approval_token, "approvalResponse": approval_response,
                "approvalTokenVerbatim": token_verbatim, "approvalResponseVerbatim": response_verbatim,
                "normalizedFromVariant": normalized, "approvedAt": now()}
    if node == "G2":
        if not args.approved_narration_ref or not args.fact_citation_ref or not args.voice_brief_ref:
            emit({"status": "blocked", "error": "G2 approval requires approvedNarrationRef, factCitationRef, and voiceBriefRef"}, 2)
        try:
            for label, reference in (("G2 approvedNarrationRef", args.approved_narration_ref), ("G2 factCitationRef", args.fact_citation_ref), ("G2 voiceBriefRef", args.voice_brief_ref)):
                require_project_file(state_path, reference, label)
            require_basis_references(record["reviewGate"], [args.approved_narration_ref, args.fact_citation_ref, args.voice_brief_ref])
        except ValueError as error:
            emit({"status": "blocked", "error": str(error)}, 2)
        approval.update({"approvedNarrationRef": args.approved_narration_ref, "factCitationRef": args.fact_citation_ref, "voiceBriefRef": args.voice_brief_ref})
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
        try:
            require_basis_references(record["reviewGate"], [args.edit_plan_ref, args.timeline_review_ref])
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
            try:
                require_basis_references(record["reviewGate"], [args.chatcut_export_ref])
            except ValueError as error:
                emit({"status": "blocked", "error": str(error)}, 2)
            approval["chatcutExportRef"] = args.chatcut_export_ref
            record["artifactRefs"] = list(dict.fromkeys(record["artifactRefs"] + [args.chatcut_export_ref]))
        else:
            if not args.local_render_ref or not args.g4_validation_ref:
                emit({"status": "blocked", "error": "G4 local-direct branch requires localRenderRef and g4ValidationRef"}, 2)
            try:
                render_path = require_g4_file(state_path, args.local_render_ref, "G4 localRenderRef")
                report_path = require_g4_file(state_path, args.g4_validation_ref, "G4 g4ValidationRef")
                validate_g4_report(report_path, render_path, state["projectId"])
            except ValueError as error:
                emit({"status": "blocked", "error": str(error)}, 2)
            try:
                require_basis_references(record["reviewGate"], [args.local_render_ref, args.g4_validation_ref])
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
            report_path = require_g5_file(state_path, args.g5_validation_ref, "G5 g5ValidationRef")
            if manifest.name != "delivery-manifest.json":
                raise ValueError("G5 deliveryManifestRef must name delivery-manifest.json")
            validate_g5_report(report_path, state["projectId"])
        except ValueError as error:
            emit({"status": "blocked", "error": str(error)}, 2)
        try:
            require_basis_references(record["reviewGate"], [args.delivery_manifest_ref, args.g5_validation_ref])
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
    review = sub.add_parser("record-review"); review.add_argument("--state", required=True); review.add_argument("--node", choices=NODES[1:], required=True); review.add_argument("--review-gate-ref", required=True); review.set_defaults(func=command_record_review)
    bgm = sub.add_parser("bgm-choice"); bgm.add_argument("--state", required=True)
    bgm.add_argument("--decision", required=True, choices=("provided", "use_library_later", "no_bgm"))
    bgm.add_argument("--preference"); bgm.add_argument("--evidence"); bgm.add_argument("--note")
    bgm.set_defaults(func=command_bgm_choice)
    approve = sub.add_parser("approve"); approve.add_argument("--state", required=True); approve.add_argument("--node", choices=NODES, required=True); approve.add_argument("--approval-ref", required=True); approve.add_argument("--approval-token", required=True); approve.add_argument("--approval-response", required=True)
    approve.add_argument("--approved-narration-ref"); approve.add_argument("--fact-citation-ref"); approve.add_argument("--voice-brief-ref"); approve.add_argument("--edit-plan-ref"); approve.add_argument("--timeline-review-ref"); approve.add_argument("--g4-output-mode", choices=("local_direct", "chatcut"), default="local_direct"); approve.add_argument("--local-render-ref"); approve.add_argument("--g4-validation-ref"); approve.add_argument("--chatcut-export-ref"); approve.add_argument("--delivery-manifest-ref"); approve.add_argument("--g5-validation-ref"); approve.add_argument("--accepted-warnings"); approve.add_argument("--accepted-warning", action="append"); approve.set_defaults(func=command_approve)
    reopen = sub.add_parser("reopen"); reopen.add_argument("--state", required=True); reopen.add_argument("--reason", required=True); reopen.add_argument("--rework-ref", required=True); reopen.set_defaults(func=command_reopen)
    reopen_g3 = sub.add_parser("reopen-g3"); reopen_g3.add_argument("--state", required=True); reopen_g3.add_argument("--reason", required=True); reopen_g3.add_argument("--rework-ref", required=True); reopen_g3.set_defaults(func=command_reopen_g3)
    for command in (init, status, record, review, bgm, approve, reopen, reopen_g3):
        command.add_argument("--unicode", action="store_true", help="Emit readable Unicode JSON for UTF-8 terminals")
    return result


if __name__ == "__main__":
    args = parser().parse_args()
    if getattr(args, "unicode", False):
        UNICODE_OUTPUT = True
    args.func(args)
