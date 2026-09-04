"""Canonical active-project layout helpers shared by P0-C runtime scripts."""
from pathlib import Path

G4_DIRECTORY = "G4-剪辑与渲染"
G5_DIRECTORY = "G5-交付包"
CHATCUT_DIRECTORY = "ChatCut-导出"


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
