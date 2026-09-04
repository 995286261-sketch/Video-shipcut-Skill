#!/usr/bin/env python3
"""Validate the G3 narration-to-visual semantic beat contract."""

import argparse
import json
from pathlib import Path


CLAIM_TYPES = {"object", "appearance", "state_change", "weapon", "action", "character_reaction", "abstract_conclusion", "editorial_hold"}
STATUSES = {"draft", "review_required", "approved"}


def fail(message: str) -> None:
    raise ValueError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--beats", required=True, type=Path)
    args = parser.parse_args()
    payload = json.loads(args.beats.read_text(encoding="utf-8-sig"))
    if payload.get("schemaVersion") != "0.1" or payload.get("node") != "G3":
        fail("semantic beats must be a G3 schemaVersion 0.1 artifact")
    if payload.get("status") not in STATUSES:
        fail("semantic beats status must be draft, review_required, or approved")
    for field in ("projectId", "narrationDraft", "narrationDecisionRef", "timingBasis"):
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            fail(f"semantic beats requires {field}")
    beats = payload.get("beats")
    if not isinstance(beats, list) or not beats:
        fail("semantic beats requires a non-empty beats list")
    ids, previous_end = set(), 0
    for beat in beats:
        if not isinstance(beat, dict):
            fail("each semantic beat must be an object")
        beat_id = beat.get("beatId")
        if not isinstance(beat_id, str) or not beat_id or beat_id in ids:
            fail("semantic beatId must be unique and non-empty")
        ids.add(beat_id)
        start, end = beat.get("outputStartMs"), beat.get("outputEndMs")
        if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
            fail(f"semantic beat {beat_id} has invalid output time range")
        if start < previous_end:
            fail(f"semantic beat {beat_id} overlaps the preceding beat")
        previous_end = end
        if not isinstance(beat.get("narrationText"), str) or not beat["narrationText"].strip():
            fail(f"semantic beat {beat_id} requires narrationText")
        claim = beat.get("claim")
        if not isinstance(claim, dict) or claim.get("type") not in CLAIM_TYPES:
            fail(f"semantic beat {beat_id} requires a valid claim type")
        evidence = claim.get("minimumVisibleEvidence")
        if not isinstance(evidence, list) or not evidence or not all(isinstance(item, str) and item.strip() for item in evidence):
            fail(f"semantic beat {beat_id} requires minimumVisibleEvidence")
        alternatives = beat.get("allowedVisualAlternatives", [])
        if not isinstance(alternatives, list) or not all(isinstance(item, str) and item.strip() for item in alternatives):
            fail(f"semantic beat {beat_id} allowedVisualAlternatives must be a string list")
    print(json.dumps({"status": "completed", "beats": len(beats), "timingBasis": payload["timingBasis"]}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "invalid", "error": str(error)}, ensure_ascii=True))
        raise SystemExit(2)
