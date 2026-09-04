#!/usr/bin/env python3
"""Create and validate the input-only media material pack contract."""

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path


REQUIRED = ("01_需求说明.md", "02_原始素材", "03_事实依据", "04_授权说明.md", "05_风格参考", "06_品牌资产", "07_授权音频")
SOURCE_DIR = "02_原始素材"
AUDIO_DIR = "07_授权音频"
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
REQUIREMENT_FIELDS = ("想讲什么", "给谁看", "目标时长", "输出", "希望的感觉", "不能说什么")


class PackError(RuntimeError):
    pass


def emit(value: dict, unicode_output: bool = False) -> None:
    # ASCII is the default so legacy Windows terminals cannot garble status JSON.
    print(json.dumps(value, ensure_ascii=not unicode_output, indent=2))


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest().upper()


def asset_id(kind: str, relative_path: Path) -> str:
    readable = re.sub(r"[^a-z0-9]+", "-", relative_path.with_suffix("").as_posix().lower()).strip("-")
    path_hash = hashlib.sha256(relative_path.as_posix().encode("utf-8")).hexdigest()[:8]
    return f"{kind}-{(readable or 'asset')[:48]}-{path_hash}"


def files_under(pack: Path, entry: str) -> list[Path]:
    root = pack / entry
    return sorted(path for path in root.rglob("*") if path.is_file() and path.name != ".gitkeep")


def requirement_field_has_value(text: str, field: str) -> bool:
    lines = text.splitlines()
    field_pattern = re.compile(rf"^\s*{re.escape(field)}\s*[：:]\s*(.*)$")
    any_field_pattern = re.compile(rf"^\s*(?:{'|'.join(map(re.escape, REQUIREMENT_FIELDS))})\s*[：:]")
    for index, line in enumerate(lines):
        match = field_pattern.match(line)
        if not match:
            continue
        if match.group(1).strip():
            return True
        for following in lines[index + 1:]:
            if any_field_pattern.match(following):
                break
            candidate = following.strip().lstrip("-*").strip()
            if candidate and not candidate.startswith("#"):
                return True
    return False


def authorization_has_entry(text: str) -> bool:
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4 or cells[0] in {"", "文件名"}:
            continue
        if all(re.fullmatch(r"-+", cell) for cell in cells if cell):
            continue
        return True
    return False


def bgm_decision(text: str) -> str | None:
    """Read the explicit, user-facing G0 BGM decision from the requirement file."""
    match = re.search(r"^\s*BGM decision\s*[：:]\s*(provided|use_library_later|no_bgm)\s*$", text, re.IGNORECASE | re.MULTILINE)
    return match.group(1).lower() if match else None


def required_state(pack: Path) -> tuple[list[str], list[str], list[str]]:
    missing = [entry for entry in REQUIRED if not (pack / entry).exists()]
    empty = []
    incomplete = []
    requirements = pack / "01_需求说明.md"
    if requirements.is_file():
        text = requirements.read_text(encoding="utf-8-sig")
        missing_fields = [field for field in REQUIREMENT_FIELDS if not requirement_field_has_value(text, field)]
        if missing_fields:
            empty.append("01_需求说明.md")
            incomplete.extend(f"01_需求说明.md:{field}" for field in missing_fields)
        decision = bgm_decision(text)
        if not decision:
            empty.append("01_需求说明.md")
            incomplete.append("01_需求说明.md:BGM decision (provided / use_library_later / no_bgm)")
        elif decision == "provided" and not files_under(pack, AUDIO_DIR):
            empty.append(AUDIO_DIR)
            incomplete.append("07_授权音频: BGM decision is provided but no audio file is present")
    authorization = pack / "04_授权说明.md"
    if authorization.is_file() and not authorization_has_entry(authorization.read_text(encoding="utf-8-sig")):
        empty.append("04_授权说明.md")
        incomplete.append("04_授权说明.md:缺少真实文件名或待确认记录")
    if not files_under(pack, SOURCE_DIR):
        empty.append(SOURCE_DIR)
    return missing, empty, incomplete


