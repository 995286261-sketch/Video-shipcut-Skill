#!/usr/bin/env python3
"""Search NetEase Cloud Music for BGM candidates — internal-test audition discovery only.

Probe evidence (2026-09-10, references/library-probes.md): the legacy public search
endpoint returns song metadata without auth, and the outer preview url serves a real
decodable mp3.  This adapter therefore does the "找" half of the sourcing loop for the
mainland catalog the reviewers actually know: search -> candidate manifest -> optional
preview download with SHA-256 + ffmpeg decode probe (issue 023 rules).

What it NEVER does: claim a license.  Every candidate carries
``license: uncleared-platform-catalog`` and ``distributionBoundary: internal_test``.
Platform catalog authorization covers in-app playback only — using a track in a video
requires a human to obtain the file through official channels and register it with real
license evidence via ``music_register_candidate.py`` before it can enter an edit plan
(sourcing-contract track three).  Risk-control responses (-462/verifyType) and any
network failure are a structured block; no silent fallback, no retry storms.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SEARCH_URL = os.environ.get("P0C_NETEASE_SEARCH_URL", "https://music.163.com/api/search/get/web")
PREVIEW_BASE = os.environ.get("P0C_NETEASE_PREVIEW_BASE", "https://music.163.com/song/media/outer/url")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Referer": "https://music.163.com/",
    "Content-Type": "application/x-www-form-urlencoded",
}


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True))


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def classify_block(payload: object) -> dict | None:
    """Risk control / malformed payloads become structured blockers, never candidates."""
    if not isinstance(payload, dict):
        return {"type": "malformed_response", "detail": "search payload is not a JSON object"}
    code = payload.get("code")
    if code != 200:
        kind = "risk_control" if code == -462 or "verifyType" in payload else "api_error"
        return {"type": kind, "detail": f"netease code {code}: {str(payload.get('message', ''))[:120]}"}
    if not isinstance(payload.get("result"), dict) or not isinstance(payload["result"].get("songs"), list):
        return {"type": "malformed_response", "detail": "payload lacks result.songs"}
    return None


def candidate_record(song: dict) -> dict:
    artists = "、".join(a.get("name", "") for a in song.get("artists", []) if a.get("name"))
    album = (song.get("album") or {}).get("name")
    return {
        "schemaVersion": "0.1",
        "skill": "music-expert",
        "provenance": "netease_search",
        "neteaseId": song.get("id"),
        "title": song.get("name"),
        "artist": artists,
        "album": album,
        "durationMs": song.get("duration"),
        "fee": song.get("fee"),
        "sourceUrl": f"https://music.163.com/song?id={song.get('id')}",
        "previewUrl": f"{PREVIEW_BASE}?id={song.get('id')}.mp3",
        "license": "uncleared-platform-catalog",
        "licenseNote": "平台曲库仅覆盖端内播放授权；候选只用于 internal_test 试听选型。"
                       "整轨必须经人通过官方渠道取得并用 music_register_candidate.py 登记真实许可证据后方可进剪辑计划（sourcing-contract 轨道三）。",
        "attributionRequired": True,
        "attributionText": f"{artists} - {song.get('name')}",
        "retrievedAt": now(),
        "distributionBoundary": "internal_test",
        "decodeProbe": {"status": "not_run", "engine": "ffmpeg"},
        "analysisRef": None,
    }


def search(query: str, limit: int) -> tuple[dict | None, dict | None]:
    data = urllib.parse.urlencode({"s": query, "type": 1, "offset": 0, "limit": max(min(limit * 3, 100), limit)}).encode()
    request = urllib.request.Request(SEARCH_URL, data=data, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        kind = "rate_limited" if error.code == 429 else "http_error"
        return None, {"type": kind, "detail": f"HTTP {error.code} from search endpoint"}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        return None, {"type": "network_failed", "detail": str(error)[:200]}
    blocker = classify_block(payload)
    if blocker is not None:
        return None, blocker
    return payload, None


def download(url: str, target: Path) -> str | None:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=120) as response:
            data = response.read()
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        return f"download failed: {str(error)[:150]}"
    if not data:
        return "downloaded file is empty"
    target.write_bytes(data)
    if not target.is_file() or target.stat().st_size == 0:
        return "download did not land on disk"
    return None


def decode_probe(path: Path) -> tuple[bool, str]:
    result = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    return result.returncode == 0, (result.stderr or "").strip()[:200]


def load_terms_file(path: Path) -> tuple[list[dict], dict, list]:
    """Read a BGM-检索词 contract; returns (terms, filters, errors)."""
    errors: list = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        return [], {}, [{"field": "termsFile", "error": str(error)[:200]}]
    if payload.get("purpose") != "bgm_search_terms":
        errors.append({"field": "termsFile", "error": "not a bgm_search_terms contract"})
    terms = payload.get("terms") or []
    if not terms:
        errors.append({"field": "termsFile", "error": "contract carries no terms"})
    return terms, payload.get("filters") or {}, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default=None, help="free-text song/genre/mood query (中文优先)")
    parser.add_argument("--terms-file", default=None, type=Path,
                        help="BGM-检索词-v0.1.json from music_search_terms.py (searches every term, merges)")
    parser.add_argument("--max-results", type=int, default=8)
    parser.add_argument("--duration-min", type=float, default=15.0, help="seconds")
    parser.add_argument("--duration-max", type=float, default=600.0, help="seconds")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--no-preview", action="store_true", help="search only; do not download previews")
    args = parser.parse_args()

    if (args.query is None) == (args.terms_file is None):
        emit({"status": "invalid", "errors": [{"field": "query",
              "rule": "exactly one of --query or --terms-file is required"}]})
        return 2
    queries, contract_filters = [args.query], {}
    if args.terms_file is not None:
        records, filters, errors = load_terms_file(args.terms_file)
        if errors:
            emit({"status": "invalid", "errors": errors})
            return 2
        queries = [record["term"] for record in records]
        contract_filters = filters
    if contract_filters.get("durationMinSec"):
        args.duration_min = max(args.duration_min, float(contract_filters["durationMinSec"]))

    if not args.no_preview and shutil.which("ffmpeg") is None:
        emit({"status": "blocked", "blockers": [{"type": "missing_toolchain",
              "detail": "ffmpeg required for the decode probe of previews (or pass --no-preview)"}]})
        return 2

    songs, blockers = [], []
    for query in queries:
        payload, error = search(query, args.max_results)
        if payload is None:
            blockers.append({"query": query, **error})
            continue
        songs.extend(payload["result"]["songs"])
    if blockers and len(blockers) == len(queries):
        emit({"status": "blocked", "blockers": blockers})
        return 2
    deduped, seen_ids = [], set()
    for song in songs:
        song_id = (song or {}).get("id")
        if song_id is None or song_id in seen_ids:
            continue
        seen_ids.add(song_id)
        deduped.append(song)

    candidates, excluded = [], []
    for song in deduped:
        if len(candidates) >= args.max_results:
            break  # 下载封顶：够数即停，不超量拉取（自测发现 83 件下载 vs 清单 10 条的浪费）
        record = candidate_record(song or {})
        duration_ms = record.get("durationMs")
        if not record.get("neteaseId") or not isinstance(duration_ms, (int, float)):
            excluded.append({"neteaseId": record.get("neteaseId"), "name": record.get("title"),
                             "reason": "missing id or duration in payload"})
            continue
        if not args.duration_min * 1000 <= duration_ms <= args.duration_max * 1000:
            excluded.append({"neteaseId": record["neteaseId"], "name": record["title"],
                             "reason": f"duration {duration_ms}ms outside [{args.duration_min},{args.duration_max}]s"})
            continue
        if not args.no_preview:
            target_dir = args.output_dir / "candidates"
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / f"netease-{record['neteaseId']}-preview.mp3"
            failure = download(record["previewUrl"], target)
            if failure is not None:
                excluded.append({"neteaseId": record["neteaseId"], "name": record["title"], "reason": failure})
                continue
            passed, detail = decode_probe(target)
            record["previewPath"] = str(target.resolve())
            record["sha256"] = sha256(target)
            record["byteSize"] = target.stat().st_size
            record["decodeProbe"] = {"status": "passed" if passed else "failed", "engine": "ffmpeg"}
            if not passed:
                record["decodeProbe"]["error"] = detail or "undecodable"
        candidates.append(record)

    kept = [c for c in candidates if c["decodeProbe"]["status"] != "failed"][: args.max_results]
    manifest_path = args.output_dir / f"BGM-候选清单-netease-{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({
        "schemaVersion": "0.1", "purpose": "bgm_candidate_pool", "source": "netease_search",
        "usageBoundary": "internal_test 试听选型专用；未清权候选禁止进入任何对外分发项目的剪辑计划",
        "query": {"text": args.query} if args.query else {"termsFile": str(args.terms_file), "terms": queries},
        "partialFailures": blockers, "retrievedAt": now(),
        "candidates": kept, "excluded": excluded,
        "sufficiency": {"count": len(kept), "minimumExpected": 3},
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    emit({"status": "completed", "manifest": str(manifest_path), "candidates": len(kept),
          "excluded": len(excluded), "previewsDownloaded": not args.no_preview})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
