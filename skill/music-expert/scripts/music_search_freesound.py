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
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import music_tags

API_BASE = "https://freesound.org/apiv2"

# --- URL allowlist guard (SSRF, Mimosa L3 pre-commit 2026-09-21): only the official
# Freesound host may ever be fetched, and redirects are refused, never blind-followed.
ALLOWED_HOSTS = ("freesound.org",)
_REDIRECT_CODES = (301, 302, 303, 307, 308)


class _RefuseRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_RefuseRedirect)


def guard_url(url: str) -> str | None:
    """Return None when the URL may be fetched, else the refusal reason."""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return "malformed URL"
    if parts.scheme != "https":
        return f"scheme {parts.scheme or '?'} is not https"
    host = (parts.hostname or "").lower()
    if not any(host == d or host.endswith("." + d) for d in ALLOWED_HOSTS):
        return f"host {host or '?'} is outside the allowlist"
    return None
SEARCH_FIELDS = "id,name,username,license,type,duration,previews,urls.page,tags,attribution"
# The API's license field arrives either as a display name or as a Creative
# Commons URL (live-verified 2026-09-17: URLs like .../publicdomain/zero/1.0/);
# both forms must classify identically. Only CC0/CC-BY pass; NC/ND/Sampling fail closed.
CC0_MARKERS = ("publicdomain/zero", "creative commons 0", "cc0", "cc 0")
EXCLUDED_LICENSE_MARKERS = ("by-nc", "by-nd", "nc-sa", "nc-nd", "noncommercial", "non-commercial",
                            "no derivatives", "no-deriv", "noderiv", "sampling", "attribution -", "attribution-")


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
    lowered = raw.strip().lower()
    if any(marker in lowered for marker in EXCLUDED_LICENSE_MARKERS):
        return None
    if any(marker in lowered for marker in CC0_MARKERS):
        return {"licenseType": "cc0", "attributionRequired": False}
    if "licenses/by/" in lowered or lowered.startswith("attribution"):
        return {"licenseType": "cc-by", "attributionRequired": True}
    return None


