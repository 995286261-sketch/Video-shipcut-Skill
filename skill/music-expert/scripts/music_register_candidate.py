#!/usr/bin/env python3
"""Register a user-held or manually downloaded audio file as a BGM candidate.

This covers the manual track of the dual-track sourcing model: libraries with no usable
API (Pixabay/Mixkit music) where a HUMAN legally downloads the file and supplies the
license evidence. The script never downloads or copies anything by itself and never
modifies the source file (source-media read-only rule). Every candidate record keeps
SHA-256, byte size, an ffmpeg decode probe (issue 023) and explicit license evidence.
Default distribution boundary stays internal_test; only a human review may raise it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import music_tags

SCHEMA_VERSION = "0.1"
LICENSE_TYPES = {"cc0", "cc-by", "cc-by-sa", "public-domain", "owned", "cleared-for-project", "unknown"}


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


def safe_title_slug(title: str, limit: int = 40) -> str:
    """Filesystem-safe, deterministic title slug: separators collapse to '-',
    and over-long titles are cut at the last word boundary (never mid-word)."""
    cleaned = re.sub(r"-{2,}", "-", re.sub(r"[^\w一-鿿-]+", "-", title)).strip("-") or "untitled"
    if len(cleaned) <= limit:
        return cleaned
    head = cleaned[:limit + 1]
    cut = max(head.rfind("-"), head.rfind("_"))
    return head[:cut] if cut > limit // 2 else head[:limit].rsplit("-", 1)[0] or head[:limit]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True, type=Path, help="existing local audio file; read-only here")
    parser.add_argument("--title", required=True)
    parser.add_argument("--license-type", required=True, choices=sorted(LICENSE_TYPES))
    parser.add_argument("--license-evidence", required=True, help="URL or project file path holding the license terms (e.g. the download page / license screenshot)")
    parser.add_argument("--source-url", default=None, help="where the file came from")
    parser.add_argument("--attribution", default=None, help="exact attribution text the license requires, or 'none'")
    parser.add_argument("--tags", default=None, help="comma-separated controlled-vocabulary tags (references/tag-vocabulary.md)")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    if not args.audio.is_file() or args.audio.stat().st_size == 0:
        emit({"status": "invalid", "errors": [{"field": "audio", "rule": "file must exist and be non-empty", "detail": str(args.audio)}]})
        return 2
    if args.license_type != "unknown" and not args.license_evidence.strip():
        emit({"status": "invalid", "errors": [{"field": "licenseEvidence", "rule": "a claimed license requires evidence", "detail": "provide a URL or file path"}]})
        return 2
    style_tags: list[str] = []
    if args.tags:
        style_tags, unknown = music_tags.strict_tag_list([tag for tag in args.tags.split(",") if tag.strip()])
        if unknown:
            emit({"status": "invalid", "errors": [{"field": "tags", "rule": "every tag must come from the controlled vocabulary",
                  "detail": f"unknown tags: {', '.join(unknown)}; accepted — {music_tags.accepted_tags_text()}"}]})
            return 2
    if shutil.which("ffmpeg") is None:
        emit({"status": "blocked", "blockers": [{"type": "missing_toolchain", "detail": "ffmpeg required for the audio decode probe (issue 023)"}]})
        return 2

    probe = subprocess.run(["ffmpeg", "-v", "error", "-i", str(args.audio), "-f", "null", "-"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
    record = {
        "schemaVersion": SCHEMA_VERSION,
        "skill": "music-expert",
        "provenance": "manual_registration",
        "title": args.title,
        "audioPath": str(args.audio.resolve()),
        "sha256": sha256(args.audio),
        "byteSize": args.audio.stat().st_size,
        "fileExtension": args.audio.suffix.lower(),
        "sourceUrl": args.source_url,
        "license": args.license_type,
        "licenseEvidence": args.license_evidence,
        "attribution": args.attribution or "none",
        "styleTags": style_tags,
        "retrievedAt": now(),
        "distributionBoundary": "internal_test",
        "decodeProbe": {"status": "passed" if probe.returncode == 0 else "failed", "engine": "ffmpeg"},
        "analysisRef": None,
    }
    if probe.returncode != 0:
        record["decodeProbe"]["error"] = (probe.stderr or "").strip()[:200] or "ffmpeg could not decode this file"
        emit({"status": "blocked", "blockers": [{"type": "audio_decode_probe_failed",
              "detail": "音频无法完整解码（可能是流媒体加密缓存改名的假文件）；请重新获取有效音频文件 (issue 023)"}],
              "candidate": record})
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output_dir / f"BGM-候选登记-{safe_title_slug(args.title)}-{record['sha256'][:8]}.json"
    manifest_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not manifest_path.is_file() or manifest_path.stat().st_size == 0:
        emit({"status": "blocked", "blockers": [{"type": "manifest_write_failed", "detail": str(manifest_path)}]})
        return 1
    emit({"status": "completed", "candidate": str(manifest_path), "sha256": record["sha256"],
          "decodeProbe": record["decodeProbe"]["status"]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
