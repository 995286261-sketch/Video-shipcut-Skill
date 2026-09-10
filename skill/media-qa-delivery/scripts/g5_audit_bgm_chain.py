#!/usr/bin/env python3
"""G5 BGM license & hash-chain audit (N7).

Walks the assembled master's ``bgmMix`` record backwards through the whole
music chain and re-hashes every link against the artifact that is supposed to
have produced it:

    assembly record  ->  mix contract  ->  G3 plan bgmPlan  ->  alignment
artifacts + report  ->  BGM audio file  ->  G0 candidate registration +
material-pack (license / distribution boundary)

Any byte that does not match is a failed check: the delivered audio bed is not
the audited, licensed asset.  Also re-verifies the execution fidelity (bed and
ducking depths, offset, fades, duck segments copied verbatim from the
contract), the measured in-place level (floor -33 LUFS, <= 3 LU drift from the
contract prediction) and the audibility window [target-18, target-6] LUFS.

Run from the repository root: every ``path``/``Ref`` stored in the artifacts is
resolved against the current working directory, never guessed from filenames.
Machine output is a single JSON audit file plus an echo on stdout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SCHEMA_VERSION = "0.1"
MEASURE_FLOOR_LUFS = -33.0
MEASURE_DRIFT_LU = 3.0
PREDICT_DRIFT_LU = 0.1


def sha256(path: str | Path) -> str:
    value = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest().upper()


def load_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


class Audit:
    def __init__(self) -> None:
        self.checks: list[dict] = []

    def add(self, check_id: str, ok: bool, detail: str) -> None:
        self.checks.append({"id": check_id, "status": "passed" if ok else "failed", "detail": detail})

    def warn(self, check_id: str, detail: str) -> None:
        self.checks.append({"id": check_id, "status": "warning", "detail": detail})

    @property
    def failed(self) -> list[dict]:
        return [item for item in self.checks if item["status"] == "failed"]


def audit(assembly: dict, plan: dict, registration: dict, material_pack: dict) -> Audit:
    audit_ = Audit()
    bgm_mix = assembly.get("bgmMix")
    if not isinstance(bgm_mix, dict):
        audit_.add("bgmMixPresent", False, "assembly record carries no bgmMix block — nothing to audit")
        return audit_
    audit_.add("bgmMixPresent", True, "assembly record bgmMix found")

    # --- link 1: assembly record -> mix contract file -----------------------
    contract_ref = bgm_mix.get("contract", {})
    contract_path = contract_ref.get("path")
    try:
        contract = load_json(contract_path)
        recomputed = sha256(contract_path)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        audit_.add("contractReadable", False, f"cannot read mix contract {contract_path!r}: {error}")
        return audit_
    audit_.add("contractFileHash", recomputed == contract_ref.get("sha256"),
               f"contract sha {recomputed[:12]}… vs assembly record {str(contract_ref.get('sha256'))[:12]}…")
    if contract.get("purpose") != "bgm_mix_contract" or contract.get("schemaVersion") != "0.1":
        audit_.add("contractPurpose", False, f"not a music-expert mix contract: purpose={contract.get('purpose')}")
        return audit_
    audit_.add("contractPurpose", True, "music-expert bgm_mix_contract v0.1")

    # --- link 2: contract -> BGM audio bytes --------------------------------
    audio_ref = bgm_mix.get("audio", {})
    audio_path = audio_ref.get("path") or contract.get("bgmAudio", {}).get("path")
    try:
        audio_sha = sha256(audio_path)
    except (OSError, TypeError) as error:
        audit_.add("bgmFileHash", False, f"cannot read BGM file {audio_path!r}: {error}")
        return audit_
    audit_.add("bgmFileHash",
               audio_sha == contract.get("bgmAudio", {}).get("sha256") == audio_ref.get("sha256"),
               f"delivered BGM bytes {audio_sha[:12]}… == contract == assembly record")
    audit_.add("bgmPlanHash", audio_sha == plan.get("bgmPlan", {}).get("audioSha256"),
               "contract BGM hash == approved G3 plan bgmPlan.audioSha256")

    # --- link 3: contract -> approved plan / alignment / analysis report ----
    evidence = contract.get("evidence", {})
    plan_sha = sha256(evidence.get("planRef", "")) if evidence.get("planRef") else ""
    audit_.add("planFileHash", plan_sha == evidence.get("planSha256"),
               "contract references the exact plan file presented to it")
    alignment_path = evidence.get("alignmentRef")
    try:
        alignment = load_json(alignment_path)
        alignment_sha = sha256(alignment_path)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        audit_.add("alignmentFileHash", False, f"cannot read alignment artifact: {error}")
        alignment = {}
        alignment_sha = ""
    audit_.add("alignmentFileHash",
               bool(alignment) and alignment_sha == evidence.get("alignmentSha256") == plan.get("bgmPlan", {}).get("alignmentSha256"),
               "alignment file sha == contract == plan bgmPlan.alignmentSha256")
    if alignment.get("inputs", {}).get("reportCacheKey", {}).get("sha256") != audio_sha:
        audit_.add("reportCacheKey", False, "analysis report was not built from the delivered BGM bytes")
        alignment_report = None
    else:
        audit_.add("reportCacheKey", True, "analysis report cacheKey == delivered BGM hash")
        report_path = alignment.get("inputs", {}).get("report")
        try:
            alignment_report = load_json(report_path)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            alignment_report = None

    # --- link 4: audible-by-arithmetic re-check from measured track loudness -
    predicted = contract.get("predictedLufs", {})
    track_lufs = (alignment_report or {}).get("loudness", {}).get("integratedLufs")
    bed = contract.get("bedGainDb")
    duck = contract.get("duckReductionDb")
    if track_lufs is None or bed is None or duck is None:
        audit_.add("audibilityRecheck", False, "missing measured track loudness or mix depths — cannot re-derive prediction")
    else:
        derived = round(track_lufs + bed - duck, 1)
        stated = predicted.get("bedDuckedLufs")
        ok = stated is not None and abs(derived - stated) <= PREDICT_DRIFT_LU
        window = predicted.get("windowLufs") or [predicted.get("narrationTargetLufs", -14) - 18, predicted.get("narrationTargetLufs", -14) - 6]
        in_window = isinstance(window, list) and window[0] <= derived <= window[1]
        audit_.add("audibilityRecheck", ok and in_window,
                   f"report {track_lufs} + bed {bed} - duck {duck} = {derived} LUFS (contract {stated}, window {window})")

    # --- link 5: G4 executed the contract verbatim --------------------------
    verbatim = all(bgm_mix.get(key) == contract.get(key)
                   for key in ("trackOffsetMs", "bedGainDb", "duckReductionDb", "fades", "duckSegments"))
    audit_.add("executionFidelity", verbatim,
               "assembly bgmMix offset/bed/duck/fades/duckSegments == contract fields" if verbatim
               else "G4 mix parameters diverge from the contract — mix was hand-tampered or stale")

    # --- link 6: measured in-place bed level --------------------------------
    measured = bgm_mix.get("measuredInPlaceLufs")
    stated = predicted.get("bedDuckedLufs")
    if not isinstance(measured, (int, float)):
        audit_.add("measuredInPlace", False, "assembly record lacks measuredInPlaceLufs — verification was not run")
    elif measured < MEASURE_FLOOR_LUFS or stated is None or abs(measured - stated) > MEASURE_DRIFT_LU:
        audit_.add("measuredInPlace", False, f"measured {measured} LUFS breaches floor {MEASURE_FLOOR_LUFS} or drifts from predicted {stated} by > {MEASURE_DRIFT_LU} LU")
    else:
        audit_.add("measuredInPlace", True, f"measured {measured} vs predicted {stated} LUFS — within drift")

    # --- link 7: license & distribution boundary at G0 -----------------------
    reg_sha = sha256(registration.get("_path", "")) if registration.get("_path") else None
    pack_audio = (material_pack.get("audioAssets") or [{}])[0]
    pack_reg = pack_audio.get("bgmRegistration", {})
    audit_.add("registrationChain",
               registration.get("sha256") == audio_sha
               and (reg_sha is None or reg_sha == pack_reg.get("sha256")),
               "candidate registration covers the delivered bytes"
               + ("" if reg_sha is None else " (registration file hash == material-pack record)")
               if registration.get("sha256") == audio_sha else "registration hash does not cover the delivered BGM bytes")
    license_type = registration.get("license")
    boundary = registration.get("distributionBoundary")
    audit_.add("licenseCleared", bool(license_type) and license_type != "unverified",
               f"license={license_type} evidence={registration.get('licenseEvidence')}")
    audit_.add("distributionBoundary",
               bool(boundary) and boundary == pack_reg.get("distributionBoundary"),
               f"boundary={boundary} matches material-pack registration")
    policy = plan.get("sourceAudioPolicy") or {}
    if plan.get("sourceAudioPolicy"):
        audit_.add("sourceAudioExcluded", True, f"plan source-audio policy recorded: {json.dumps(policy, ensure_ascii=False)[:120]}")
    else:
        audit_.warn("sourceAudioExcluded", "plan carries no sourceAudioPolicy — source-audio exclusion cannot be machine-confirmed")
    return audit_


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assembly-record", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path, help="Approved G3 edit plan (bgmPlan authority)")
    parser.add_argument("--registration", required=True, type=Path, help="G0 BGM candidate registration JSON")
    parser.add_argument("--material-pack", required=True, type=Path, help="G0 material-pack.json")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    try:
        registration = load_json(args.registration)
        registration["_path"] = str(args.registration)
        assembly, plan, pack = (load_json(p) for p in (args.assembly_record, args.plan, args.material_pack))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, ensure_ascii=False))
        return 2

    result = audit(assembly, plan, registration, pack)
    project_id = plan.get("projectId") or assembly.get("projectId")
    status = "failed" if result.failed else "passed"
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "node": "G5",
        "purpose": "bgm_chain_audit",
        "projectId": project_id,
        "status": status,
        "checks": result.checks,
        "bgm": {
            "audio": registration.get("audioPath"),
            "sha256": registration.get("sha256"),
            "license": registration.get("license"),
            "licenseEvidence": registration.get("licenseEvidence"),
            "distributionBoundary": registration.get("distributionBoundary"),
            "measuredInPlaceLufs": assembly.get("bgmMix", {}).get("measuredInPlaceLufs"),
        },
        "inputs": {
            "assemblyRecord": str(args.assembly_record),
            "plan": str(args.plan),
            "registration": str(args.registration),
            "materialPack": str(args.material_pack),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    echo = {"status": status, "audit": str(args.output),
            "failed": [item["id"] for item in result.failed],
            "warnings": [item["id"] for item in result.checks if item["status"] == "warning"]}
    print(json.dumps(echo, ensure_ascii=False))
    return 0 if status == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
