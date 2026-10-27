"""Canonical active-project layout helpers shared by P0-C runtime scripts."""
from __future__ import annotations

import json
import os
from pathlib import Path

G4_DIRECTORY = "G4-剪辑与渲染"
G5_DIRECTORY = "G5-交付包"
CHATCUT_DIRECTORY = "ChatCut-导出"

# ---- 工作台选址合同（v1.35.0）：落点零临场——见 references/workspace-root-contract.md ----
WORKSPACE_DIR_NAME = "工作台"
CHOICE_FILENAME = "工作台选址.json"
WORKSPACE_HOME_ENV = "P0C_WORKSPACE_HOME"
REPO_ROOT = Path(__file__).resolve().parents[3]


def choice_file() -> Path:
    return REPO_ROOT / CHOICE_FILENAME


def read_choice() -> dict | None:
    """选址记录只认人的逐字原话件；半形/歪形如实报错，不静默降级。"""
    path = choice_file()
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if (data.get("kind") != "workspace-root-choice" or not str(data.get("root") or "")
            or not str(data.get("userWords") or "").strip()):
        raise ValueError(
            "工作台选址记录形制不对（kind/root/userWords 缺项）——选址必须来自人的逐字原话；"
            f"删除坏记录 {path} 后经人重新选址")
    return data


def resolve_workspace_root() -> dict:
    """规范根解析唯一正道：环境变量 > 人的选址记录 > 仓库默认。"""
    env = str(os.environ.get(WORKSPACE_HOME_ENV) or "").strip()
    if env:
        return {"root": Path(env).expanduser().resolve(), "source": "env", "record": None}
    choice = read_choice()
    if choice is not None:
        return {"root": Path(choice["root"]).resolve(), "source": "choice", "record": choice}
    return {"root": REPO_ROOT, "source": "default", "record": None}


def workspace_gate(state_path: Path) -> dict:
    """新工 init 落点硬闸：项目必须正好在 <登记根>/工作台/<projectId>/ 一层下。
    三种合法住址：env 根、选址记录根、仓库默认根——AI 没有第四种自由。"""
    ws = resolve_workspace_root()
    workbench = ws["root"] / WORKSPACE_DIR_NAME
    project_dir = state_path.resolve().parent
    if project_dir.parent != workbench:
        raise ValueError(
            f"新项目落点不符合工作台选址合同：必须位于 <登记根>/{WORKSPACE_DIR_NAME}/<projectId>/"
            f"（当前登记根 {ws['root']}，出处 {ws['source']}；实收 {project_dir}）。"
            f"换住址须由人逐字选址（pipeline_state.py workspace-root --set <根> --user-words '<原话>'），"
            f"或机器环境以 {WORKSPACE_HOME_ENV} 注入根。")
    return ws


def set_choice(root_str: str, user_words: str, chosen_at: str) -> dict:
    """选址落账：无逐字原话=拒（AI 永不代选，批准口令同纪律）；根含"工作台"段=⑤嵌套语义拒。"""
    if not str(user_words or "").strip():
        raise ValueError("选址必须带用户逐字原话（--user-words）——选址是人的决定，AI 永不代选")
    candidate = Path(str(root_str).strip()).expanduser()
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    candidate = candidate.resolve()
    if WORKSPACE_DIR_NAME in candidate.parts:
        raise ValueError(
            f"选址根不得已含“{WORKSPACE_DIR_NAME}”段：工作台目录由合同自动拼接，"
            "传进来会拼出嵌套怪物（⑤语义闸同款）——请传工作台的父目录")
    record = {"schemaVersion": "0.1", "kind": "workspace-root-choice",
              "root": str(candidate), "chosenAt": chosen_at,
              "source": "user-card", "userWords": str(user_words).strip()}
    choice_file().write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


def project_root(state_path: Path) -> Path:
    return state_path.resolve().parent


def require_project_file(state_path: Path, reference: str, label: str) -> Path:
    candidate = Path(reference).resolve()
    root = project_root(state_path)
    if not candidate.is_file() or root not in candidate.parents:
        raise ValueError(f"{label} must be an existing file under {root}")
    return candidate


def require_g4_file(state_path: Path, reference: str, label: str) -> Path:
    candidate = require_project_file(state_path, reference, label)
    if project_root(state_path) / G4_DIRECTORY not in candidate.parents:
        raise ValueError(f"{label} must be under the active G4 directory")
    return candidate


def require_g5_file(state_path: Path, reference: str, label: str) -> Path:
    candidate = require_project_file(state_path, reference, label)
    if project_root(state_path) / G5_DIRECTORY not in candidate.parents:
        raise ValueError(f"{label} must be under the active G5 directory")
    return candidate