def validate_manifest(pack: Path, manifest: dict) -> list[dict]:
    failures = []
    known_ids = set()
    for group in ("sourceAssets", "audioAssets"):
        for asset in manifest.get(group, []):
            current_id = asset.get("assetId")
            if not current_id or current_id in known_ids:
                failures.append({"assetId": current_id, "type": "missing_or_duplicate_asset_id"})
            known_ids.add(current_id)
            path = (pack / asset.get("relativePath", "")).resolve()
            if pack.resolve() not in path.parents or not path.is_file():
                failures.append({"assetId": asset.get("assetId"), "type": "missing_or_escaping_path"})
            elif asset.get("sha256") and digest(path) != asset["sha256"].upper():
                failures.append({"assetId": asset.get("assetId"), "type": "sha256_mismatch"})
    return failures


def init_pack(destination: Path) -> dict:
    template = Path(__file__).resolve().parents[1] / "assets" / "material-pack-template"
    if destination.exists():
        raise PackError(f"Destination already exists: {destination}")
    shutil.copytree(template, destination)
    return {"status": "created", "pack": str(destination.resolve()), "finishedAt": now()}


def register(pack: Path) -> dict:
    pack = pack.resolve()
    missing, empty, incomplete = required_state(pack)
    if missing or empty:
        return {"status": "incomplete", "pack": str(pack), "missingEntries": missing, "emptyRequiredEntries": empty, "incompleteRequiredEntries": incomplete, "finishedAt": now()}

    manifest_path = pack / "material-pack.json"
    try:
        existing = json.loads(manifest_path.read_text(encoding="utf-8-sig")) if manifest_path.is_file() else {}
    except json.JSONDecodeError as error:
        raise PackError(f"Invalid material-pack.json: {error}") from error
    source_files = files_under(pack, SOURCE_DIR)
    audio_files = [path for path in files_under(pack, AUDIO_DIR) if path.suffix.lower() in AUDIO_EXTENSIONS]
    sources = [{"assetId": asset_id("source", path.relative_to(pack)), "relativePath": path.relative_to(pack).as_posix(), "sourceKind": "local-file", "sha256": digest(path), "byteSize": path.stat().st_size, "fileExtension": path.suffix.lower()} for path in source_files]
    audio = [{"assetId": asset_id("audio", path.relative_to(pack)), "relativePath": path.relative_to(pack).as_posix(), "sha256": digest(path), "byteSize": path.stat().st_size, "fileExtension": path.suffix.lower()} for path in audio_files]
    manifest = {**existing, "schemaVersion": "0.1", "materialPackId": existing.get("materialPackId", pack.name), "sourceAssets": sources, "audioAssets": audio, "packStatus": "complete", "registeredAt": now()}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"status": "completed", "pack": str(pack), "manifest": str(manifest_path), "sourceAssetCount": len(sources), "audioAssetCount": len(audio), "finishedAt": now()}


def validate(pack: Path) -> dict:
    pack = pack.resolve()
    missing, empty, incomplete = required_state(pack)
    manifest_path = pack / "material-pack.json"
    failures = []
    if manifest_path.is_file():
        try:
            failures = validate_manifest(pack, json.loads(manifest_path.read_text(encoding="utf-8-sig")))
        except json.JSONDecodeError as error:
            failures = [{"type": "invalid_manifest_json", "detail": str(error)}]
    else:
        missing.append("material-pack.json")
    complete = not missing and not empty and not failures
    return {"status": "complete" if complete else "incomplete", "pack": str(pack), "missingEntries": missing, "emptyRequiredEntries": empty, "incompleteRequiredEntries": incomplete, "manifestFailures": failures, "optionalEntries": [entry for entry in ("05_风格参考", "06_品牌资产", "07_授权音频") if not files_under(pack, entry)], "finishedAt": now()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Material pack intake")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "register", "validate"):
        command = commands.add_parser(name)
        command.add_argument("--pack", required=True, type=Path)
        command.add_argument("--unicode", action="store_true", help="Emit readable Unicode JSON for UTF-8 terminals")
    args = parser.parse_args()
    try:
        result = init_pack(args.pack) if args.command == "init" else register(args.pack) if args.command == "register" else validate(args.pack)
        emit(result, args.unicode)
        return 0 if result["status"] in {"created", "completed", "complete"} else 2
    except PackError as error:
        emit({"status": "failed", "error": str(error), "finishedAt": now()})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
