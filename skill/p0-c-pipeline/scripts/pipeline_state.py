"""Strict state operations used internally by the conversational P0-C pipeline."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from project_layout import (CHATCUT_DIRECTORY, choice_file, require_g4_file, require_g5_file,
                            resolve_workspace_root, require_project_file, set_choice,
                            workspace_gate, WORKSPACE_DIR_NAME, WORKSPACE_HOME_ENV)
from review_gate import load_review_gate, require_basis_references, reviewed_file_hashes, sha256_file

NODES = ("G0", "G1", "G2", "G3", "G4", "G5")
STATES = {"pending", "in_progress", "review_required", "blocked", "completed", "completed_with_accepted_warnings",
          # v1.22.0 自动确认模式：G5 经 auto-policy 关单的项目终态（人工听感验收未执行、如实披露）。
          "completed_auto_reviewed", "completed_auto_reviewed_with_accepted_warnings"}
APPROVAL_MODES = ("human", "auto")
# 预授权受控词表（七类）。词表外的类别写进策略文件=当场拒——
# 未清权×对外、授权不明×对外、人工背书断言（userManuallyVerifiedClaims）
# 属永久 fail-stop，不可预授权，词表里根本没有它们。
AUTO_PREAUTH_CATEGORIES = (
    "preview_voice_production", "loudness_blocked_exit", "transition_preview_waiver",
    "subject_policy", "warning_acceptance", "sufficiency_shorten", "music_delegated_selection",
)
INWARD_DISTRIBUTION = {"internal_test", "local_only", "not_for_distribution"}
UNCLEARED_LICENSES = {"uncleared-platform-catalog", "unverified", ""}


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
    # v1.22.0：历史 state 无 approvalMode 字段 = human（R3 不追溯，旧项目零影响）。
    mode = state.get("approvalMode", "human")
    if mode not in APPROVAL_MODES:
        emit({"status": "invalid", "error": f"unsupported approvalMode: {mode!r} (human|auto)"}, 2)
    if mode == "auto" and not str(state.get("autoPolicyRef") or "").strip():
        emit({"status": "invalid", "error": "approvalMode=auto requires autoPolicyRef (无策略不自动——fail-stop 而非放行)"}, 2)
    for node in NODES:
        value = state["nodes"].get(node)
        if not isinstance(value, dict) or value.get("status") not in STATES:
            emit({"status": "invalid", "error": "invalid node state", "node": node}, 2)
    # v1.34.0 能力预检申报：块可选——老项目无块＝legacy 不追溯；在场必须形状齐
    #（申报形状歪而运行时对的 v0.13.1 教训：歪形状当场拒，不许半块上岗）。
    audit = state.get("capabilityAudit")
    if audit is not None:
        absent = [key for key in ("file", "sha256", "probedAt", "summary") if key not in audit]
        if absent:
            emit({"status": "invalid", "error": "capabilityAudit 块缺必备字段", "fields": absent}, 2)


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


# ---- v1.22.0 自动确认模式（approvalMode=auto）----
# 批准人从"宿主会话真人口令"换成"输入端策略"：机器验收链（收据对账/basisHashes/
# 节点 validator/R1 报告解析）全部照跑，只是口令段被信任类预检替代。红线：绝不伪造
# 人类原话——auto 留痕写 approvalSource=auto-policy、verbatim=策略条款原文；
# 未被预授权覆盖的信任类事项一律 fail-stop（宁可停不可猜）。

def validate_policy_doc(policy: object, project_id: str) -> dict:
    if not isinstance(policy, dict):
        raise ValueError("auto-approval 策略必须是 JSON 对象")
    if policy.get("schemaVersion") != "0.1" or policy.get("kind") != "auto-approval-policy":
        raise ValueError("auto-approval 策略要求 schemaVersion 0.1 / kind auto-approval-policy")
    if policy.get("projectId") != project_id:
        raise ValueError(f"auto-approval 策略 projectId={policy.get('projectId')!r} 与当前项目 {project_id!r} 不符（别项目的策略不得管本项目）")
    if not isinstance(policy.get("statement"), str) or not policy["statement"].strip():
        raise ValueError("auto-approval 策略缺 statement（自动批准的逐字依据：人话写明批准语义与范围）")
    entries = policy.get("preAuthorizations", [])
    if not isinstance(entries, list):
        raise ValueError("preAuthorizations 必须是列表")
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("每条 preAuthorization 必须是对象")
        category = entry.get("category")
        if category not in AUTO_PREAUTH_CATEGORIES:
            raise ValueError(f"预授权类别 {category!r} 不在受控词表 {list(AUTO_PREAUTH_CATEGORIES)}——未清权×对外分发、授权不明×对外、人工背书断言永久不可预授权，词表不可扩展")
        for field in ("basis", "authorizedBy", "authorizedAt"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise ValueError(f"预授权 {category} 缺 {field}（依据/授权人/时间三件必须齐）")
        params = entry.get("parameters")
        if params is not None and not isinstance(params, dict):
            raise ValueError(f"预授权 {category} 的 parameters 必须是对象")
        params = params or {}
        if category == "preview_voice_production" and "预览级" not in str(params.get("disclosure") or "") + str(entry.get("basis") or ""):
            raise ValueError("preview_voice_production 预授权必须在 basis 或 parameters.disclosure 含披露词'预览级'（绿灯通道的披露词在自动模式一字不松）")
        if category == "loudness_blocked_exit" and not str(params.get("exit") or "").strip():
            raise ValueError("loudness_blocked_exit 预授权必须用 parameters.exit 指明走哪条出路（不得概括放行）")
        if category == "warning_acceptance":
            scopes = params.get("scopes")
            if not isinstance(scopes, list) or not scopes or not all(isinstance(item, str) and item.strip() for item in scopes):
                raise ValueError("warning_acceptance 预授权必须带 parameters.scopes（警告关键词列表，不得概括放行）")
    return policy


def load_policy_file(raw_path: object, project_id: str) -> tuple[Path, dict]:
    path = Path(str(raw_path).strip())
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.is_file():
        raise ValueError(f"auto-policy 文件不存在：{path}")
    try:
        policy = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as error:
        raise ValueError(f"auto-policy 不是可解析 JSON：{error}") from error
    return path, validate_policy_doc(policy, project_id)


def load_auto_policy(state_path: Path, state: dict) -> dict:
    path = require_project_file(state_path, str(state.get("autoPolicyRef") or ""), "autoPolicyRef")
    try:
        policy = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as error:
        raise ValueError(f"auto-approval 策略不是可解析 JSON：{error}") from error
    return validate_policy_doc(policy, state["projectId"])


def validate_distribution_rights(state: dict) -> list:
    """auto 模式专属永久闸（v1.22.0 补上现存缺口）：对外分发 × 未清权音频/授权不明。
    human 模式行为不变（R3 不追溯；人审 distribution_boundary 项照旧覆盖）。
    分布值不在已知内向词表=按对外处理（保守）。"""
    distribution = str(state.get("distribution") or "").strip()
    if distribution.lower() in INWARD_DISTRIBUTION:
        return []
    problems = []
    authorization = str(state.get("authorization") or "")
    if re.search(r"unknown|unclear|待确认|pending", authorization, re.I):
        problems.append(f"授权不明（{authorization!r}）× 对外分发（{distribution!r}）：不得对外（永久不可预授权）")
    pack_path = Path(state.get("sourcePackRef") or "")
    pack = {}
    if pack_path.is_file():
        try:
            pack = json.loads(pack_path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            pack = {}
    assets = pack.get("audioAssets") if isinstance(pack.get("audioAssets"), list) else []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        license_value = str(asset.get("licenseType") or asset.get("license") or "").strip()
        if license_value.lower() in UNCLEARED_LICENSES or "uncleared" in license_value.lower():
            label = asset.get("assetId") or asset.get("path") or asset.get("relativePath") or "未标注音频"
            problems.append(f"音频资产 {label} 许可 {license_value!r} 未清权 × 对外分发（{distribution!r}）：未清权音频不得对外（永久不可预授权）")
    return problems


def _resolve_ref(state_path: Path, ref: object):
    """与 require_project_file 同语义的宽容解析：先按调用方 CWD，再按项目根。
    解析不到返回 None——机械判据只判在场的机械事实。"""
    if not isinstance(ref, str) or not ref.strip():
        return None
    candidate = Path(ref)
    if candidate.is_file():
        return candidate
    fallback = state_path.parent / ref
    return fallback if fallback.is_file() else None


def _json_docs(state_path: Path, refs):
    docs = []
    for ref in refs or []:
        path = _resolve_ref(state_path, ref)
        if path is None or path.suffix.lower() != ".json":
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            continue
        if isinstance(doc, dict):
            docs.append((str(ref), doc))
    return docs


def scan_trust_markers(state_path: Path, state: dict, record: dict, args) -> dict:
    """从被审面（收据 basisRefs + 本次批准载荷）收集信任类标记。
    标记不在场不触发；在场而策略未预授权覆盖 = fail-stop。"""
    refs = list(record["reviewGate"].get("basisRefs") or [])
    for extra in (getattr(args, "voice_brief_ref", None), getattr(args, "edit_plan_ref", None)):
        if extra:
            refs.append(extra)
    markers = {"preview_voice": False, "loudness_blocked": None, "transition_waiver": False,
               "sufficiency_shorten": False, "disclosed_exceedance": False, "permanent": []}
    for _ref, doc in _json_docs(state_path, refs):
        if doc.get("voiceTier") == "preview_only":
            markers["preview_voice"] = True
        if doc.get("skill") == "loudness-expert" and doc.get("purpose") == "loud_plan" \
                and str(doc.get("status") or "").startswith("blocked"):
            markers["loudness_blocked"] = doc.get("exits") if isinstance(doc.get("exits"), list) else []
        if "transitionPreviewWaiver" in doc:
            markers["transition_waiver"] = True
        subject = doc.get("targetSubject")
        if isinstance(subject, dict) and isinstance(subject.get("sufficiencyFallback"), dict):
            markers["sufficiency_shorten"] = True
        claims = doc.get("userManuallyVerifiedClaims")
        if isinstance(claims, list) and claims:
            markers["permanent"].append("userManuallyVerifiedClaims 非空：人工背书断言属人工批准的项目，自动模式项目不得携带（永久不可预授权）")
        pure = doc.get("pureNarration")
        if isinstance(pure, dict) and pure.get("verdict") == "disclosed-exceedance":
            markers["disclosed_exceedance"] = True
        if doc.get("skill") == "loudness-expert" and doc.get("status") == "disclosed-exceedance":
            markers["disclosed_exceedance"] = True
    markers["permanent"].extend(validate_distribution_rights(state))
    return markers


def require_auto_approval(state_path: Path, state: dict, node: str, record: dict, args) -> dict:
    """自动批准：机器验收已在本链上游全部通过，此处只做信任类预检。
    返回写进 approval 记录的字段（approvalSource=auto-policy，verbatim=策略条款原文）。"""
    policy = load_auto_policy(state_path, state)
    markers = scan_trust_markers(state_path, state, record, args)
    if node == "G5":
        # 响度验收审计在交付包目录（不在收据引用面），按合同固定名补读。
        manifest_path = _resolve_ref(state_path, getattr(args, "delivery_manifest_ref", None))
        audit_path = manifest_path.parent / "loudness-audit.json" if manifest_path else None
        if audit_path and audit_path.is_file():
            try:
                audit = json.loads(audit_path.read_text(encoding="utf-8-sig"))
            except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                audit = None
            if isinstance(audit, dict) and audit.get("status") == "disclosed-exceedance":
                markers["disclosed_exceedance"] = True
    missing, used = [], []

    def cover(category, reason, decision, entry_check=None):
        entries = [entry for entry in policy.get("preAuthorizations", []) if entry.get("category") == category]
        if not entries:
            missing.append({"category": category, "reason": reason, "decisionNeeded": decision})
        elif entry_check is not None and not any(entry_check(entry) for entry in entries):
            missing.append({"category": category, "reason": reason, "decisionNeeded": decision,
                            "note": "策略已有该预授权但参数与现场事实对不上（机械判据只判在场事实，参数不得概括放行）"})
        elif category not in used:
            used.append(category)

    if markers["preview_voice"]:
        cover("preview_voice_production",
              "配音清单声明 voiceTier=preview_only（系统声预览级）：升成品级必须知情批准",
              "人工试听后口令裁决本闸，或在策略中补 preview_voice_production 预授权（披露词'预览级'必须在场）")
    if markers["loudness_blocked"] is not None:
        def exit_matches(entry):
            choice = str((entry.get("parameters") or {}).get("exit") or "").strip()
            exits = markers["loudness_blocked"]
            if not choice:
                return False
            if not exits or not all(isinstance(item, str) for item in exits):
                return True
            return any(choice in item or item in choice for item in exits)
        cover("loudness_blocked_exit",
              "响度计划为 blocked_*（现天花板够不到目标）：出路必须显式选择，不得自动放行",
              "人工在出路卡上选择，或在策略中补 loudness_blocked_exit 预授权（parameters.exit 指明出路）",
              entry_check=exit_matches)
    if markers["transition_waiver"]:
        cover("transition_preview_waiver",
              "转场试装预览 blocked_previews（本机无法生成预览）：你批准的是未见过的效果，必须知情批准",
              "人工阅读披露后裁决，或在策略中补 transition_preview_waiver 预授权")
    if markers["sufficiency_shorten"]:
        cover("sufficiency_shorten",
              "计划出现充分性缩短兜底（sufficiencyFallback）：缩短成片是委托方可见的决定",
              "人工裁决，或在策略中补 sufficiency_shorten 预授权")
    if node == "G3":
        cover("subject_policy",
              "G3 目标主体确认（身份判定政策）属信任类授权：自动模式必须由输入工单+策略预授权承载",
              "人工确认主体政策后口令裁决本闸，或在策略中补 subject_policy 预授权（附主体定义）")
    warnings = []
    if markers["disclosed_exceedance"]:
        warnings.append("响度超差（disclosed-exceedance）")
    accepted = list(getattr(args, "accepted_warning", None) or [])
    if getattr(args, "accepted_warnings", None):
        try:
            parsed = json.loads(args.accepted_warnings)
            if isinstance(parsed, list):
                warnings.extend(str(item) for item in parsed)
        except json.JSONDecodeError:
            pass
    if warnings:
        def scopes_cover(entry):
            scopes = (entry.get("parameters") or {}).get("scopes") or []
            return all(any(str(scope) in warning for scope in scopes) for warning in warnings)
        cover("warning_acceptance",
              "存在需知情接受的警告：" + "；".join(warnings),
              "人工逐条点名接受，或在策略中补 warning_acceptance 预授权（parameters.scopes 覆盖每条警告关键词）",
              entry_check=scopes_cover)
    if markers["permanent"]:
        emit({"status": "blocked",
              "error": "自动批准永久拒绝（不可预授权）：" + "；".join(markers["permanent"]),
              "autoApprovalBlocked": {"node": node, "permanent": markers["permanent"],
                                      "missingPreAuthorizations": missing,
                                      "resolution": "永久项没有预授权通道——修正输入（换已清权资产/明确授权/移除人工背书断言）或把本项目转人工模式"}}, 2)
    if missing:
        emit({"status": "blocked",
              "error": "自动确认受阻（宁可停不可猜）：" + "；".join(
                  f"[{item['category']}] {item['reason']}" + (f"（{item['note']}）" if item.get("note") else "")
                  for item in missing),
              "autoApprovalBlocked": {"node": node, "permanent": [], "missingPreAuthorizations": missing,
                                      "resolution": "人工裁决后以精确口令关闭本闸（本闸如实记 host-session，后续闸恢复自动），或在策略文件补预授权后重试"}}, 2)
    statement = str(policy["statement"]).strip()
    if used:
        applied = "；".join(
            f"{category}: {next(entry['basis'].strip() for entry in policy['preAuthorizations'] if entry.get('category') == category)}"
            for category in used)
        verbatim = f"{statement}｜适用预授权 → {applied}"
    else:
        verbatim = statement
    return {"approvalToken": f"auto-policy:{node}", "approvalResponse": f"auto-policy:{node}",
            "approvalTokenVerbatim": verbatim, "approvalResponseVerbatim": verbatim,
            "approvalSource": "auto-policy", "autoPolicyRef": state.get("autoPolicyRef"),
            "preAuthorizationsUsed": used}


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
    # v1.35.0 工作台选址硬闸：新项目落点必须正好在 <登记根>/工作台/<projectId>/（env>选址记录>仓库默认），
    # AI 没有临场指路的第四种自由；合同见 references/workspace-root-contract.md。
    try:
        workspace = workspace_gate(destination)
    except ValueError as error:
        emit({"status": "blocked", "error": str(error)}, 2)
    # v1.22.0 输入端选模式：auto 必须带策略文件（当场校验，坏策略不开工）。
    mode = getattr(args, "approval_mode", "human") or "human"
    policy_ref = None
    if mode == "auto":
        if not getattr(args, "auto_policy", None) or not str(args.auto_policy).strip():
            emit({"status": "blocked", "error": "--approval-mode auto 必须携带 --auto-policy（预授权策略文件）——无策略不自动"}, 2)
        try:
            policy_path, _policy = load_policy_file(args.auto_policy, args.project_id)
        except ValueError as error:
            emit({"status": "blocked", "error": f"auto-policy 无效：{error}"}, 2)
        policy_ref = str(policy_path)
    timestamp = now()
    bgm = pack.get("bgm") or {"decision": "unknown", "preference": None, "libraryPending": False, "clearCondition": None}
    bgm = {**bgm, "history": []}
    state = {
        "schemaVersion": "0.1", "projectId": args.project_id, "sourcePackRef": str(source),
        "authorization": args.authorization, "distribution": args.distribution, "bgm": bgm,
        "approvalMode": mode,
        "currentNode": "G1", "status": "in_progress",
        "nodes": {"G0": {"status": "completed", "artifactRefs": [str(source)], "inputRefs": [], "humanReviewPoints": [], "approval": None}, **{node: node_record("in_progress" if node == "G1" else "pending") for node in NODES if node != "G0"}},
        "acceptedWarnings": [], "nextAction": next_action("G1"), "createdAt": timestamp, "updatedAt": timestamp,
    }
    if policy_ref:
        state["autoPolicyRef"] = policy_ref
    # 落账的住址（v1.35.0）：root+source 随 state 永久可审——续工/审计不用猜。
    state["workspaceRoot"] = {"root": str(workspace["root"]), "source": workspace["source"],
                              "workbench": str(workspace["root"] / WORKSPACE_DIR_NAME)}
    write_state(destination, state)
    emit({"status": "created", "state": str(destination), "currentNode": "G1", "approvalMode": mode,
          "workspaceRoot": state["workspaceRoot"], "nextAction": state["nextAction"]})


def command_capability_audit(args: argparse.Namespace) -> None:
    """能力盘点入册（v1.34.0）：只认 capability_audit.py 真产物，手补件冒充拒收
    （台账⑦同款纪律）；重跑盘点则旧块进 capabilityAuditHistory，永不覆盖留痕。"""
    state_path = Path(args.state)
    state = read_state(state_path)
    audit_path = Path(args.audit_file)
    if not audit_path.is_file():
        emit({"status": "blocked", "error": f"盘点文件不在盘上：{audit_path}"}, 2)
    report = json.loads(audit_path.read_text(encoding="utf-8"))
    if report.get("kind") != "capability-audit" or report.get("schemaVersion") != "0.1":
        emit({"status": "blocked", "error": "盘点文件不是 capability-audit v0.1 产物——不许手补件冒充专员产物（台账⑦同款）"}, 2)
    block = {
        "file": str(audit_path), "sha256": sha256_file(audit_path),
        "probedAt": report.get("probedAt"), "profile": report.get("profile", []),
        "summary": report.get("summary") or {},
        "missing": [{"id": item["id"], "label": item.get("labelPlain"), "affects": item.get("affects", [])}
                    for item in report.get("items", []) if item.get("status") == "missing"],
    }
    if state.get("capabilityAudit"):
        state.setdefault("capabilityAuditHistory", []).append(state["capabilityAudit"])
    state["capabilityAudit"] = block
    write_state(state_path, state)
    emit({"status": "recorded", "capabilityAudit": block,
          "nextAction": "把盘点摊上本节点回显（缺口=③区点名）；缺口只影响后段节点时不阻塞开工，缺口节点前必须补齐或人工拍板降级"})


def command_status(args: argparse.Namespace) -> None:
    state = read_state(Path(args.state))
    node = state["currentNode"]
    record = state["nodes"].get(node, {})
    review_gate = record.get("reviewGate")
    bgm = state.get("bgm") or {}
    if bgm.get("libraryPending"):
        bgm = {**bgm, "reminder": "BGM 待找乐：G1 末出检索词卡 → 找乐 → 用户挑曲 → 官方渠道取得整轨并登记 → `bgm-choice` 翻槽；G3 批准前槽必须已清"}
    emit({"status": state["status"], "projectId": state["projectId"], "currentNode": node, "nodeStatus": record.get("status"), "approvalMode": state.get("approvalMode", "human"), "autoPolicyRef": state.get("autoPolicyRef"), "inputRefs": record.get("inputRefs", []), "artifactRefs": record.get("artifactRefs", []), "humanReviewPoints": record.get("humanReviewPoints", []), "reviewGate": review_gate, "reviewGateStatus": "ready" if review_gate else "missing", "acceptedWarnings": state.get("acceptedWarnings", []), "bgm": bgm, "capabilityAudit": state.get("capabilityAudit"), "workspaceRoot": state.get("workspaceRoot"), "nextAction": state["nextAction"]})




def command_bgm_choice(args: argparse.Namespace) -> None:
    """Flip the G0 BGM slot with evidence. Pending never clears by talking; it
    clears by a registered file (provided) or the user's deliberate no-BGM call."""
    state_path = Path(args.state)
    state = read_state(state_path)
    # v1.22.0：auto 模式下翻 BGM 槽=系统受托选曲（挑曲是人耳偏好），必须有预授权在场。
    if str(state.get("approvalMode") or "human") == "auto":
        try:
            policy = load_auto_policy(state_path, state)
        except ValueError as error:
            emit({"status": "blocked", "error": f"auto 模式下 BGM 翻槽被拦：{error}"}, 2)
        if not any(entry.get("category") == "music_delegated_selection" for entry in policy.get("preAuthorizations", [])):
            emit({"status": "blocked", "error": "自动确认模式下 BGM 翻槽=系统受托选曲（挑曲属人耳偏好）：策略需带 music_delegated_selection 预授权，或 set-approval-mode 转人工处理本项目"}, 2)
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
        # R2（Leader 反馈）：登记即冻结被审文件指纹——真人看到的版本从这一刻起被绑定。
        record["reviewGate"]["basisHashes"] = reviewed_file_hashes(state_path, args.review_gate_ref)
    except (ValueError, json.JSONDecodeError, OSError) as error:
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
    # ⑫（banshee-001 台账，2026-10-10 用户拍板甲案）：注入文案随本次必传的 reason 逐字生成，
    # 工具手里拿着真相就不再写死句子——审计读账本看到的就是回炉原因本身。
    g2["humanReviewPoints"] = list(dict.fromkeys(
        g2.get("humanReviewPoints", []) + ["reopen-g2 返工并重批 G2（按回炉原因）：" + args.reason]))
    g3["status"] = "pending"
    clear_review_gate(g3)
    g3["humanReviewPoints"] = []
    g3["approval"] = None
    state["currentNode"] = "G2"
    state["status"] = "in_progress"
    state["nextAction"] = "按本次回炉原因完成返工后，重新申请 G2 批准——原因：" + args.reason
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
    # ⑫（banshee-001 台账，2026-10-10 用户拍板甲案）：注入文案随本次必传的 reason 逐字生成——
    # banshee 那次纯混音参数回炉被写死句子说成"重建语义对齐"，账面失真；真相以后不再靠人事后覆盖。
    g3["humanReviewPoints"] = list(dict.fromkeys(
        g3.get("humanReviewPoints", []) + ["reopen-g3 返工并重批 G3（按回炉原因）：" + args.reason]))
    g4["status"] = "pending"
    clear_review_gate(g4)
    g4["approval"] = None
    g4["inputRefs"] = []
    g4["humanReviewPoints"] = []
    state["currentNode"] = "G3"
    state["status"] = "in_progress"
    state["nextAction"] = "按本次回炉原因完成返工后，重新申请 G3 批准——原因：" + args.reason
    write_state(state_path, state)
    emit({"status": "reopened", "currentNode": "G3", "nextAction": state["nextAction"], "amendment": history[-1]})


