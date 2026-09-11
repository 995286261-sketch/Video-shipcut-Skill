#!/usr/bin/env python3
"""The cross-project music experience library (experience/music) — sole write entry.

One record per track, identity = SHA-256 of the audio content. Four layers, never
impersonating each other: track.json (identity + license traffic light), acoustic.json
(deterministic facts: bpm/energy timeline/climax), listen.md (audio-model absolute
attributes, stamped with model+prompt version, append-only), verdicts.jsonl (human
adjudications, append-only raw words).

Red lines (user 2026-09-11):
- 音频本体永不进库：未清权试听件的"复用"= 凭 neteaseId/sourceUrl 证据重取 + SHA 验明正身；
  已清权文件是项目素材资产的指针（audioRefs），不是库内容。
- license 只升不降：登记(grant)才能翻转红灯，重复 ingest 绝不覆盖既有更强许可。
- 相对评价（A/B 贴合分）不做库事实；库里只有绝对属性。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import music_recommend  # reuse the deterministic 16-bucket macro-curve resampler

SCHEMA = "0.1"
# license strength: 0 = 红灯（不得进成片）, 1 = 可用需署名, 2 = 干净
LICENSE_STRENGTH = {"uncleared-platform-catalog": 0, "unknown": 0,
                    "cc-by": 1, "cc-by-sa": 1,
                    "public-domain": 2, "cc0": 2, "owned": 2, "cleared-for-project": 2}


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def track_dir(root: Path, sha: str) -> Path:
    return root / "tracks" / sha[:16]


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def emit(payload) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=1))


def fail(errors: list) -> int:
    emit({"status": "invalid", "errors": errors})
    return 2


def upsert_track(root: Path, sha: str, *, title=None, artist=None, netease_id=None,
                 source_url=None, provenance=None, project=None, license_value=None,
                 boundary=None, attribution_required=None, audio_ref=None) -> tuple[dict, list]:
    """Create or merge the identity card. License is monotonic: never downgrades."""
    card_path = track_dir(root, sha) / "track.json"
    notes = []
    card = read_json(card_path) if card_path.is_file() else {
        "schemaVersion": SCHEMA, "sha256": sha, "aliases": [], "audioRefs": [], "roles": ["candidate"],
        "license": license_value or "unknown", "licenseEvidence": [],
        "distributionBoundary": boundary or "internal_test", "attributionRequired": True,
        "createdAt": now(),
    }
    alias = {"title": title, "artist": artist, "neteaseId": netease_id, "sourceUrl": source_url,
             "provenance": provenance, "project": project, "seenAt": now()}
    alias = {k: v for k, v in alias.items() if v is not None}
    if alias and not any(a.get("title") == title and a.get("neteaseId") == netease_id for a in card["aliases"]):
        card["aliases"].append(alias)
    if license_value:
        old, new = card["license"], license_value
        if LICENSE_STRENGTH.get(new, 0) >= LICENSE_STRENGTH.get(old, 0):
            card["license"] = new
        else:
            notes.append(f"licenseKeptExisting:{old}")  # 只升不降
    # 许可边界是许可事实，只随 grant 变；重复 ingest 见到更宽的说法也绝不放宽记录
    if attribution_required is not None:
        card["attributionRequired"] = bool(attribution_required)
    if audio_ref and not any(r.get("path") == str(audio_ref) for r in card["audioRefs"]):
        card["audioRefs"].append({"path": str(audio_ref), "recordedAt": now()})
    card["updatedAt"] = now()
    write_json(card_path, card)
    return card, notes


def put_acoustic(root: Path, sha: str, report: Path) -> dict:
    if not (track_dir(root, sha) / "track.json").is_file():
        raise FileNotFoundError("identity first: ingest the track before attaching acoustic facts")
    data = read_json(report)
    segments = [{"startMs": s.get("startMs"), "endMs": s.get("endMs"), "energyMean": s.get("energyMean")}
                for s in data.get("energySegments", [])]
    climax = max(segments, key=lambda s: s.get("energyMean") or 0, default=None)
    curve = data.get("energyCurve") or [s.get("energyMean", 0.0) for s in data.get("energySegments", [])]
    payload = {"schemaVersion": SCHEMA, "sha256": sha, "reportPath": str(report.resolve()),
               "durationMs": (data.get("source") or {}).get("decodedDurationMs"),
               "tempoBpm": data.get("tempoBpm"),
               "integratedLufs": (data.get("loudness") or {}).get("integratedLufs"),
               "segments": segments, "macroCurve16": music_recommend.resample_curve(curve),
               "climaxSegment": climax, "recordedAt": now()}
    write_json(track_dir(root, sha) / "acoustic.json", payload)
    return payload


def put_listen(root: Path, sha: str, notes_text: str, model: str, prompt_ver: str,
               reference: str | None = None) -> Path:
    if reference:
        raise SystemExit("拒绝写入：相对评价（A/B）不是库事实，只有绝对属性笔记可入库")
    path = track_dir(root, sha) / "listen.md"
    header = "# 听觉模型绝对属性笔记\n\n" if not path.is_file() else path.read_text(encoding="utf-8")
    section = f"\n---\n\n> heardAt {now()}｜model={model}｜prompt={prompt_ver}\n\n{notes_text.strip()}\n"
    path.write_text(header + section, encoding="utf-8")
    return path


def listen_meta(path: Path) -> list[dict]:
    metas = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("> heardAt"):
                parts = dict(p.strip().split("=", 1) for p in line.split("｜")[1:] if "=" in p)
                metas.append({"heardAt": line.split("｜")[0].replace("> heardAt", "").strip(), **parts})
    return metas


def latest_listen_note(root: Path, sha: str, model: str, prompt_ver: str) -> tuple[str, str] | None:
    """Return (heardAt, body) of the newest note made by the same model+prompt version."""
    path = track_dir(root, sha) / "listen.md"
    if not path.is_file():
        return None
    best = None
    for section in path.read_text(encoding="utf-8").split("\n---\n")[1:]:
        lines = section.strip().splitlines()
        if not lines or not lines[0].startswith("> heardAt"):
            continue
        heard_at = lines[0].split("｜")[0].replace("> heardAt", "").strip()
        meta = dict(p.strip().split("=", 1) for p in lines[0].split("｜")[1:] if "=" in p)
        if meta.get("model") == model and meta.get("prompt") == prompt_ver:
            best = (heard_at, "\n".join(lines[1:]).strip())
    return best


def append_verdict(root: Path, sha: str, text: str, project: str | None, who: str, event: str | None = None) -> None:
    path = track_dir(root, sha) / "verdicts.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"at": now(), "who": who, "project": project, "text": text}
    if event:
        entry["event"] = event
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def warnings_for(card: dict, project_boundary: str | None) -> list[str]:
    warns = []
    strength = LICENSE_STRENGTH.get(card.get("license", "unknown"), 0)
    if strength == 0:
        warns.append("🔴 未清权（{}）：档案只能复用过选型记忆；进成片必须官方渠道取得并登记后 grant".format(card.get("license")))
        if project_boundary and project_boundary != card.get("distributionBoundary"):
            warns.append("🔴 项目边界 {} ≠ 档案许可边界 {}：不得使用".format(project_boundary, card.get("distributionBoundary")))
    elif strength == 1 and card.get("attributionRequired"):
        warns.append("🟡 需署名：分发前核对 attribution 证据")
    return warns


def find_tracks(root: Path, match: str | None, sha: str | None, role: str | None) -> list[Path]:
    result = []
    for card_path in sorted((root / "tracks").glob("*/track.json")):
        card = read_json(card_path)
        if sha and card.get("sha256", "").upper() != sha.upper():
            continue
        if role and role not in card.get("roles", []):
            continue
        if match:
            needle = match.lower()
            hay = json.dumps(card.get("aliases", []), ensure_ascii=False).lower()
            if needle not in hay:
                continue
        result.append(card_path)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    sub = parser.add_subparsers(dest="action", required=True)

    p = sub.add_parser("ingest")
    p.add_argument("--audio", type=Path, help="existing file to hash (else --sha required)")
    p.add_argument("--sha")
    p.add_argument("--title"); p.add_argument("--artist"); p.add_argument("--netease-id")
    p.add_argument("--source-url"); p.add_argument("--provenance"); p.add_argument("--project")
    p.add_argument("--license"); p.add_argument("--boundary")
    p.add_argument("--attribution-required"); p.add_argument("--audio-ref")

    p = sub.add_parser("acoustic")
    p.add_argument("--sha", required=True); p.add_argument("--report", required=True, type=Path)

    p = sub.add_parser("listen")
    p.add_argument("--sha", required=True)
    p.add_argument("--notes-file", type=Path); p.add_argument("--notes-text")
    p.add_argument("--model", required=True); p.add_argument("--prompt-ver", required=True)
    p.add_argument("--reference", help="forbidden: proves the note is relative; refuse")

    p = sub.add_parser("verdict")
    p.add_argument("--sha", required=True); p.add_argument("--text", required=True)
    p.add_argument("--project"); p.add_argument("--who", default="user")

    p = sub.add_parser("grant")
    p.add_argument("--sha", required=True); p.add_argument("--license", required=True)
    p.add_argument("--evidence", required=True); p.add_argument("--audio"); p.add_argument("--project")

    p = sub.add_parser("anchor")
    p.add_argument("--sha", required=True); p.add_argument("--brief", required=True, type=Path)

    p = sub.add_parser("query")
    p.add_argument("--match"); p.add_argument("--sha")
    p.add_argument("--role", choices=["anchor", "candidate"])
    p.add_argument("--project-boundary")

    args = parser.parse_args()
    root = args.root

    if args.action == "ingest":
        sha = args.sha or (sha256_file(args.audio) if args.audio and args.audio.is_file() else None)
        if not sha:
            return fail([{"field": "audio/sha", "rule": "one of --audio(existing file) or --sha is required"}])
        card, notes = upsert_track(root, sha, title=args.title, artist=args.artist,
                                   netease_id=args.netease_id, source_url=args.source_url,
                                   provenance=args.provenance, project=args.project,
                                   license_value=args.license, boundary=args.boundary,
                                   attribution_required=args.attribution_required,
                                   audio_ref=args.audio_ref)
        emit({"status": "ok", "action": "ingest", "sha256": sha, "track": str(track_dir(root, sha)),
              "license": card["license"], "notes": notes})
        return 0

    if args.action == "acoustic":
        try:
            payload = put_acoustic(root, args.sha, args.report)
        except FileNotFoundError as error:
            return fail([{"field": "sha", "rule": str(error)}])
        emit({"status": "ok", "action": "acoustic", "climaxSegment": payload["climaxSegment"]})
        return 0

    if args.action == "listen":
        if args.reference:
            emit({"status": "rejected", "errors": [{"field": "reference",
                  "rule": "相对评价（A/B 贴合分）不做库事实；只存绝对属性笔记"}]})
            return 2
        if args.notes_file:
            text = args.notes_file.read_text(encoding="utf-8")
        elif args.notes_text:
            text = args.notes_text
        else:
            return fail([{"field": "notes", "rule": "--notes-file or --notes-text required"}])
        path = put_listen(root, args.sha, text, args.model, args.prompt_ver)
        emit({"status": "ok", "action": "listen", "path": str(path)})
        return 0

    if args.action == "verdict":
        append_verdict(root, args.sha, args.text, args.project, args.who)
        emit({"status": "ok", "action": "verdict"})
        return 0

    if args.action == "grant":
        card_path = track_dir(root, args.sha) / "track.json"
        if not card_path.is_file():
            return fail([{"field": "sha", "rule": "no track record; ingest first"}])
        card = read_json(card_path)
        card["license"] = args.license
        card["licenseEvidence"].append({"evidence": args.evidence, "at": now(), "project": args.project})
        if args.audio:
            card["audioRefs"].append({"path": str(args.audio), "role": "cleared", "recordedAt": now()})
        write_json(card_path, card)
        append_verdict(root, args.sha, f"许可登记：{args.license}｜证据：{args.evidence}", args.project, "user",
                       event="license_granted")
        emit({"status": "ok", "action": "grant", "license": args.license})
        return 0

    if args.action == "anchor":
        card_path = track_dir(root, args.sha) / "track.json"
        if not card_path.is_file():
            return fail([{"field": "sha", "rule": "no track record; ingest first"}])
        card = read_json(card_path)
        if "anchor" not in card["roles"]:
            card["roles"].append("anchor")
        write_json(card_path, card)
        (track_dir(root, args.sha) / "style-brief.json").write_bytes(args.brief.read_bytes())
        emit({"status": "ok", "action": "anchor"})
        return 0

    # query
    matches = []
    for card_path in find_tracks(root, args.match, args.sha, args.role):
        card = read_json(card_path)
        directory = card_path.parent
        matches.append({"track": card, "directory": str(directory),
                        "hasAcoustic": (directory / "acoustic.json").is_file(),
                        "listenNotes": listen_meta(directory / "listen.md"),
                        "verdictCount": sum(1 for _ in (directory / "verdicts.jsonl").open("r", encoding="utf-8"))
                        if (directory / "verdicts.jsonl").is_file() else 0,
                        "warnings": warnings_for(card, args.project_boundary)})
    emit({"status": "ok", "count": len(matches), "tracks": matches})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
