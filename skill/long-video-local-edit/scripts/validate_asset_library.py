#!/usr/bin/env python3
"""Validate local, licensed entries in the bundled media asset library."""

import argparse
import hashlib
import json
from pathlib import Path


LICENSE_STATES = {"company-owned", "user-authorized", "redistributable"}
REQUIRED_FIELDS = {"assetId", "type", "relativePath", "sha256", "license", "allowedUse"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def validate(manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if manifest.get("schemaVersion") != "0.1":
        errors.append("schemaVersion must be 0.1")
    if not manifest.get("libraryId"):
        errors.append("libraryId is required")
    root = (manifest_path.parent / manifest.get("assetRoot", "media")).resolve()
    asset_ids: set[str] = set()
    for index, asset in enumerate(manifest.get("assets", [])):
        prefix = f"assets[{index}]"
        missing = REQUIRED_FIELDS - asset.keys()
        if missing:
            errors.append(f"{prefix} missing: {', '.join(sorted(missing))}")
            continue
        if asset["assetId"] in asset_ids:
            errors.append(f"duplicate assetId: {asset['assetId']}")
        asset_ids.add(asset["assetId"])
        if asset["license"] not in LICENSE_STATES:
            errors.append(f"{prefix} has unsupported license state: {asset['license']}")
        relative_path = Path(asset["relativePath"])
        if relative_path.is_absolute() or ".." in relative_path.parts:
            errors.append(f"{prefix} relativePath must stay inside assetRoot")
            continue
        path = (root / relative_path).resolve()
        if not path.is_file():
            errors.append(f"{prefix} file missing: {asset['relativePath']}")
        elif sha256(path) != asset["sha256"].upper():
            errors.append(f"{prefix} sha256 mismatch: {asset['assetId']}")
    return {"status": "pass" if not errors else "fail", "assetCount": len(manifest.get("assets", [])), "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a local media asset library")
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    result = validate(args.manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
