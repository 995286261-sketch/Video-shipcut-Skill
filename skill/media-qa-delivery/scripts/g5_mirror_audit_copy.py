#!/usr/bin/env python3
"""Mirror a validated G5 bundle into the canonical workspace audit directory."""
import argparse
import json
import shutil
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-bundle", required=True, type=Path)
    parser.add_argument("--audit-root", required=True, type=Path)
    args = parser.parse_args()

    source = args.source_bundle.resolve()
    audit_root = args.audit_root.resolve()
    if not source.is_dir() or not (source / "delivery-manifest.json").is_file():
        raise ValueError("source bundle must contain delivery-manifest.json")
    if source == audit_root or source in audit_root.parents or audit_root in source.parents:
        raise ValueError("source bundle and audit root must not contain each other")

    destination = audit_root / source.name
    audit_root.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)
    print(json.dumps({"status": "mirrored", "source": str(source), "auditCopy": str(destination)}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=True))
        raise SystemExit(2)
