#!/usr/bin/env python3
"""Search Freesound for BGM candidates and register them with a full license evidence chain.

This is the ONLY sanctioned automatic online sourcing adapter in music-expert (see
references/sourcing-contract.md). Every candidate keeps: source URL, per-sound license,
author, retrieval time, downloaded preview SHA-256 and a decode probe result (issue 023
rule). A missing token or any network/auth failure is a structured block — the script
never silently falls back to another source. Source files already owned by the user are
never touched here.
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

API_BASE = "https://freesound.org/apiv2"
SEARCH_FIELDS = "id,name,username,license,type,duration,previews,urls.page,tags,attribution"
ACCEPTED_LICENSES = {
    "Creative Commons 0": {"licenseType": "cc0", "attributionRequired": False},
    "Attribution": {"licenseType": "cc-by", "attributionRequired": True},
    "Attribution (http://creativecommons.org/licenses/by/4.0/)": {"licenseType": "cc-by", "attributionRequired": True},
}
EXCLUDED_LICENSE_MARKERS = ("nc", "noncommercial", "non-commercial", "nd", "noderiv", "sampling")


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


def classify_license(raw: str | None) -> dict | None:
    if not raw:
        return None
    normalized = raw.strip()
    for name, verdict in ACCEPTED_LICENSES.items():
        if normalized == name or normalized.startswith(name):
            lowered = normalized.lower()
            if any(marker in lowered for marker in EXCLUDED_LICENSE_MARKERS):
                return None
            return verdict
    return None


def api_get(token: str, path: str, params: dict) -> tuple[dict | None, dict | None]:
    query = urllib.parse.urlencode({**params, "token": token})
    request = urllib.request.Request(f"{API_BASE}{path}?{query}", headers={"User-Agent": "p0c-music-expert/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8")), None
    except urllib.error.HTTPError as error:
        kind = "auth_failed" if error.code in (401, 403) else ("rate_limited" if error.code == 429 else "http_error")
        return None, {"type": kind, "detail": f"HTTP {error.code} from {path}"}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        return None, {"type": "network_failed", "detail": str(error)[:200]}


def download(url: str, target: Path) -> str | None:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "p0c-music-expert/0.1"}), timeout=120) as response:
            data = response.read()
    except (urllib.error.URLError, TimeoutError) as error:
        return f"download failed: {str(error)[:150]}"
    if not data:
        return "downloaded file is empty"
    target.write_bytes(data)
    # Issue 022 rule: exit-success is not proof; the bytes must be on disk.
    if not target.is_file() or target.stat().st_size == 0:
        return "download did not land on disk"
    return None


def decode_probe(path: Path) -> tuple[bool, str]:
    result = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    return result.returncode == 0, (result.stderr or "").strip()[:200]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default=None, help="free-text mood/genre query")
    parser.add_argument("--tags", default=None, help="comma-separated freesound tags")
    parser.add_argument("--similar-to", type=int, default=None, help="Freesound sound id for content-based similarity search")
    parser.add_argument("--duration-min", type=float, default=15.0)
    parser.add_argument("--duration-max", type=float, default=600.0)
    parser.add_argument("--max-results", type=int, default=8)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--no-download", action="store_true", help="search and filter only; do not fetch previews")
    args = parser.parse_args()

    if args.query is None and args.tags is None and args.similar_to is None:
        emit({"status": "invalid", "errors": [{"field": "query", "rule": "need --query, --tags or --similar-to"}]})
        return 2
    token = (os.environ.get("MUSIC_EXPERT_FREESOUND_TOKEN") or os.environ.get("P0C_FREESOUND_TOKEN") or "").strip()
    if not token:
        emit({"status": "blocked", "blockers": [{"type": "missing_token",
              "detail": "MUSIC_EXPERT_FREESOUND_TOKEN (or the legacy P0C_FREESOUND_TOKEN) is unset; register a free Freesound API token. Silent fallback to unlicensed sources is forbidden (sourcing-contract)."}]})
        return 2
    if not args.no_download and shutil.which("ffmpeg") is None:
        emit({"status": "blocked", "blockers": [{"type": "missing_toolchain", "detail": "ffmpeg required for the decode probe of downloads"}]})
        return 2

    if args.similar_to is not None:
        payload, error = api_get(token, f"/sounds/{args.similar_to}/similar/", {"page_size": args.max_results, "fields": SEARCH_FIELDS})
    else:
        params = {"fields": SEARCH_FIELDS, "page_size": max(args.max_results * 3, args.max_results), "min_duration": args.duration_min, "max_duration": args.duration_max}
        if args.query:
            params["query"] = args.query
        if args.tags:
            params["filter"] = " ".join(f'tag:"{tag.strip()}"' for tag in args.tags.split(",") if tag.strip())
        payload, error = api_get(token, "/search/text/", params)
    if payload is None:
        emit({"status": "blocked", "blockers": [error]})
        return 2

    results = payload.get("results", [])
    candidates_dir = args.output_dir / "candidates"
    candidates = []
    excluded = []
    for item in results:
        verdict = classify_license(item.get("license"))
        if verdict is None:
            excluded.append({"freesoundId": item.get("id"), "name": item.get("name"), "license": item.get("license"),
                             "reason": "license not in {CC0, CC-BY} or carries NC/ND/Sampling restriction"})
            continue
        record = {
            "schemaVersion": "0.1",
            "skill": "music-expert",
            "provenance": "freesound_api",
            "freesoundId": item.get("id"),
            "title": item.get("name"),
            "author": item.get("username"),
            "sourceUrl": (item.get("urls") or {}).get("page"),
            "license": item.get("license"),
            "licenseType": verdict["licenseType"],
            "attributionRequired": verdict["attributionRequired"],
            "attributionText": item.get("attribution"),
            "durationSecProbe": item.get("duration"),
            "tags": (item.get("tags") or [])[:12],
            "retrievedAt": now(),
            "distributionBoundary": "internal_test",
            "decodeProbe": {"status": "not_run", "engine": "ffmpeg"},
            "analysisRef": None,
        }
        if not args.no_download:
            preview = ((item.get("previews") or {}).get("preview_mp3")
                       or (item.get("previews") or {}).get("preview_lq_mp3"))
            if not preview:
                excluded.append({"freesoundId": record["freesoundId"], "name": record["title"], "reason": "no preview url in response"})
                continue
            candidates_dir.mkdir(parents=True, exist_ok=True)
            target = candidates_dir / f"freesound-{record['freesoundId']}-preview.mp3"
            download_error = download(preview, target)
            if download_error is not None:
                excluded.append({"freesoundId": record["freesoundId"], "name": record["title"], "reason": download_error})
                continue
            passed, probe_detail = decode_probe(target)
            record["previewPath"] = str(target.resolve())
            record["sha256"] = sha256(target)
            record["byteSize"] = target.stat().st_size
            record["decodeProbe"] = {"status": "passed" if passed else "failed", "engine": "ffmpeg"}
            if not passed:
                record["decodeProbe"]["error"] = probe_detail or "undecodable"
        candidates.append(record)

    kept = [c for c in candidates if c["decodeProbe"]["status"] != "failed"]
    manifest_path = args.output_dir / f"BGM-候选清单-freesound-{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({
        "schemaVersion": "0.1", "purpose": "bgm_candidate_pool", "source": "freesound",
        "query": {"text": args.query, "tags": args.tags, "similarTo": args.similar_to},
        "retrievedAt": now(), "candidates": kept, "excluded": excluded,
        "sufficiency": {"count": len(kept), "minimumExpected": 3},
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    emit({"status": "completed", "manifest": str(manifest_path), "candidates": len(kept), "excluded": len(excluded),
          "downloaded": not args.no_download})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