def command_set_approval_mode(args: argparse.Namespace) -> None:
    """显式模式切换（v1.22.0）：只此一个入口，必须带理由，切换历史 append-only。
    隐式切换不存在——fail-stop 不切模式，人裁决单闸走口令（该闸记 host-session）。"""
    state_path = Path(args.state)
    state = read_state(state_path)
    current = str(state.get("approvalMode") or "human")
    if args.mode == current:
        emit({"status": "unchanged", "approvalMode": current, "note": "模式未变；切换必须显式带理由，本次未写入"})
    if args.mode == "auto":
        if getattr(args, "auto_policy", None) and str(args.auto_policy).strip():
            try:
                policy_path, _policy = load_policy_file(args.auto_policy, state["projectId"])
            except ValueError as error:
                emit({"status": "blocked", "error": f"auto-policy 无效：{error}"}, 2)
            state["autoPolicyRef"] = str(policy_path)
        try:
            load_auto_policy(state_path, state)
        except ValueError as error:
            emit({"status": "blocked", "error": f"切自动被拦（--auto-policy 缺失或既有策略无效）：{error}"}, 2)
    history = state.setdefault("approvalModeHistory", [])
    history.append({"from": current, "to": args.mode, "reason": args.reason, "at": now()})
    state["approvalMode"] = args.mode
    write_state(state_path, state)
    emit({"status": "recorded", "action": "set-approval-mode", "approvalMode": args.mode, "change": history[-1]})


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
    if fresh_gate != {key: value for key, value in record["reviewGate"].items() if key != "basisHashes"}:
        emit({"status": "blocked",
              "error": "review gate receipt changed since record-review (renderedAt/basisRefs/checklist); re-run record-review before approving"}, 2)
    # R2（Leader 反馈，用户 09-24 裁决）：收据没动但被审文件被同路径换过内容——
    # 真人批准的版本已不存在，旧批准不可复用。approvalRef 是关单时才写的文件，豁免。
    basis_hashes = record["reviewGate"].get("basisHashes")
    if not isinstance(basis_hashes, dict) or not basis_hashes:
        emit({"status": "blocked", "error": "审核门禁快照缺少被审文件指纹（R2 升级前登记的在途门禁）：重渲染审核卡并重新 record-review 后再批准"}, 2)
    try:
        live_hashes = reviewed_file_hashes(state_path, record["reviewGate"]["reviewGateRef"])
    except (ValueError, json.JSONDecodeError, OSError) as error:
        emit({"status": "blocked", "error": f"被审文件在登记审核后缺失或不可读，批准失效：{error}"}, 2)
    changed = sorted(ref for ref, digest in basis_hashes.items() if ref != args.approval_ref and live_hashes.get(ref) != digest)
    if changed:
        emit({"status": "blocked", "error": "被审文件已在登记审核后变更（同路径替换/修改内容=真人所批版本不存在，旧批准不可复用）：" + "、".join(changed) + "；请重渲染审核卡 → 重新 record-review → 重新取得人工确认后再批准"}, 2)
    if node in ("G2", "G3") and (state.get("bgm") or {}).get("libraryPending"):
        emit({"status": "blocked", "error": f"{node} 批准被 BGM 待找乐槽拦住：音乐须在首个消费节点前在场（N9 顺序）。挑曲→官方渠道取得整轨→登记→bgm-choice 翻槽后再批"}, 2)
    # ---- v1.22.0 批准来源分支：human=口令（原逻辑逐字保留）；auto=策略批准（--auto）。
    # 一次批准只有一个来源：--auto 与口令参数同传=拒（防审计混乱）。auto 项目里
    # 人依然可以口令裁决某一闸（fail-stop 的处理通道），该闸如实记 host-session。----
    mode = str(state.get("approvalMode") or "human")
    auto_flag = bool(getattr(args, "auto", False))
    token_given = args.approval_token is not None or args.approval_response is not None
    if auto_flag and token_given:
        emit({"status": "blocked", "error": "--auto 不得与 --approval-token/--approval-response 混用（一次批准只有一个来源：策略自动 或 人工口令）"}, 2)
    if auto_flag and mode != "auto":
        emit({"status": "blocked", "error": "本项目 approvalMode=human：不存在自动批准通道（要切换用 set-approval-mode 并留理由）"}, 2)
    if mode == "auto" and not auto_flag and not token_given:
        emit({"status": "blocked", "error": "自动模式下 approve 二选一：--auto（策略自动批准）或 --approval-token/--approval-response（人工裁决本闸，如实记 host-session）"}, 2)
    if not auto_flag and (args.approval_token is None or args.approval_response is None):
        emit({"status": "blocked", "error": f"人工批准必须携带 --approval-token 与 --approval-response（精确口令：确认 {node}）"}, 2)
    if auto_flag:
        try:
            load_auto_policy(state_path, state)  # fail-fast：策略文件本身无效就别进预检
        except ValueError as error:
            emit({"status": "blocked", "error": f"自动批准被拦：{error}"}, 2)
        approval = {"approvalRef": args.approval_ref, "reviewGateRef": record["reviewGate"]["reviewGateRef"],
                    "approvalToken": f"auto-policy:{node}", "approvalResponse": f"auto-policy:{node}",
                    "approvalTokenVerbatim": "", "approvalResponseVerbatim": "",
                    "normalizedFromVariant": False, "approvedAt": now(),
                    "approvalSource": "auto-policy", "autoPolicyRef": state.get("autoPolicyRef"),
                    "preAuthorizationsUsed": []}
    else:
        try:
            approval_token, approval_response, token_verbatim, response_verbatim, normalized = require_approval_token(
                node, args.approval_token, args.approval_response)
        except ValueError as error:
            emit({"status": "blocked", "error": str(error)}, 2)
        approval = {"approvalRef": args.approval_ref, "reviewGateRef": record["reviewGate"]["reviewGateRef"], "approvalToken": approval_token, "approvalResponse": approval_response,
                    "approvalTokenVerbatim": token_verbatim, "approvalResponseVerbatim": response_verbatim,
                    "normalizedFromVariant": normalized, "approvedAt": now(),
                    # R2 信任边界（见 pipeline-state-contract）：本地阶段确认来源=宿主会话真人回复，
                    # Agent 可代录、不可制造；接 Proxima 后由宿主审核入口提供可信审批事件。
                    "approvalSource": "host-session"}
        if mode == "auto":
            approval["autoModeOverride"] = True  # auto 项目里的人工裁决闸，如实双记
    try:
        require_project_file(state_path, args.approval_ref, "approvalRef")
        require_basis_references(record["reviewGate"], [args.approval_ref])
    except ValueError as error:
        emit({"status": "blocked", "error": str(error)}, 2)
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
        # v1.22.0 人审决策文件形状对账（诚实披露闸，双向都拦）：
        # auto 关单必须带 performed:false + replacedBy auto-policy:（缺文件/冒充人审=拒）；
        # 人工关单不接受 performed:false（免审声明是自动模式专属，人批了却说没人审=矛盾）。
        decision_path = manifest.parent / "human-review-decision.json"
        decision_doc = None
        if decision_path.is_file():
            try:
                decision_doc = json.loads(decision_path.read_text(encoding="utf-8-sig"))
            except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                decision_doc = None
        if approval.get("approvalSource") == "auto-policy":
            if not (isinstance(decision_doc, dict) and decision_doc.get("performed") is False
                    and str(decision_doc.get("replacedBy") or "").startswith("auto-policy:")):
                emit({"status": "blocked", "error": "自动确认 G5 要求 human-review-decision.json 以披露形状在场（performed:false + replacedBy 以 auto-policy: 开头）——缺此文件不得宣称免审，自动模式也不得声称做过人工审"}, 2)
        elif isinstance(decision_doc, dict) and decision_doc.get("performed") is False:
            emit({"status": "blocked", "error": "人工关单不接受 performed:false 免审声明（该形状是自动确认模式专属）：完成人工播放审核后关单，或 set-approval-mode 留痕转自动"}, 2)
    if approval.get("approvalSource") == "auto-policy":
        approval.update(require_auto_approval(state_path, state, node, record, args))
    record["approval"] = approval
    if node == "G5" and approval.get("approvalSource") == "auto-policy":
        record["status"] = "completed_auto_reviewed_with_accepted_warnings" if state["acceptedWarnings"] else "completed_auto_reviewed"
    else:
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


