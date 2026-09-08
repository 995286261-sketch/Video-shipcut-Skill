#!/usr/bin/env python3
"""Create auditable local transcription timings for an approved G3 narration audio file.

Mirrors the G2 controlled-runtime pattern (issue 014): the Faster-Whisper package is
loaded from P0C_FASTER_WHISPER_HOME, model snapshots are resolved only from an explicit
--model-dir or P0C_FASTER_WHISPER_MODEL_HOME, and every precondition failure is a
structured JSON block instead of an import traceback.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True))


def configure_offline_runtime() -> None:
    runtime_home = os.environ.get("P0C_FASTER_WHISPER_HOME")
    if runtime_home and Path(runtime_home).is_dir() and runtime_home not in sys.path:
        sys.path.insert(0, runtime_home)


def resolve_cached_model(model: str, model_dir: Path) -> str | None:
    """Return an existing model snapshot only; never hand a model name to the downloader."""
    candidate = Path(model)
    if candidate.is_dir():
        return str(candidate)
    snapshots = model_dir / f"models--Systran--faster-whisper-{model}" / "snapshots"
    if snapshots.is_dir():
        available = sorted(path for path in snapshots.iterdir() if path.is_dir())
        if len(available) == 1:
            return str(available[0])
    return None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default="small")
    parser.add_argument("--model-dir", type=Path, default=None, help="Defaults to P0C_FASTER_WHISPER_MODEL_HOME")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--initial-prompt", default="")
    args = parser.parse_args()

    if not args.audio.is_file():
        emit({"status": "invalid", "errors": [{"field": "audio", "rule": "file not found", "detail": str(args.audio)}]})
        return 2
    model_dir = args.model_dir or Path(os.environ.get("P0C_FASTER_WHISPER_MODEL_HOME", ""))
    if not str(model_dir) or not model_dir.is_dir():
        emit({"status": "blocked", "blockers": [{"type": "missing_model_dir", "detail": f"--model-dir or P0C_FASTER_WHISPER_MODEL_HOME must point to a local model cache directory (got {model_dir or 'unset'})"}]})
        return 2

    cache_key = {
        "sha256": sha256(args.audio),
        "language": args.language,
        "model": args.model,
        "device": args.device,
        "computeType": args.compute_type,
        "runtimeVersion": "g3-align-narration-v0.2",
    }
    if args.output.is_file():
        try:
            existing = json.loads(args.output.read_text(encoding="utf-8"))
            if existing.get("cacheKey") == cache_key:
                emit({"status": "reused", "segments": len(existing.get("segments", [])), "output": str(args.output)})
                return 0
        except (OSError, json.JSONDecodeError):
            pass

    model_name_or_path = resolve_cached_model(args.model, model_dir)
    if model_name_or_path is None:
        emit({"status": "blocked", "blockers": [{"type": "missing_cached_model", "detail": f"No local Faster-Whisper model for '{args.model}' under {model_dir}. Provision it through the controlled toolchain; downloading here is forbidden."}]})
        return 2

    configure_offline_runtime()
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        emit({"status": "blocked", "blockers": [{"type": "missing_dependency", "detail": "faster_whisper is unavailable; set P0C_FASTER_WHISPER_HOME to the controlled runtime site-packages or install faster-whisper"}]})
        return 2

    try:
        model = WhisperModel(model_name_or_path, device=args.device, compute_type=args.compute_type, download_root=str(model_dir))
        segments, info = model.transcribe(
            str(args.audio), language=args.language, beam_size=5, vad_filter=True,
            word_timestamps=True, initial_prompt=args.initial_prompt or None,
        )
        output_segments = []
        for item in segments:
            output_segments.append({
                "startMs": round(item.start * 1000),
                "endMs": round(item.end * 1000),
                "text": item.text.strip(),
                "words": [{"startMs": round(word.start * 1000), "endMs": round(word.end * 1000), "text": word.word} for word in (item.words or [])],
            })
    except Exception as error:  # surface model/runtime failures as structured JSON
        emit({"status": "failed", "error": str(error)})
        return 1

    payload = {
        "schemaVersion": "0.1", "node": "G3", "purpose": "approved_narration_audio_alignment",
        "audioRef": str(args.audio), "engine": "faster-whisper", "model": args.model,
        "cacheKey": cache_key,
        "language": info.language, "languageProbability": info.language_probability,
        "segments": output_segments,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    emit({"status": "completed", "segments": len(output_segments), "language": info.language, "output": str(args.output)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