def api_get(token: str, path: str, params: dict) -> tuple[dict | None, dict | None]:
    query = urllib.parse.urlencode({**params, "token": token})
    url = f"{API_BASE}{path}?{query}"
    refusal = guard_url(url)
    if refusal:
        return None, {"type": "url_not_allowed", "detail": f"SSRF guard: {refusal}"}
    request = urllib.request.Request(url, headers={"User-Agent": "p0c-music-expert/0.1"})
    try:
        with _OPENER.open(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8")), None
    except urllib.error.HTTPError as error:
        if error.code in _REDIRECT_CODES:
            return None, {"type": "redirect_refused", "detail": f"HTTP {error.code} redirect refused by SSRF guard"}
        kind = "auth_failed" if error.code in (401, 403) else ("rate_limited" if error.code == 429 else "http_error")
        return None, {"type": kind, "detail": f"HTTP {error.code} from {path}"}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        return None, {"type": "network_failed", "detail": str(error)[:200]}


def download(url: str, target: Path) -> str | None:
    refusal = guard_url(url)
    if refusal:
        return f"download blocked by SSRF guard: {refusal}"
    try:
        with _OPENER.open(urllib.request.Request(url, headers={"User-Agent": "p0c-music-expert/0.1"}), timeout=120) as response:
            data = response.read()
    except urllib.error.HTTPError as error:
        if error.code in _REDIRECT_CODES:
            return "download blocked by SSRF guard: redirect refused"
        return f"download failed: HTTP {error.code}"
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


def load_terms_file(path: Path) -> tuple[list[dict], dict, list]:
    """Read a BGM-检索词 contract; returns (terms, filters, errors). Mirrors
    music_search_netease.py — duplicated by design, search-terms-contract.md is truth."""
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
    parser.add_argument("--query", default=None, help="free-text mood/genre query")
    parser.add_argument("--terms-file", default=None, type=Path,
                        help="BGM-检索词-v0.1.json from music_search_terms.py (searches every term, merges)")
    parser.add_argument("--tags", default=None, help="comma-separated freesound tags")
    parser.add_argument("--similar-to", type=int, default=None, help="Freesound sound id for content-based similarity search")
    parser.add_argument("--duration-min", type=float, default=15.0)
    parser.add_argument("--duration-max", type=float, default=600.0)
    parser.add_argument("--max-results", type=int, default=8)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--no-download", action="store_true", help="search and filter only; do not fetch previews")
    args = parser.parse_args()

    if args.query is not None and args.terms_file is not None:
        emit({"status": "invalid", "errors": [{"field": "query",
              "rule": "exactly one of --query or --terms-file is required"}]})
        return 2
    queries: list[str] = []
    if args.terms_file is not None:
        records, filters, errors = load_terms_file(args.terms_file)
        if errors:
            emit({"status": "invalid", "errors": errors})
            return 2
        queries = [str(record.get("term") or "").strip() for record in records]
        queries = [query for query in queries if query]
        if not queries:
            emit({"status": "invalid", "errors": [{"field": "termsFile", "error": "no usable term values"}]})
            return 2
        if filters.get("durationMinSec"):
            args.duration_min = max(args.duration_min, float(filters["durationMinSec"]))
    elif args.query:
        queries = [args.query]
    if not queries and args.tags is None and args.similar_to is None:
        emit({"status": "invalid", "errors": [{"field": "query", "rule": "need --query, --terms-file, --tags or --similar-to"}]})
        return 2
    token = (os.environ.get("MUSIC_EXPERT_FREESOUND_TOKEN") or os.environ.get("P0C_FREESOUND_TOKEN") or "").strip()
    if not token:
        emit({"status": "blocked", "blockers": [{"type": "missing_token",
              "detail": "MUSIC_EXPERT_FREESOUND_TOKEN (or the legacy P0C_FREESOUND_TOKEN) is unset; register a free Freesound API token. Silent fallback to unlicensed sources is forbidden (sourcing-contract)."}]})
        return 2
    if not args.no_download and shutil.which("ffmpeg") is None:
        emit({"status": "blocked", "blockers": [{"type": "missing_toolchain", "detail": "ffmpeg required for the decode probe of downloads"}]})
        return 2

    # Issue 002-③: the duration floor starts as a hard filter; when it starves the pool
    # (live 002: 42/42 rejected for a 3–10 min target) we run ONE relaxed pass and keep
    # undersized candidates visibly marked `durationShortfall`. Loop/splice/relax stays a
    # user decision on the G1 card — never silent padding.
    RELAXED_MIN = 15.0
    results, blockers = [], []
    duration_mode = "hard"

    # Live 2026-09-22 (验收003-⑦): page_size fetches 3x headroom so post-filter keeps can
    # still reach the per-term cap -- but the cap itself must actually truncate. Before this
    # fix, every API result was downloaded (4 terms x 24 = 62 kept live), quietly multiplying
    # the user-visible "search the top few per term" contract.
    hard_stats: list[dict] = []
    kept_per_query: dict[str, int] = {}

    def search_pass(min_duration: float, stats_bucket: list):
        pass_results, pass_blockers = [], []
        for query in queries:
            params = {"fields": SEARCH_FIELDS, "page_size": max(args.max_results * 3, args.max_results),
                      "min_duration": min_duration, "max_duration": args.duration_max}
            if query:
                params["query"] = query
            if args.tags:
                params["filter"] = " ".join(f'tag:"{tag.strip()}"' for tag in args.tags.split(",") if tag.strip())
            payload, error = api_get(token, "/search/text/", params)
            if payload is None:
                pass_blockers.append({"query": query, **error})
                continue
            returned = payload.get("results", [])
            stats_bucket.append({"query": query, "returned": len(returned)})
            pass_results.extend((query, item) for item in returned)
        return pass_results, pass_blockers

    def dedupe(pairs):
        seen_ids, unique = set(), []
        for query, item in pairs:
            sound_id = item.get("id")
            if sound_id in seen_ids:
                continue
            seen_ids.add(sound_id)
            unique.append((query, item))
        return unique

    text_search = args.similar_to is None
    if not text_search:
        payload, error = api_get(token, f"/sounds/{args.similar_to}/similar/", {"page_size": args.max_results, "fields": SEARCH_FIELDS})
        if payload is None:
            emit({"status": "blocked", "blockers": [error]})
            return 2
        results = [(None, item) for item in payload.get("results", [])]
    else:
        results, blockers = search_pass(args.duration_min, hard_stats)
        if blockers and len(blockers) == len(queries):
            emit({"status": "blocked", "blockers": blockers})
            return 2
    results = dedupe(results)
    candidates_dir = args.output_dir / "candidates"
    candidates = []
    excluded = []

    def collect(pairs, shortfall_floor=None):
      for query, item in pairs:
        if query is not None and kept_per_query.get(query, 0) >= args.max_results:
            continue  # per-term cap: this query already contributed its share
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
            # Live 2026-09-17: search results no longer carry urls.page — the
            # canonical short URL /s/<id>/ is derived instead (verified redirect target).
            "sourceUrl": (item.get("urls") or {}).get("page") or f"https://freesound.org/s/{item.get('id')}/",
            "license": item.get("license"),
            "licenseType": verdict["licenseType"],
            "attributionRequired": verdict["attributionRequired"],
            "attributionText": item.get("attribution") or (
                f"\"{item.get('name')}\" by {item.get('username')} ({item.get('license')})"
                if verdict["attributionRequired"] else None),
            "durationSecProbe": item.get("duration"),
            "tags": (item.get("tags") or [])[:12],
            "styleTags": music_tags.normalize_tag_list(item.get("tags") or []),
            "retrievedAt": now(),
            "distributionBoundary": "internal_test",
            "decodeProbe": {"status": "not_run", "engine": "ffmpeg"},
            "analysisRef": None,
        }
        if shortfall_floor is not None and isinstance(item.get("duration"), (int, float)) and item["duration"] < shortfall_floor:
            record["durationShortfall"] = {"requiredMinSec": shortfall_floor, "actualSec": item["duration"],
                                           "note": "短于目标时长：进卡如实标注，循环/拼接/放宽由用户在卡片上决定（002-③），不得静默凑时长"}
        if not args.no_download:
            # Live 2026-09-17: the API renamed preview keys to hyphen form
            # (preview-hq-mp3); accept both spellings so old and new responses work.
            previews = item.get("previews") or {}
            preview = (previews.get("preview_mp3") or previews.get("preview_lq_mp3")
                       or previews.get("preview-hq-mp3") or previews.get("preview-lq-mp3"))
            if not preview:
                excluded.append({"freesoundId": record["freesoundId"], "name": record["title"], "reason": "no preview url in response"})
                continue
            candidates_dir.mkdir(parents=True, exist_ok=True)
            target = candidates_dir / f"freesound-{record['freesoundId']}-preview.mp3"
            # 验收003-①: long searches must show incremental life; stderr keeps the
            # stdout JSON contract clean.
            print(f"[{len(candidates) + len(excluded) + 1}] {query or 'similar'} -> {record['freesoundId']} {record['title']}",
                  file=sys.stderr, flush=True)
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
        if query is not None:
            kept_per_query[query] = kept_per_query.get(query, 0) + 1

    collect(results)
    if text_search and not candidates and args.duration_min > RELAXED_MIN:
        relaxed_stats: list[dict] = []
        relaxed_results, relaxed_blockers = search_pass(RELAXED_MIN, relaxed_stats)
        blockers.extend(relaxed_blockers)
        hard_stats.extend(relaxed_stats)
        seen_ids = {item.get("id") for _query, item in results}
        collect([(query, item) for query, item in dedupe(relaxed_results) if item.get("id") not in seen_ids],
                shortfall_floor=args.duration_min)
        if candidates:
            duration_mode = "soft-fallback"

    kept = [c for c in candidates if c["decodeProbe"]["status"] != "failed"]
    manifest_path = args.output_dir / f"BGM-候选清单-freesound-{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({
        "schemaVersion": "0.1", "purpose": "bgm_candidate_pool", "source": "freesound",
        "query": {"text": args.query, "tags": args.tags, "similarTo": args.similar_to,
                  "termsFile": str(args.terms_file) if args.terms_file else None, "terms": queries or None},
        "partialBlockers": blockers,
        "durationFilter": {"mode": duration_mode, "requestedMinSec": args.duration_min,
                           "appliedMinSec": (RELAXED_MIN if duration_mode == "soft-fallback" else args.duration_min),
                           "maxSec": args.duration_max},
        "retrievedAt": now(), "candidates": kept, "excluded": excluded,
        "perQuery": [{"query": s["query"], "returned": s["returned"], "cap": args.max_results,
                      "kept": kept_per_query.get(s["query"], 0)} for s in hard_stats],
        "sufficiency": {"count": len(kept), "minimumExpected": 3},
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    emit({"status": "completed", "manifest": str(manifest_path), "candidates": len(kept), "excluded": len(excluded),
          "downloaded": not args.no_download})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
