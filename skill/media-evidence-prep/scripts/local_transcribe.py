#!/usr/bin/env python3
"""Create a timestamped local transcription without uploading media.

Errors are emitted as structured JSON on stdout so downstream agents can
parse them. Exit codes: 0 success, 2 invalid input or blocked precondition,
1 unexpected transcription failure.
"""

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys


def emit(payload: dict) -> None:
    # ensure_ascii keeps stdout console-encoding safe on Windows (GBK consoles).
    print(json.dumps(payload, ensure_ascii=True))


def configure_offline_runtime() -> None:
    """Load the controlled Faster-Whisper package when it is not on Python's default path."""
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
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def registered_asset_id(source_pack: Path | None, input_path: Path, input_hash: str) -> str:
    if source_pack is None:
        return f"unregistered:{input_path.name}"
    manifest_path = source_pack / "material-pack.json"
    if not manifest_path.is_file():
        return f"unregistered:{input_path.name}"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        relative_path = input_path.resolve().relative_to(source_pack.resolve()).as_posix()
        for asset in manifest.get("sourceAssets", []):
            if asset.get("relativePath") == relative_path and str(asset.get("sha256", "")).upper() == input_hash:
                return str(asset["assetId"])
    except (OSError, ValueError, json.JSONDecodeError, KeyError):
        pass
    return f"unregistered:{input_path.name}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Local Faster-Whisper transcription")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default="small")
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--language", default="zh")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--source-pack", type=Path, default=None, help="Material pack root; output must stay outside it")
    args = parser.parse_args()

    if not args.input.is_file():
        emit({"status": "invalid", "errors": [{"field": "input", "rule": "file not found", "detail": str(args.input)}]})
        return 2
    if not args.model_dir.is_dir():
        emit({"status": "blocked", "blockers": [{"type": "missing_model_dir", "detail": str(args.model_dir)}]})
        return 2
    if args.source_pack is not None:
        pack = args.source_pack.resolve()
        output = args.output.resolve()
        if pack == output.parent or pack in output.parents:
            emit({"status": "blocked", "blockers": [{"type": "output_inside_material_pack", "detail": f"{output} is inside {pack}"}]})
            return 2

    input_hash = sha256(args.input)
    cache_key = {
        "assetId": registered_asset_id(args.source_pack, args.input, input_hash),
        "sha256": input_hash,
        "language": args.language,
        "model": args.model,
        "device": args.device,
        "computeType": args.compute_type,
        "runtimeVersion": "local-transcribe-script-v0.2",
    }
    if args.output.is_file():
        try:
            existing = json.loads(args.output.read_text(encoding="utf-8"))
            if existing.get("cacheKey") == cache_key:
                emit({"status": "reused", "segments": len(existing.get("segments", [])), "output": str(args.output)})
                return 0
        except (OSError, json.JSONDecodeError):
            pass

    model_name_or_path = resolve_cached_model(args.model, args.model_dir)
    if model_name_or_path is None:
        emit(
            {
                "status": "blocked",
                "blockers": [
                    {
                        "type": "missing_cached_model",
                        "detail": (
                            f"No local Faster-Whisper model for '{args.model}' under {args.model_dir}. "
                            "A controlled toolchain administrator must provision it before this offline run."
                        ),
                    }
                ],
            }
        )
        return 2

    configure_offline_runtime()
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        emit({"status": "blocked", "blockers": [{"type": "missing_dependency", "detail": "faster_whisper is not installed; run `python -m pip install faster-whisper` first"}]})
        return 2

    try:
        model = WhisperModel(
            model_name_or_path,
            device=args.device,
            compute_type=args.compute_type,
            download_root=str(args.model_dir),
        )
        segments, info = model.transcribe(
            str(args.input),
            language=args.language,
            beam_size=5,
            vad_filter=True,
            word_timestamps=True,
        )
        result_segments = []
        for index, segment in enumerate(segments, start=1):
            result_segments.append(
                {
                    "segmentId": f"tr-{index:04d}",
                    "startMs": round(segment.start * 1000),
                    "endMs": round(segment.end * 1000),
                    "text": segment.text.strip(),
                    "words": [
                        {
                            "startMs": round(word.start * 1000),
                            "endMs": round(word.end * 1000),
                            "text": word.word,
                            "probability": word.probability,
                        }
                        for word in (segment.words or [])
                    ],
                }
            )
        result = {
            "schemaVersion": "0.1",
            "producer": "local-faster-whisper",
            "model": args.model,
            "cacheKey": cache_key,
            "language": info.language,
            "languageProbability": info.language_probability,
            "input": str(args.input),
            "segments": result_segments,
            "status": "draft_requires_human_fact_review",
            "finishedAt": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        }
    except Exception as error:  # surface model/runtime failures as structured JSON
        emit({"status": "failed", "error": str(error)})
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    emit({"status": "completed", "segments": len(result_segments), "output": str(args.output)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
