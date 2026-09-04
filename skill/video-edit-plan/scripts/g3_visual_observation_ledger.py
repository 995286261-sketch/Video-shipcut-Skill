#!/usr/bin/env python3
"""Read and append exact-key visual observations without re-analyzing frames."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


KEY_FIELDS = (
    "sourceAssetId", "sourceSha256", "sourceMs", "frameExtractionSpec",
    "analysisPromptVersion", "provider", "model",
)
REQUIRED_FIELDS = KEY_FIELDS + ("recordId", "analysisStatus", "frameRef", "createdAt")
STATUSES = {"completed", "failed", "timeout", "superseded"}


def fail(message: str) -> None:
    raise ValueError(message)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        fail(f"{path.name} must be a JSON object")
    return value


def require_record(record: dict) -> None:
    if not isinstance(record, dict):
        fail("ledger record must be an object")
    for field in REQUIRED_FIELDS:
        value = record.get(field)
        if field == "sourceMs":
            if not isinstance(value, int) or value < 0:
                fail("sourceMs must be a non-negative integer")
        elif not isinstance(value, str) or not value.strip():
            fail(f"ledger record requires {field}")
    if record["analysisStatus"] not in STATUSES:
        fail("analysisStatus must be completed, failed, timeout, or superseded")
    if record["analysisStatus"] == "completed":
        if not isinstance(record.get("observedVisuals"), str) or not record["observedVisuals"].strip():
            fail("completed record requires observedVisuals")
        if not isinstance(record.get("riskFlags", []), list):
            fail("completed record riskFlags must be a list")


def key(record: dict) -> tuple:
    return tuple(record[field] for field in KEY_FIELDS)


def validate_ledger(ledger: dict) -> list[dict]:
    if ledger.get("schemaVersion") != "0.1" or ledger.get("node") != "G3":
        fail("ledger must be a G3 schemaVersion 0.1 artifact")
    records = ledger.get("records")
    if not isinstance(records, list):
        fail("ledger requires a records list")
    ids, keys = set(), set()
    for record in records:
        require_record(record)
        if record["recordId"] in ids:
            fail("ledger recordId values must be unique")
        if key(record) in keys:
            fail("ledger has duplicate exact frame-analysis keys")
        ids.add(record["recordId"])
        keys.add(key(record))
    return records


def write(path: Path, ledger: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", required=True, type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--validate", action="store_true")
    group.add_argument("--lookup", type=Path, help="JSON record/key containing all exact reuse key fields")
    group.add_argument("--append", type=Path, help="JSON observation record to append")
    args = parser.parse_args()
    ledger = load_json(args.ledger)
    records = validate_ledger(ledger)
    if args.validate:
        result = {"status": "completed", "records": len(records)}
    elif args.lookup:
        query = load_json(args.lookup)
        for field in KEY_FIELDS:
            if field not in query:
                fail(f"lookup requires {field}")
        matches = [record for record in records if key(record) == key(query)]
        result = {"status": "completed", "found": bool(matches), "record": matches[0] if matches else None}
    else:
        record = load_json(args.append)
        require_record(record)
        if any(key(existing) == key(record) for existing in records):
            fail("exact frame-analysis key already exists; reuse it instead of re-analyzing")
        if any(existing["recordId"] == record["recordId"] for existing in records):
            fail("recordId already exists")
        ledger["records"].append(record)
        write(args.ledger, ledger)
        result = {"status": "completed", "appendedRecordId": record["recordId"], "records": len(ledger["records"])}
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "invalid", "error": str(error)}, ensure_ascii=True))
        raise SystemExit(2)
