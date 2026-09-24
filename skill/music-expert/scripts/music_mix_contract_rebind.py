#!/usr/bin/env python3
"""Re-lock a BGM mix contract to the CURRENT approved G3 plan (issue ⑩, 2026-09-24).

Why this exists: the mix contract pins `evidence.planSha256` — the exact bytes of the
plan it was built from. A reopen-g3 amendment round legitimately rewrites the plan
(subtitle axis, fps field, approval stamps), so every downstream chain audit after the
revision reports planFileHash=failed even when the mix itself is untouched. Without a
sanctioned re-lock channel the only ways out are forging the old contract (forbidden)
or shipping a disclosed red light forever. This script is that channel:

  - mix parameters are COPIED field by field from the previous contract — the script
    never recomputes or accepts overrides for them (the same rule as g4_assemble:
    it does not pick gains; a rebind that changes a gain is not a rebind);
  - only `evidence.planRef/planSha256` move, plus an honest `rebind` provenance block;
  - the BGM audio bytes are re-hashed and must still equal the old contract (the
    thing being re-bound is the plan lock, never the audio);
  - version bumps v0.N -> v0.N+1 with next-free-path semantics (㉘: never overwrite).

The revised-round G4 re-run then consumes the NEWEST contract and the existing
approve/re-approval chain (R2 basisHashes) covers the new artifact like any other.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "0.1"
PURPOSE = "bgm_mix_contract"
REBIND_LOCKED_FIELDS = ("timelineMs", "trackOffsetMs", "bedGainDb", "duckReductionDb",
                        "fades", "ducking", "duckSegments", "mixMode", "predictedLufs")
VERSION_RE = re.compile(r"-v(\d+)\.(\d+)\.json$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True))


def fail_exit(errors: list) -> None:
    emit({"status": "invalid", "errors": errors})
    raise SystemExit(2)


def next_versioned_path(old_path: Path) -> Path:
    """v0.N -> v0.N+1, skipping any already-taken suffix (㉘ 自增永不覆盖)."""
    match = VERSION_RE.search(old_path.name)
    if not match:
        fail_exit([f"合同文件名不带 -vX.Y 版本段，无法自增：{old_path.name}"])
    major, minor = int(match.group(1)), int(match.group(2)) + 1
    while True:
        candidate = old_path.with_name(old_path.name[:match.start()] + f"-v{major}.{minor}.json")
        if not candidate.exists():
            return candidate
        minor += 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, type=Path, help="现行混音合同（上一批准版）")
    parser.add_argument("--plan", required=True, type=Path, help="修订轮重批后的 G3 计划（新锁对象）")
    parser.add_argument("--reason", required=True, help="重锁原因（点名修订轮修了什么，与混音无关）")
    args = parser.parse_args()
    errors: list = []
    if not args.contract.is_file():
        fail_exit([f"现行合同不存在：{args.contract}"])
    if not args.plan.is_file():
        fail_exit([f"新批准计划不存在：{args.plan}"])
    try:
        contract = json.loads(args.contract.read_text(encoding="utf-8-sig"))
    except ValueError as error:
        fail_exit([f"现行合同不是合法 JSON：{error}"])
    if contract.get("skill") != "music-expert" or contract.get("purpose") != PURPOSE:
        fail_exit(["只重锁 music-expert bgm_mix_contract；这份文件身份不符"])
    audio = contract.get("bgmAudio", {})
    audio_path = Path(str(audio.get("path", "")))
    if not audio_path.is_file():
        fail_exit([f"合同登记的 BGM 音频文件不在盘上：{audio_path}（重锁不许掩盖丢字节）"])
    if sha256(audio_path) != str(audio.get("sha256", "")).upper():
        fail_exit(["BGM 音频字节与合同登记不符——变的是音乐不是计划，不走重锁通道，重跑 music_mix_plan 并回 G3 重批"])
    evidence = contract.get("evidence", {})

    rebinding_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    new_contract = json.loads(json.dumps(contract))  # deep copy: params ride along verbatim
    new_contract["evidence"] = {**evidence, "planRef": str(args.plan), "planSha256": sha256(args.plan)}
    new_contract["rebind"] = {
        "rebindFrom": {"path": str(args.contract), "sha256": sha256(args.contract)},
        "reason": args.reason,
        "rebindAt": rebinding_at,
        "note": "仅重锁计划指纹；混音参数逐字段原样继承（脚本无参数覆盖入口），BGM 字节已复验",
    }
    # Machine self-proof that nothing but the lock moved: strip the sanctioned keys,
    # everything else must be byte-equal in value to the old contract.
    def comparable(doc: dict) -> dict:
        return {key: value for key, value in doc.items() if key not in {"evidence", "rebind"}}
    if comparable(new_contract) != comparable(contract):
        fail_exit(["内部错误：复制后参数发生漂移（本脚本不可能做到，出现即 bug），拒绝出合同"])
    for field in REBIND_LOCKED_FIELDS:
        if new_contract.get(field) != contract.get(field):
            fail_exit([f"锁定字段 {field} 不一致——重锁工具拒绝携带任何参数改动"])

    output_path = next_versioned_path(args.contract)
    output_path.write_text(json.dumps(new_contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    emit({"status": "completed", "contract": str(output_path), "rebindFrom": str(args.contract),
          "planRef": str(args.plan), "planSha256": new_contract["evidence"]["planSha256"],
          "paramsUnchanged": True, "lockedFields": list(REBIND_LOCKED_FIELDS)})
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        emit({"status": "invalid", "errors": [str(error)]})
        raise SystemExit(2)
