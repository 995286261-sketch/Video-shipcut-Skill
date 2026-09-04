#!/usr/bin/env python3
"""Create auditable local transcription timings for an approved G3 narration audio file."""

import argparse
import json
from pathlib import Path

from faster_whisper import WhisperModel


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default="small")
    parser.add_argument("--initial-prompt", default="")
    args = parser.parse_args()
    if not args.audio.is_file():
        raise FileNotFoundError(f"audio not found: {args.audio}")
    model = WhisperModel(args.model, device="cpu", compute_type="int8", local_files_only=True)
    segments, info = model.transcribe(
        str(args.audio), language="zh", beam_size=5, vad_filter=True,
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
    payload = {
        "schemaVersion": "0.1", "node": "G3", "purpose": "approved_narration_audio_alignment",
        "audioRef": str(args.audio), "engine": "faster-whisper", "model": args.model,
        "language": info.language, "languageProbability": info.language_probability,
        "segments": output_segments,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "segments": len(output_segments), "language": info.language}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
