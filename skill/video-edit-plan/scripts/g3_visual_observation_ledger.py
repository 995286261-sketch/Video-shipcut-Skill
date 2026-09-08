#!/usr/bin/env python3
"""Maintain an append-only G3 visual observation ledger with explicit supersede transitions."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path


KEY_FIELDS = (
    "sourceAssetId", "sourceSha256", "sourceMs", "frameExtractionSpec",
    "analysisPromptVersion", "provider", "model",
)
REQUIRED_FIELDS = KEY_FIELDS + ("recordId", "analysisStatus", "frameRef", "createdAt")
STATUSES = {"completed", "failed", "timeout", "superseded"}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def is_active(record: dict) -> bool:
    return record.get("analysisStatus") != "superseded"


def validate_supersede_chain(records: list[dict]) -> None:
    by_id = {record["recordId"]: record for record in records}
    for record in records:
        superseded_by = record.get("supersededBy")
        if record["analysisStatus"] == "superseded":
            if not isinstance(superseded_by, str) or superseded_by not in by_id:
                fail(f"superseded record {record['recordId']} requires an existing supersededBy record")
            if by_id[superseded_by].get("supersedesRecordId") != record["recordId"]:
                fail(f"superseded record {record['recordId']} requires reciprocal supersedesRecordId")
        elif superseded_by is not None:
            fail(f"active record {record['recordId']} cannot have supersededBy")
    for record in records:
        seen = {record["recordId"]}
        current = record
        while current["analysisStatus"] == "superseded":
            current = by_id[current["supersededBy"]]
            if current["recordId"] in seen:
                fail(f"supersede chain for {record['recordId']} contains a cycle")
            seen.add(current["recordId"])


def validate_ledger(ledger: dict) -> list[dict]:
    if ledger.get("schemaVersion") != "0.1" or ledger.get("node") != "G3":
        fail("ledger must be a G3 schemaVersion 0.1 artifact")
    records = ledger.get("records")
    if not isinstance(records, list):
        fail("ledger requires a records list")
    ids, active_keys = set(), set()
    for record in records:
        require_record(record)
        if record["recordId"] in ids:
            fail("ledger recordId values must be unique")
        supersedes = record.get("supersedesRecordId")
        if supersedes is not None and (not isinstance(supersedes, str) or not supersedes.strip()):
            fail(f"record {record['recordId']} supersedesRecordId must be a non-empty string")
        if supersedes is not None:
            if supersedes not in {item["recordId"] for item in records}:
                fail(f"record {record['recordId']} supersedes unknown record {supersedes}")
            if not isinstance(record.get("correctionSource"), str) or not record["correctionSource"].strip():
                fail(f"correction record {record['recordId']} requires correctionSource")
        if is_active(record):
            if key(record) in active_keys:
                fail("ledger has duplicate active frame-analysis keys; supersede the existing record instead")
            active_keys.add(key(record))
        ids.add(record["recordId"])
    if any(record["analysisStatus"] == "superseded" or "supersedesRecordId" in record or "supersededBy" in record for record in records):
        validate_supersede_chain(records)
    return records


def write(path: Path, ledger: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def lineage(records: list[dict], record: dict) -> list[dict]:
    by_id = {item["recordId"]: item for item in records}
    oldest = record
    while oldest.get("supersedesRecordId"):
        oldest = by_id[oldest["supersedesRecordId"]]
    chain = [oldest]
    while chain[-1].get("supersededBy") and chain[-1]["supersededBy"] in by_id:
        chain.append(by_id[chain[-1]["supersededBy"]])
    return chain


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", required=True, type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--validate", action="store_true")
    group.add_argument("--lookup", type=Path, help="JSON record/key containing all exact reuse key fields")
    parser.add_argument("--history", action="store_true", help="with --lookup, return the full correction lineage")
    group.add_argument("--append", type=Path, help="JSON observation record to append")
    group.add_argument("--supersede", type=Path, help="JSON correction payload containing supersedesRecordId and newRecord")
    args = parser.parse_args()
    ledger = load_json(args.ledger)
    records = validate_ledger(ledger)
    if args.history and not args.lookup:
        fail("--history requires --lookup")
    if args.validate:
        result = {"status": "completed", "records": len(records)}
    elif args.lookup:
        query = load_json(args.lookup)
        for field in KEY_FIELDS:
            if field not in query:
                fail(f"lookup requires {field}")
        candidates = [record for record in records if key(record) == key(query)]
        if args.history:
            result = {"status": "completed", "found": bool(candidates), "history": lineage(records, candidates[0]) if candidates else []}
        else:
            active = next((record for record in candidates if is_active(record)), None)
            result = {"status": "completed", "found": active is not None, "record": active}
    elif args.supersede:
        payload = load_json(args.supersede)
        superseded_id = payload.get("supersedesRecordId")
        replacement = payload.get("newRecord")
        if not isinstance(superseded_id, str) or not isinstance(replacement, dict):
            fail("supersede payload requires supersedesRecordId and newRecord")
        if not isinstance(replacement.get("correctionSource"), str) or not replacement["correctionSource"].strip():
            fail("supersede requires correctionSource in newRecord")
        existing = next((record for record in records if record["recordId"] == superseded_id), None)
        if existing is None or not is_active(existing):
            fail(f"supersede target {superseded_id} is not an active record")
        require_record(replacement)
        if any(record["recordId"] == replacement["recordId"] for record in records):
            fail("recordId already exists")
        if key(replacement) != key(existing):
            fail("superseding record must preserve the superseded record's exact reuse key")
        replacement = {**replacement, "supersedesRecordId": superseded_id}
        replacement_id = replacement["recordId"]
        existing["analysisStatus"] = "superseded"
        existing["supersededBy"] = replacement_id
        existing["supersededAt"] = now()
        ledger["records"].append(replacement)
        validate_ledger(ledger)
        write(args.ledger, ledger)
        result = {"status": "completed", "supersededRecordId": superseded_id, "replacementRecordId": replacement_id, "records": len(ledger["records"])}
    else:
        record = load_json(args.append)
        require_record(record)
        if any(is_active(existing) and key(existing) == key(record) for existing in records):
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
