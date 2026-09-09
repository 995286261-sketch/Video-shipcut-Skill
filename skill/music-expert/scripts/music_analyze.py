#!/usr/bin/env python3
"""Analyze a music audio track (or the audio track of a reference video) deterministically.

Produces a BGM analysis report: tempo, beats, onsets, energy segments, hit-point table,
measured duration and loudness. Reuses the controlled-runtime pattern (issue 014): the
analysis libraries load only from P0C_MUSIC_RUNTIME_HOME, a missing runtime is a
structured block, never an import traceback. Reuses the cacheKey pattern (issue 031):
re-running on the same bytes returns cache_hit without recomputation. Every produced
file is verified to exist and be non-empty (issue 022). Source media stay read-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCHEMA_VERSION = "0.1"
ANALYSIS_VERSION = "music-expert-analysis-v0.2"
SAMPLE_RATE = 22050


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True))


def fail_invalid(field: str, detail: str) -> int:
    emit({"status": "invalid", "errors": [{"field": field, "rule": "machine precondition", "detail": detail}]})
    return 2


def fail_blocked(reason: str, detail: str) -> int:
    emit({"status": "blocked", "blockers": [{"type": reason, "detail": detail}]})
    return 2


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def probe_media(path: Path) -> tuple[dict | None, str | None]:
    result = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)])
    if result.returncode != 0:
        return None, (result.stderr or "").strip()[:200] or "ffprobe failed"
    try:
        info = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None, "ffprobe returned unparsable json"
    streams = info.get("streams", [])
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    duration = None
    for source in (audio or {}, info.get("format", {})):
        try:
            duration = float(source.get("duration"))
            break
        except (TypeError, ValueError):
            continue
    return {"hasAudio": audio is not None, "hasVideo": video is not None, "durationSecProbe": duration,
            "audioCodec": (audio or {}).get("codec_name"), "channels": (audio or {}).get("channels")}, None


def decode_wav(source: Path, target: Path) -> str | None:
    result = run(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
                  "-c:a", "pcm_s16le", str(target)])
    # Issue 022 rule: never trust the exit code alone; the artifact must exist and be non-empty.
    if result.returncode != 0:
        return (result.stderr or "").strip()[:200] or "ffmpeg decode failed"
    if not target.is_file() or target.stat().st_size == 0:
        return "ffmpeg exited without producing the decoded wav"
    return None


def measure_loudness(path: Path) -> dict:
    result = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-filter:a", "ebur128", "-f", "null", "-"])
    text = (result.stderr or "") + (result.stdout or "")
    loudness = {"integratedLufs": None, "loudnessRangeLu": None, "truePeakDbtp": None}
    # ffmpeg's ebur128 prints an early "I: -70.0" sentinel before the Final Summary at the
    # very end; take the LAST match and reject the silence-floor so recommend.py never
    # treats an unmeasured track as "quiet".
    matches = re.findall(r"I:\s+(-?\d+\.?\d*)\s*LUFS", text)
    if matches:
        value = float(matches[-1])
        loudness["integratedLufs"] = None if value <= -69.9 else value
    matches = re.findall(r"LRA:\s+(-?\d+\.?\d*)\s*LU", text)
    if matches:
        loudness["loudnessRangeLu"] = float(matches[-1])
    matches = re.findall(r"Sample Peak:\s+(-?\d+\.?\d*)\s*dBFS", text)
    if matches:
        loudness["truePeakDbtp"] = float(matches[-1])
    loudness["engine"] = "ffmpeg-ebur128"
    return loudness


def find_cached_report(cache_key: dict, search_dirs: list[Path]) -> Path | None:
    for directory in search_dirs:
        if not directory.is_dir():
            continue
        for candidate in sorted(directory.glob("BGM-分析报告-*.json")):
            try:
                existing = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if existing.get("cacheKey") == cache_key:
                return candidate
    return None


def energy_segments(times, rms_values, min_len_sec: float = 4.0, max_segments: int = 8):
    """Deterministic greedy change-point split of the energy curve (no clustering deps).

    Uses prefix sums of x and x^2 so the sum-of-squared-deviations cost is O(1), keeping
    the divisive scan near O(n) per pass — a long track must analyze in seconds, not the
    minutes an O(n^2)-with-slicing version takes on ~2000-frame curves.
    """
    total = len(rms_values)
    if total < 4:
        return [0, total]
    frames_per_sec = 1.0
    if len(times) > 1 and float(times[1]) > float(times[0]):
        frames_per_sec = 1.0 / (float(times[1]) - float(times[0]))
    min_len = max(2, math.ceil(min_len_sec * frames_per_sec))

    prefix = [0.0] * (total + 1)
    prefix_sq = [0.0] * (total + 1)
    for index, value in enumerate(rms_values):
        prefix[index + 1] = prefix[index] + float(value)
        prefix_sq[index + 1] = prefix_sq[index] + float(value) * float(value)

    def sse(lo: int, hi: int) -> float:
        count = hi - lo
        total_sum = prefix[hi] - prefix[lo]
        return (prefix_sq[hi] - prefix_sq[lo]) - (total_sum * total_sum) / count

    bounds = [(0, total)]
    while len(bounds) < max_segments:
        best = None
        for index, (lo, hi) in enumerate(bounds):
            span = hi - lo
            if span < 2 * min_len:
                continue
            parent = sse(lo, hi)
            for split in range(lo + min_len, hi - min_len + 1):
                reduction = parent - sse(lo, split) - sse(split, hi)
                if best is None or reduction > best[0]:
                    best = (reduction, index, split)
        if best is None or best[0] <= 0:
            break
        reduction, index, split = best
        lo, hi = bounds.pop(index)
        bounds.insert(index, (lo, split))
        bounds.insert(index + 1, (split, hi))
    bounds.sort()
    return [lo for lo, _ in bounds] + [total]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--cache-root", action="append", type=Path, default=[], help="Extra directory to scan for a cacheable report")
    parser.add_argument("--style-brief-out", type=Path, default=None)
    args = parser.parse_args()

    if not args.input.is_file() or args.input.stat().st_size == 0:
        return fail_invalid("input", f"missing or empty media file: {args.input}")
    for tool in ("ffprobe", "ffmpeg"):
        if shutil.which(tool) is None:
            return fail_blocked("missing_toolchain", f"{tool} is not on PATH")

    media, error = probe_media(args.input)
    if media is None:
        return fail_invalid("input", f"unprobeable media: {error}")
    if not media["hasAudio"]:
        return fail_invalid("input", "media has no audio stream; music analysis requires audio")
    media_kind = "video-with-audio" if media["hasVideo"] else "audio"

    source_sha = sha256(args.input)
    cache_key = {"sha256": source_sha, "analysisVersion": ANALYSIS_VERSION, "sampleRate": SAMPLE_RATE,
                 "mediaKind": media_kind}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cached = find_cached_report(cache_key, [args.output_dir, *args.cache_root])
    if cached is not None:
        emit({"status": "cache_hit", "report": str(cached), "cacheKey": cache_key["sha256"][:16], "sourceSha256": source_sha})
        return 0

    configure_runtime()
    runtime_error = runtime_block_reason()
    if runtime_error is not None:
        return fail_blocked("missing_analysis_runtime", runtime_error)

    temporary = Path(tempfile.mkdtemp(prefix="music-expert-"))
    try:
        wav_path = temporary / "decoded.wav"
        decode_error = decode_wav(args.input, wav_path)
        if decode_error is not None:
            return fail_blocked("audio_decode_failed", f"{decode_error}; the file may be a stream-encrypted fake (issue 023 root cause)")
        loudness = measure_loudness(args.input)

        import numpy as np
        import librosa  # noqa: F401  (imported after configure_runtime)

        y, sr = librosa.load(str(wav_path), sr=None, mono=True)
        duration_ms = round(float(len(y)) / sr * 1000)
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        tempo_value = float(np.atleast_1d(tempo)[0])
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)
        onset_times = librosa.onset.onset_detect(y=y, sr=sr, units="time")
        hop = 2048
        rms = librosa.feature.rms(y=y, hop_length=hop)[0]
        rms_times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)
    except Exception as error:  # runtime/model failures are structured, never bare tracebacks
        emit({"status": "failed", "error": str(error)[:300]})
        return 1
    finally:
        shutil.rmtree(temporary, ignore_errors=True)

    boundaries = energy_segments(rms_times, rms)
    segments = []
    for lo_index, hi_index in zip(boundaries, boundaries[1:]):
        part = rms[lo_index:hi_index]
        segments.append({
            "startMs": round(float(rms_times[lo_index]) * 1000),
            "endMs": round(float(rms_times[hi_index - 1]) * 1000) if hi_index <= len(rms_times) else duration_ms,
            "energyMean": round(float(sum(part) / len(part)), 6),
        })
    hit_points = build_hit_points(beat_times, onset_times)

    report = {
        "schemaVersion": SCHEMA_VERSION,
        "skill": "music-expert",
        "purpose": "bgm_music_analysis",
        "analysisVersion": ANALYSIS_VERSION,
        "cacheKey": cache_key,
        "source": {"path": str(args.input.resolve()), "sha256": source_sha, "mediaKind": media_kind,
                   "audioCodecProbe": media["audioCodec"], "channelsProbe": media["channels"],
                   "durationSecProbe": media["durationSecProbe"], "decodedDurationMs": duration_ms},
        "tempoBpm": round(tempo_value, 2),
        "beatsMs": [round(float(t) * 1000) for t in beat_times],
        "onsetsMs": [round(float(t) * 1000) for t in onset_times],
        "hitPoints": hit_points,
        "energySegments": segments,
        "energyCurve": [{"tMs": round(float(t) * 1000), "rms": round(float(v), 6)} for t, v in zip(rms_times[::4], rms[::4])],
        "loudness": loudness,
        "timing": {"durationMsSource": "decoded samples", "unit": "integer milliseconds; human display timecodes are derived downstream"},
    }
    report_path = args.output_dir / f"BGM-分析报告-{args.input.stem}-{source_sha[:8]}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not report_path.is_file() or report_path.stat().st_size == 0:
        return fail_blocked("report_write_failed", f"analysis report was not written to {report_path}")

    if args.style_brief_out is not None:
        brief = build_style_brief(report, args.input)
        args.style_brief_out.parent.mkdir(parents=True, exist_ok=True)
        args.style_brief_out.write_text(json.dumps(brief, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if not args.style_brief_out.is_file() or args.style_brief_out.stat().st_size == 0:
            return fail_blocked("style_brief_write_failed", str(args.style_brief_out))

    emit({"status": "completed", "report": str(report_path), "tempoBpm": report["tempoBpm"],
          "segments": len(segments), "hitPoints": len(hit_points), "durationMs": duration_ms,
          "styleBrief": str(args.style_brief_out) if args.style_brief_out else None})
    return 0


def runtime_home_candidates() -> list[str]:
    # Generic name first so the skill stays portable; P0C_* kept as a legacy alias.
    return [value for value in (os.environ.get("MUSIC_EXPERT_RUNTIME_HOME"), os.environ.get("P0C_MUSIC_RUNTIME_HOME")) if value]


def configure_runtime() -> None:
    for runtime_home in runtime_home_candidates():
        if Path(runtime_home).is_dir() and runtime_home not in sys.path:
            sys.path.insert(0, runtime_home)


def runtime_block_reason() -> str | None:
    try:
        import numpy  # noqa: F401
        import librosa  # noqa: F401
    except ImportError:
        return ("numpy/librosa are unavailable; set MUSIC_EXPERT_RUNTIME_HOME (or the legacy "
                "P0C_MUSIC_RUNTIME_HOME) to the controlled music-expert runtime "
                "(see references/music-analysis-contract.md). Downloading packages at run time is forbidden.")
    return None


def build_hit_points(beat_times, onset_times) -> list[dict]:
    """卡点表: every beat is an anchor; onsets away from beats are accents (±120ms grid)."""
    beats_ms = [round(float(t) * 1000) for t in beat_times]
    onsets_ms = [round(float(t) * 1000) for t in onset_times]
    points = [{"tMs": b, "kind": "beat"} for b in beats_ms]
    for onset in onsets_ms:
        if all(abs(onset - b) > 120 for b in beats_ms):
            points.append({"tMs": onset, "kind": "accent"})
    points.sort(key=lambda item: item["tMs"])
    return points


def build_style_brief(report: dict, source: Path) -> dict:
    tempo = report["tempoBpm"]
    curve = [point["rms"] for point in report["energyCurve"]]
    peak = max(curve) if curve else 0.0
    return {
        "schemaVersion": SCHEMA_VERSION,
        "purpose": "reference_music_style_brief",
        "sourceTitle": source.stem,
        "sourceReport": report["source"]["sha256"],
        "bpm": tempo,
        "bpmRange": [round(tempo * 0.9, 1), round(tempo * 1.1, 1)] if tempo > 0 else None,
        "durationMs": report["source"]["decodedDurationMs"],
        "energyShape": [round(v / peak, 3) if peak else 0.0 for v in curve],
        "segmentCount": len(report["energySegments"]),
        "usage": "检索与推荐输入；suggestedQueryTerms 由 Agent 依情绪/风格补写，本文件只承载机器事实",
        "suggestedQueryTerms": [],
    }


if __name__ == "__main__":
    raise SystemExit(main())
