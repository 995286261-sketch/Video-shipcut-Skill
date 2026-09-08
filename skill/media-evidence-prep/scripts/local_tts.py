#!/usr/bin/env python3
"""Synthesize sentence-level narration with the local macOS `say` engine and produce a
measured-duration table (issues 015/017), with an optional ASR read-back self-check
(issue 011).

Key contract points:
- The requested voice must exist in `say -v ?`; macOS otherwise silently falls back to
  an English voice that cannot read Chinese, so a missing voice is a hard block.
- `say -o out.wav` fails on this macOS with a "fmt?" error; audio is written as raw
  LEI16@22050 CAF first and converted to wav with FFmpeg (issue 015).
- Voice cards must register durations measured from the synthesized audio, not text
  estimates that were ~40% off in the baseline (issue 017).
- System `say` output is preview-tier only; production narration requires neural TTS
  or a human voice (issue 028).
- `--verify-asr` transcribes each sentence with the controlled Faster-Whisper runtime
  and compares normalized text; a silent fallback voice is detected and blocked.

Exit codes match the G2 tooling convention: 0 ok, 2 invalid/blocked, 1 runtime failure.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True))


def configure_offline_runtime() -> None:
    runtime_home = os.environ.get("P0C_FASTER_WHISPER_HOME")
    if runtime_home and Path(runtime_home).is_dir() and runtime_home not in sys.path:
        sys.path.insert(0, runtime_home)


def probe_duration_ms(path: Path) -> int:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
    )
    return round(float(json.loads(result.stdout)["format"]["duration"]) * 1000)


def available_voices() -> set[str]:
    result = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
    names = set()
    for line in result.stdout.splitlines():
        match = re.match(r"^(\S.*?)\s{2,}([A-Za-z]{2}[-_][A-Za-z]{2})", line.strip())
        if match:
            names.add(match.group(1).strip())
    return names


def normalize_text(value: str) -> str:
    stripped = unicodedata.normalize("NFKC", value)
    return "".join(ch for ch in stripped if ch.isalnum())


def verify_with_asr(items: list[dict], args) -> dict | None:
    """Return a verification payload; raise ValueError (structured by main) when blocked."""
    model_dir = args.model_dir or Path(os.environ.get("P0C_FASTER_WHISPER_MODEL_HOME", ""))
    if not str(model_dir) or not model_dir.is_dir():
        emit({"status": "blocked", "blockers": [{"type": "missing_model_dir", "detail": "--verify-asr requires --model-dir or P0C_FASTER_WHISPER_MODEL_HOME"}]})
        raise SystemExit(2)
    snapshots = model_dir / f"models--Systran--faster-whisper-{args.model}" / "snapshots"
    available = sorted(path for path in snapshots.iterdir() if path.is_dir()) if snapshots.is_dir() else []
    if len(available) != 1:
        emit({"status": "blocked", "blockers": [{"type": "missing_cached_model", "detail": f"No single cached Faster-Whisper snapshot for '{args.model}' under {model_dir}"}]})
        raise SystemExit(2)
    configure_offline_runtime()
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        emit({"status": "blocked", "blockers": [{"type": "missing_dependency", "detail": "faster_whisper unavailable; set P0C_FASTER_WHISPER_HOME to the controlled runtime"}]})
        raise SystemExit(2)
    model = WhisperModel(str(available[0]), device="cpu", compute_type="int8", download_root=str(model_dir))
    results = []
    failures = []
    # Without the domain vocabulary whisper mishears proper nouns (刹帝利 -> 沙地力)
    # and the readback check would blame the voice for an ASR error.
    initial_prompt = args.asr_initial_prompt.strip() or None
    for item in items:
        segments, _info = model.transcribe(item["file"], language="zh", beam_size=5, initial_prompt=initial_prompt)
        heard = normalize_text("".join(segment.text for segment in segments))
        expected = normalize_text(item["text"])
        ratio = difflib.SequenceMatcher(None, expected, heard).ratio() if expected else 0.0
        results.append({"sentenceId": item["sentenceId"], "expected": expected, "heard": heard, "similarity": round(ratio, 3)})
        if ratio < args.asr_min_ratio:
            failures.append(item["sentenceId"])
    if failures:
        emit({
            "status": "blocked",
            "blockers": [{"type": "asr_readback_mismatch", "detail": f"voice may have silently fallen back or misread; sentences below {args.asr_min_ratio}: {', '.join(failures)}"}],
            "verification": {"perSentence": results},
        })
        raise SystemExit(2)
    return {"engine": "faster-whisper", "model": args.model, "minRatio": args.asr_min_ratio, "initialPrompt": args.asr_initial_prompt or None, "perSentence": results}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sentences", required=True, type=Path, help="JSON array: [{sentenceId, text}]")
    parser.add_argument("--voice", required=True, help="macOS voice name, e.g. Tingting")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--rate", type=int, default=0, help="say words-per-minute override; 0 keeps the voice default")
    parser.add_argument("--verify-asr", action="store_true", help="transcribe the synthesis back and compare with the source text (issue 011)")
    parser.add_argument("--model", default="small")
    parser.add_argument("--model-dir", type=Path, default=None)
    parser.add_argument("--asr-min-ratio", type=float, default=0.6)
    parser.add_argument("--asr-initial-prompt", default="", help="domain vocabulary (proper nouns) so readback does not mishear names")
    args = parser.parse_args()

    if shutil.which("say") is None:
        emit({"status": "blocked", "blockers": [{"type": "missing_tts_provider", "detail": "macOS `say` unavailable; use authorized neural TTS (e.g. Bailian CosyVoice) or human narration instead"}]})
        return 2
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        emit({"status": "blocked", "blockers": [{"type": "missing_ffmpeg", "detail": "ffmpeg/ffprobe must be on PATH for CAF conversion and duration probing"}]})
        return 2
    try:
        sentences = json.loads(args.sentences.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        emit({"status": "invalid", "errors": [{"field": "sentences", "rule": str(error), "detail": str(args.sentences)}]})
        return 2
    if not isinstance(sentences, list) or not sentences or not all(isinstance(item, dict) and item.get("sentenceId") and isinstance(item.get("text"), str) and item["text"].strip() for item in sentences):
        emit({"status": "invalid", "errors": [{"field": "sentences", "rule": "requires non-empty [{sentenceId,text}]", "detail": str(args.sentences)}]})
        return 2
    ids = [item["sentenceId"] for item in sentences]
    if len(ids) != len(set(ids)):
        emit({"status": "invalid", "errors": [{"field": "sentenceId", "rule": "must be unique", "detail": str(ids)}]})
        return 2

    voices = available_voices()
    if args.voice not in voices:
        # macOS would silently fall back to an English voice that cannot read Chinese (issue 011).
        emit({"status": "blocked", "blockers": [{"type": "missing_voice", "detail": f"'{args.voice}' is not installed; installed voices include: {', '.join(sorted(voices)[:8])}..."}]})
        return 2

    work = args.output_dir / "_say-caf"
    work.mkdir(parents=True, exist_ok=True)
    items: list[dict] = []
    for item in sentences:
        base = str(item["sentenceId"])
        caf = work / f"{base}.caf"
        wav = args.output_dir / f"{base}.wav"
        command = ["say", "-v", args.voice, "--data-format", "LEI16@22050", "-o", str(caf)]
        if args.rate:
            command += ["-r", str(args.rate)]
        command.append(item["text"])
        subprocess.run(command, check=True, capture_output=True)
        if not caf.is_file() or caf.stat().st_size == 0:
            emit({"status": "failed", "error": f"say exited without producing {caf.name}"})
            return 1
        subprocess.run(["ffmpeg", "-y", "-i", str(caf), "-ar", "22050", "-ac", "1", str(wav)], check=True, capture_output=True)
        if not wav.is_file() or wav.stat().st_size == 0:
            emit({"status": "failed", "error": f"ffmpeg exited without producing {wav.name}"})
            return 1
        items.append({"sentenceId": base, "text": item["text"], "file": str(wav), "durationMs": probe_duration_ms(wav)})

    verification = verify_with_asr(items, args) if args.verify_asr else None
    total_ms = sum(item["durationMs"] for item in items)
    manifest = {
        "schemaVersion": "0.1",
        "node": "G2",
        "purpose": "narration_synthesis_measured_durations",
        "provider": "macos_say",
        "voice": args.voice,
        "voiceTier": "preview_only",
        "tierNotice": "macOS system TTS is preview-tier only; production narration requires authorized neural TTS (e.g. Bailian CosyVoice) or a human voice (issue 028).",
        "measuredTotalDurationMs": total_ms,
        "sentences": items,
        "asrVerification": verification,
        "cacheKey": hashlib.sha256(json.dumps({"voice": args.voice, "rate": args.rate, "items": [(item["sentenceId"], item["text"]) for item in items]}, sort_keys=True).encode("utf-8")).hexdigest().upper(),
    }
    manifest_path = args.output_dir / "G2-配音清单-v0.1.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    emit({
        "status": "completed",
        "manifest": str(manifest_path),
        "sentences": len(items),
        "measuredTotalDurationMs": total_ms,
        "voiceTier": "preview_only",
        "asrVerified": verification is not None,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