def command_workspace_root(args: argparse.Namespace) -> None:
    """工作台选址（v1.35.0）：读=当前登记根与是否首次待选；写=必须带人的逐字原话。
    选址是机器级事实不是项目动态项：落账一次、之后 init 硬闸按此对账。"""
    if getattr(args, "set", None):
        try:
            record = set_choice(args.set, args.user_words, now())
        except ValueError as error:
            emit({"status": "blocked", "error": str(error)}, 2)
        emit({"status": "recorded", "root": record["root"], "source": "choice",
              "workbench": str(Path(record["root"]) / WORKSPACE_DIR_NAME),
              "userWords": record["userWords"], "choiceFile": str(choice_file()),
              "nextAction": "选址已落账；此后新项目 init 必须落在该根的 工作台/ 之下（越界=罢工点名）。"
                            "回到 G0 开工单九问。"})
        return
    try:
        ws = resolve_workspace_root()
    except ValueError as error:
        emit({"status": "blocked", "error": str(error)}, 2)
    emit({"status": "completed", "root": str(ws["root"]), "source": ws["source"],
          "workbench": str(ws["root"] / WORKSPACE_DIR_NAME),
          "userWords": (ws["record"] or {}).get("userWords"),
          "needsUserChoice": ws["source"] == "default",
          "hint": f"needsUserChoice=true 时先出一张一次性选址小卡（甲=仓库默认 {WORKSPACE_DIR_NAME}/ 推荐；"
                  f"乙=用户逐字给的目录），选完经 workspace-root --set --user-words '<原话>' 落账；"
                  f"机器环境以 {WORKSPACE_HOME_ENV} 注入根视为人已定。"})


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    sub = result.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--project-id", required=True); init.add_argument("--source-pack", required=True); init.add_argument("--state", required=True)
    init.add_argument("--authorization", required=True); init.add_argument("--distribution", required=True)
    init.add_argument("--approval-mode", choices=APPROVAL_MODES, default="human",
                      help="输入端选审批模式（v1.22.0）：human=每节点真人口令（默认）；auto=策略自动确认（必带 --auto-policy）")
    init.add_argument("--auto-policy", help="auto 模式必带：预授权策略 JSON（kind=auto-approval-policy，schemaVersion 0.1）")
    init.set_defaults(func=command_init)
    wroot = sub.add_parser("workspace-root", help="工作台选址：读登记/首次待选；写=人逐字原话落账（v1.35.0）")
    wroot.add_argument("--set", help="新根目录（工作台之父目录；含 工作台 段=⑤嵌套语义拒）")
    wroot.add_argument("--user-words", help="用户选址原话（--set 必带；AI 永不代选）")
    wroot.set_defaults(func=command_workspace_root)
    status = sub.add_parser("status"); status.add_argument("--state", required=True); status.set_defaults(func=command_status)
    record = sub.add_parser("record"); record.add_argument("--state", required=True); record.add_argument("--node", choices=NODES, required=True)
    record.add_argument("--node-status", choices=sorted(STATES), required=True); record.add_argument("--input-ref", action="append"); record.add_argument("--artifact-ref", action="append"); record.add_argument("--review-point", action="append"); record.set_defaults(func=command_record)
    review = sub.add_parser("record-review"); review.add_argument("--state", required=True); review.add_argument("--node", choices=NODES[1:], required=True); review.add_argument("--review-gate-ref", required=True); review.set_defaults(func=command_record_review)
    bgm = sub.add_parser("bgm-choice"); bgm.add_argument("--state", required=True)
    bgm.add_argument("--decision", required=True, choices=("provided", "use_library_later", "no_bgm"))
    bgm.add_argument("--preference"); bgm.add_argument("--evidence"); bgm.add_argument("--note")
    bgm.set_defaults(func=command_bgm_choice)
    approve = sub.add_parser("approve"); approve.add_argument("--state", required=True); approve.add_argument("--node", choices=NODES, required=True); approve.add_argument("--approval-ref", required=True)
    # v1.22.0：口令参数改由代码按模式校验（human 必带；auto 走 --auto；混用即拒）。
    approve.add_argument("--approval-token"); approve.add_argument("--approval-response")
    approve.add_argument("--auto", action="store_true", help="自动确认模式：按策略批准本闸（要求项目 approvalMode=auto；不得与口令参数同传）")
    approve.add_argument("--approved-narration-ref"); approve.add_argument("--fact-citation-ref"); approve.add_argument("--voice-brief-ref"); approve.add_argument("--edit-plan-ref"); approve.add_argument("--timeline-review-ref"); approve.add_argument("--g4-output-mode", choices=("local_direct", "chatcut"), default="local_direct"); approve.add_argument("--local-render-ref"); approve.add_argument("--g4-validation-ref"); approve.add_argument("--chatcut-export-ref"); approve.add_argument("--delivery-manifest-ref"); approve.add_argument("--g5-validation-ref"); approve.add_argument("--accepted-warnings"); approve.add_argument("--accepted-warning", action="append"); approve.set_defaults(func=command_approve)
    audit = sub.add_parser("capability-audit")
    audit.add_argument("--state", required=True); audit.add_argument("--audit-file", required=True)
    audit.set_defaults(func=command_capability_audit)
    reopen = sub.add_parser("reopen"); reopen.add_argument("--state", required=True); reopen.add_argument("--reason", required=True); reopen.add_argument("--rework-ref", required=True); reopen.set_defaults(func=command_reopen)
    reopen_g3 = sub.add_parser("reopen-g3"); reopen_g3.add_argument("--state", required=True); reopen_g3.add_argument("--reason", required=True); reopen_g3.add_argument("--rework-ref", required=True); reopen_g3.set_defaults(func=command_reopen_g3)
    sam = sub.add_parser("set-approval-mode")
    sam.add_argument("--state", required=True); sam.add_argument("--mode", choices=APPROVAL_MODES, required=True)
    sam.add_argument("--reason", required=True, help="切换理由（append-only 历史，禁隐式切换）"); sam.add_argument("--auto-policy")
    sam.set_defaults(func=command_set_approval_mode)
    for command in (init, wroot, status, record, review, bgm, approve, reopen, reopen_g3, sam, audit):
        command.add_argument("--unicode", action="store_true", help="Emit readable Unicode JSON for UTF-8 terminals")
    return result


if __name__ == "__main__":
    args = parser().parse_args()
    if getattr(args, "unicode", False):
        UNICODE_OUTPUT = True
    args.func(args)
