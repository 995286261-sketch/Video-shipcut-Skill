#!/usr/bin/env python3
"""Deterministic G1 gate, contract validation, and confirmed brief writer."""

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path


PROJECT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
TITLE_TYPES = {"editorial_expression", "factual_claim", "mixed"}
CLAIM_STATUSES = {"supported", "pending"}
BGM_DECISIONS = {"provided", "use_library_later", "no_bgm"}
DIRECTION_SOURCES = {"agent_recommendation", "custom"}


def g0_audio_assets(pack):
    """Return registered G0 audio facts so G1 can inherit, rather than re-ask."""
    manifest_path = Path(pack) / "material-pack.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    return [{"assetId": item.get("assetId"), "relativePath": item.get("relativePath"), "sha256": item.get("sha256")} for item in manifest.get("audioAssets", []) if isinstance(item, dict)]


def emit(value):
    # Keep CLI JSON readable by any Windows code page; consumers decode escapes as Unicode.
    print(json.dumps(value, ensure_ascii=True, indent=2))


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"无法读取 JSON 输入：{error}") from error


def pack_gate(pack):
    script = Path(__file__).resolve().parents[2] / "material-pack-intake" / "scripts" / "material_pack.py"
    result = subprocess.run(
        [sys.executable, str(script), "validate", "--pack", str(pack)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"status": "blocked", "blockers": [{"type": "upstream_validation_unreadable", "detail": result.stderr.strip() or result.stdout.strip()}]}
    if report.get("status") == "complete":
        return {"status": "complete", "pack": str(Path(pack).resolve()), "upstreamReport": report}
    blockers = []
    for key in ("missingEntries", "emptyRequiredEntries", "incompleteRequiredEntries", "manifestFailures"):
        for item in report.get(key, []):
            blockers.append({"type": key, "detail": item})
    return {"status": "blocked", "pack": str(Path(pack).resolve()), "blockers": blockers, "upstreamReport": report}


def evidence_is_valid(pack, item):
    path_text = item.get("path") if isinstance(item, dict) else None
    locator = item.get("locator") if isinstance(item, dict) else None
    if not isinstance(path_text, str) or not isinstance(locator, str) or not locator.strip():
        return False
    relative = Path(path_text)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts or relative.parts[0] != "03_事实依据":
        return False
    target = (pack / relative).resolve()
    return pack.resolve() in target.parents and target.is_file()


def validate_direction(pack, data):
    errors = []
    if not isinstance(data, dict):
        return [{"field": "input", "rule": "根节点必须为对象"}]
    project_id = data.get("projectId")
    if not isinstance(project_id, str) or not PROJECT_ID.fullmatch(project_id):
        errors.append({"field": "projectId", "rule": "必须匹配 [A-Za-z0-9][A-Za-z0-9._-]{0,63}"})
    if not isinstance(data.get("title"), str) or not data["title"].strip():
        errors.append({"field": "title", "rule": "必须提供标题"})
    if data.get("titleExpressionType") not in TITLE_TYPES:
        errors.append({"field": "titleExpressionType", "rule": "必须为 editorial_expression、factual_claim 或 mixed"})
    for field in ("coreQuestion", "audience", "coreViewpoint"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            errors.append({"field": field, "rule": "G1 简报必填，且必须为非空文本"})
    preferences = data.get("outputPreferences")
    if not isinstance(preferences, dict):
        errors.append({"field": "outputPreferences", "rule": "G1 简报必填，且必须为对象"})
    else:
        if not isinstance(preferences.get("aspectRatio"), str) or not preferences["aspectRatio"].strip():
            errors.append({"field": "outputPreferences.aspectRatio", "rule": "必须为非空文本"})
        duration = preferences.get("targetDurationSec")
        is_duration = isinstance(duration, (int, float)) and not isinstance(duration, bool) and duration > 0
        is_range = isinstance(duration, list) and len(duration) == 2 and all(isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 for value in duration) and duration[0] <= duration[1]
        if not (is_duration or is_range):
            errors.append({"field": "outputPreferences.targetDurationSec", "rule": "必须为正秒数，或两个递增正秒数的数组"})
        if not isinstance(preferences.get("usagePurpose"), str) or not preferences["usagePurpose"].strip():
            errors.append({"field": "outputPreferences.usagePurpose", "rule": "必须明确成片用途"})
    if data.get("bgmDecision") not in BGM_DECISIONS:
        errors.append({"field": "bgmDecision", "rule": "必须为 provided、use_library_later 或 no_bgm"})
    elif data.get("bgmDecision") == "provided" and not g0_audio_assets(pack):
        errors.append({"field": "bgmDecision", "rule": "G0 没有已登记音频；请在 G0 补充 BGM 后再选择 provided"})
    direction_choice = data.get("directionChoice")
    if not isinstance(direction_choice, dict) or not isinstance(direction_choice.get("id"), str) or not direction_choice["id"].strip() or not isinstance(direction_choice.get("label"), str) or not direction_choice["label"].strip() or direction_choice.get("source") not in DIRECTION_SOURCES:
        errors.append({"field": "directionChoice", "rule": "必须记录方向卡 id、label 及 agent_recommendation 或 custom 来源"})
    for field in ("styleRules", "expressionBoundaries"):
        if field not in data:
            errors.append({"field": field, "rule": "G1 简报必填；无额外规则时也必须显式传入 []"})
            continue
        value = data[field]
        if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
            errors.append({"field": field, "rule": "必须为非空文本组成的数组"})
    claims = data.get("claims", [])
    if not isinstance(claims, list):
        errors.append({"field": "claims", "rule": "必须为数组"})
        claims = []
    seen = set()
    for index, claim in enumerate(claims):
        prefix = f"claims[{index}]"
        if not isinstance(claim, dict):
            errors.append({"field": prefix, "rule": "必须为对象"})
            continue
        claim_id = claim.get("claimId")
        if not isinstance(claim_id, str) or not claim_id.strip() or claim_id in seen:
            errors.append({"field": f"{prefix}.claimId", "rule": "必须唯一且非空"})
        seen.add(claim_id)
        if not isinstance(claim.get("text"), str) or not claim["text"].strip():
            errors.append({"field": f"{prefix}.text", "rule": "必须提供事实主张文本"})
        status = claim.get("status")
        if status not in CLAIM_STATUSES:
            errors.append({"field": f"{prefix}.status", "rule": "必须为 supported 或 pending"})
        refs = claim.get("evidenceRefs", [])
        if not isinstance(refs, list):
            errors.append({"field": f"{prefix}.evidenceRefs", "rule": "必须为数组"})
            refs = []
        elif any(not isinstance(ref, dict) or not isinstance(ref.get("path"), str) or not isinstance(ref.get("locator"), str) for ref in refs):
            errors.append({"field": f"{prefix}.evidenceRefs", "rule": "每条证据必须包含 path 和 locator 文本"})
        if status == "supported":
            if not refs or not all(evidence_is_valid(pack, ref) for ref in refs):
                errors.append({"field": f"{prefix}.evidenceRefs", "rule": "supported 主张必须引用素材包 03_事实依据/ 中存在的文件并提供定位信息"})
    return errors


def load_and_validate(pack, input_path):
    gate = pack_gate(pack)
    if gate["status"] != "complete":
        return gate, None, []
    try:
        data = read_json(input_path)
    except ValueError as error:
        return {"status": "invalid"}, None, [{"field": "input", "rule": str(error)}]
    return gate, data, validate_direction(Path(pack).resolve(), data)


def markdown(data, pack):
    lines = [
        "# G1 创作方向简报", "", f"项目 ID：`{data['projectId']}`  ", "状态：已由用户明确确认", "",
        "## 核心问题", "", data.get("coreQuestion", "未填写"), "", "## 目标观众", "", data.get("audience", "未填写"),
        "", "## 标题", "", f"**{data['title']}**", "", f"标题表达类型：`{data['titleExpressionType']}`", "",
        "## 核心观点", "", data.get("coreViewpoint", "未填写"), "", "## 输出偏好", "",
    ]
    for key, value in data.get("outputPreferences", {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## 方向与音频决策", "", f"- 方向卡：{data.get('directionChoice', {}).get('label', '未填写')} ({data.get('directionChoice', {}).get('source', '未填写')})", f"- BGM：{data.get('bgmDecision', '未填写')}"])
    for asset in g0_audio_assets(pack):
        lines.append(f"- 已登记音频：{asset.get('relativePath')} ({asset.get('assetId')})")
    lines.extend(["", "## 风格规则", ""])
    lines.extend(f"- {item}" for item in data.get("styleRules", []))
    lines.extend(["", "## 表达边界", ""])
    lines.extend(f"- {item}" for item in data.get("expressionBoundaries", []))
    lines.extend(["", "## 事实主张与证据引用", "", "| Claim ID | 事实主张 | 状态 | 证据路径 | 定位信息 |", "| --- | --- | --- | --- | --- |"])
    for claim in data.get("claims", []):
        refs = claim.get("evidenceRefs", [])
        if refs:
            for ref in refs:
                lines.append(f"| {claim['claimId']} | {claim['text']} | {claim['status']} | {ref['path']} | {ref['locator']} |")
        else:
            lines.append(f"| {claim['claimId']} | {claim['text']} | pending（待补事实） | - | - |")
    return "\n".join(lines) + "\n"


def target_directory(workspace, project_id, on_conflict):
    base = Path(workspace).resolve() / "创作方向" / project_id
    if not base.exists() or on_conflict == "stop":
        return base
    version = 2
    while (base.parent / f"{project_id}-v{version}").exists():
        version += 1
    return base.parent / f"{project_id}-v{version}"


def main():
    parser = argparse.ArgumentParser(description="G1 创作方向门禁与简报写入")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("check-pack", "validate", "write"):
        command = commands.add_parser(name)
        command.add_argument("--pack", required=True, type=Path)
        if name != "check-pack":
            command.add_argument("--input", required=True, type=Path)
        if name == "write":
            command.add_argument("--workspace", required=True, type=Path)
            command.add_argument("--confirmed", action="store_true")
            command.add_argument("--on-conflict", choices=("stop", "version"), default="stop")
    args = parser.parse_args()
    if args.command == "check-pack":
        output = pack_gate(args.pack)
        emit({**output, "finishedAt": now()})
        return 0 if output["status"] == "complete" else 2
    gate, data, errors = load_and_validate(args.pack, args.input)
    if gate["status"] != "complete":
        emit({**gate, "finishedAt": now()})
        return 2
    if errors:
        emit({"status": "invalid", "errors": errors, "finishedAt": now()})
        return 2
    if args.command == "validate":
        emit({"status": "valid", "projectId": data["projectId"], "finishedAt": now()})
        return 0
    if not args.confirmed:
        emit({"status": "blocked", "blockers": [{"type": "missing_explicit_confirmation", "detail": "未传入 --confirmed，禁止写入方向简报"}], "finishedAt": now()})
        return 2
    destination = target_directory(args.workspace, data["projectId"], args.on_conflict)
    if destination.exists() and args.on_conflict == "stop":
        emit({"status": "blocked", "blockers": [{"type": "project_id_conflict", "detail": str(destination)}], "finishedAt": now()})
        return 2
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "G1-方向简报.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (destination / "G1-方向简报.md").write_text(markdown(data, args.pack), encoding="utf-8")
    emit({"status": "written", "projectId": destination.name, "output": str(destination), "finishedAt": now()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
