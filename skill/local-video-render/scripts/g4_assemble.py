#!/usr/bin/env python3
"""Assemble the flattened G4 master from the editable manifest: concat, audio mix,
subtitle burn-in, and cover compositing. This is the only sanctioned entry point for
final assembly; hand-stitched ffmpeg command lines are not reproducible (issue 027).

The command always checks that every ffmpeg output exists and is non-empty (issue 022
rule reused here), and writes an auditable assembly record next to the master.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def fail(message: str) -> None:
    raise ValueError(message)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def require_file(path: Path, label: str) -> Path:
    if not path.is_file() or path.stat().st_size == 0:
        fail(f"{label} is missing or empty: {path}")
    return path


def probe_duration_ms(path: Path) -> int:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
    )
    return round(float(json.loads(result.stdout)["format"]["duration"]) * 1000)


def run_checked(command: list[str], output: Path, label: str, cwd: Path | None = None) -> None:
    subprocess.run(command, check=True, capture_output=True, cwd=cwd)
    if not output.is_file() or output.stat().st_size == 0:
        fail(f"ffmpeg exited without producing {label}: {output}")


def subtitles_filter_available() -> bool:
    result = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return result.returncode == 0 and " subtitles " in result.stdout


def concat_line(path: Path) -> str:
    return "file '" + str(path).replace("'", "'\\''") + "'"


def audio_filter_chain(narration_index: int, bgm_index: int | None, bgm_gain_db: float, duck: bool) -> str:
    narration = f"[{narration_index}:a]"
    if bgm_index is None:
        return f"{narration}anull[aud]"
    bgm = f"[{bgm_index}:a]volume={bgm_gain_db}dB[bed]"
    if duck:
        # The narration feeds the compressor sidechain and the final mix, so split it once.
        return f"{bgm};{narration}asplit=2[nmain][nside];[bed][nside]sidechaincompress=threshold=0.05:ratio=8:attack=20:release=400[ducked];[ducked][nmain]amix=inputs=2:duration=longest:normalize=0[aud]"
    return f"{bgm};[bed]{narration}amix=inputs=2:duration=longest:normalize=0[aud]"


def build_assemble_command(list_file: Path, inputs: list[Path], filter_complex: str, output: Path, fps: int, duration_s: float) -> list[str]:
    command = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file)]
    for index, path in enumerate(inputs):
        loop = ["-stream_loop", "-1"] if path.suffix.lower() in {".mp3", ".m4a", ".wav", ".ogg", ".flac", ".aac"} and index > 0 else []
        command += [*loop, "-i", str(path)]
    command += [
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "[aud]",
        "-t", str(duration_s),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(output),
    ]
    return command


def render_cover(contract_path: Path, work: Path) -> Path:
    contract = load(contract_path)
    image = require_file(Path(str(contract.get("imagePath") or "")), "cover image")
    font = require_file(Path(str(contract.get("fontFile") or "")), "cover font")
    title = str(contract.get("title") or "").strip()
    if not title:
        fail("cover contract requires title")
    raw_output = str(contract.get("output") or "").strip()
    if not raw_output:
        fail("cover contract requires output")
    output = Path(raw_output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    text_file = work / "cover-title.txt"
    text_file.write_text(title, encoding="utf-8")
    fontsize = int(contract.get("fontsize", 64))
    margin_y = int(contract.get("marginY", fontsize))
    color = str(contract.get("fontcolor", "white"))
    # Colons inside filter arguments must be escaped for the filtergraph parser.
    font_arg = str(font.resolve()).replace(":", "\\:")
    text_arg = str(text_file.resolve()).replace(":", "\\:")
    draw = (
        f"drawtext=fontfile={font_arg}:textfile={text_arg}"
        f":fontsize={fontsize}:fontcolor={color}:borderw=2:bordercolor=black@0.6"
        ":x=(w-text_w)/2:y=h-text_h-" + str(margin_y)
    )
    run_checked(["ffmpeg", "-y", "-i", str(image), "-vf", draw, "-frames:v", "1", "-q:v", "2", str(output)], output, "cover image")
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--segments-dir", required=True, type=Path)
    parser.add_argument("--narration-audio", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--subtitle-ass", type=Path)
    parser.add_argument("--bgm-audio", type=Path)
    parser.add_argument("--bgm-gain-db", type=float, default=-18.0)
    parser.add_argument("--bgm-duck", action="store_true", help="duck the BGM bed with the narration as sidechain")
    parser.add_argument("--cover", type=Path, help="cover contract JSON: imagePath, fontFile, title, output")
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--duration-tolerance-ms", type=int, default=400)
    args = parser.parse_args()

    manifest = load(require_file(args.manifest, "G4 manifest"))
    if manifest.get("status") != "prepared_for_render":
        fail("manifest is not prepared_for_render")
    segments = manifest.get("segments", [])
    if not segments:
        fail("manifest has no segments")
    cursor = 0
    ordered_files: list[Path] = []
    for index, segment in enumerate(segments, 1):
        timeline = segment.get("timeline", {})
        start, end = timeline.get("startMs"), timeline.get("endMs")
        if not isinstance(start, int) or not isinstance(end, int) or start != cursor or end <= start:
            fail(f"segment {segment.get('segmentId')} is not contiguous at position {index}")
        cursor = end
        ordered_files.append(require_file(args.segments_dir / segment.get("output", {}).get("filename", f"seg-{index:03d}.mp4"), "rendered segment"))
    timeline_ms = int(manifest.get("timelineDurationMs") or cursor)
    if abs(cursor - timeline_ms) > args.duration_tolerance_ms:
        fail(f"segment timeline {cursor}ms does not match manifest timelineDurationMs {timeline_ms}ms")

    narration = require_file(args.narration_audio, "narration audio")
    narration_ms = probe_duration_ms(narration)
    if narration_ms + args.duration_tolerance_ms < timeline_ms:
        fail(f"narration audio ({narration_ms}ms) is shorter than the timeline ({timeline_ms}ms); align audio before assembly")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    work = args.output.parent / f"{args.output.stem}-assemble-work"
    work.mkdir(exist_ok=True)
    list_file = work / "concat.txt"
    list_file.write_text("\n".join(concat_line(path.resolve()) for path in ordered_files) + "\n", encoding="utf-8")

    inputs = [narration]
    if args.bgm_audio:
        inputs.append(require_file(args.bgm_audio, "BGM audio"))
    if args.subtitle_ass:
        require_file(args.subtitle_ass, "subtitle ASS")
        if not subtitles_filter_available():
            fail("this ffmpeg build lacks the libass subtitles filter; install full FFmpeg before burning captions")
        shutil.copyfile(args.subtitle_ass, work / "captions.ass")
        video_chain = f"[0:v]fps=fps={args.fps},format=yuv420p,subtitles=captions.ass[v]"
    else:
        video_chain = f"[0:v]fps=fps={args.fps},format=yuv420p[v]"
    filter_complex = video_chain + ";" + audio_filter_chain(1, 2 if len(inputs) == 2 else None, args.bgm_gain_db, args.bgm_duck)
    command = build_assemble_command(list_file.resolve(), [path.resolve() for path in inputs], filter_complex, args.output.resolve(), args.fps, timeline_ms / 1000)
    run_checked(command, args.output, "assembled master", cwd=work)

    output_ms = probe_duration_ms(args.output)
    if abs(output_ms - timeline_ms) > max(args.duration_tolerance_ms, len(segments) * 60):
        fail(f"assembled duration {output_ms}ms deviates from timeline {timeline_ms}ms beyond tolerance")
    streams = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "json", str(args.output.resolve())],
        capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout).get("streams", [])
    kinds = {stream.get("codec_type") for stream in streams}
    if "video" not in kinds or "audio" not in kinds:
        fail(f"assembled master lacks a video+audio stream pair: {sorted(kinds)}")

    cover_output = render_cover(args.cover, work) if args.cover else None

    record = {
        "schemaVersion": "0.1",
        "node": "G4",
        "projectId": manifest.get("projectId"),
        "status": "assembled",
        "manifest": str(args.manifest),
        "timelineDurationMs": timeline_ms,
        "segments": [{"segmentId": seg.get("segmentId"), "file": str(path), "sha256": sha256(path)} for seg, path in zip(segments, ordered_files)],
        "narrationAudio": {"path": str(narration), "sha256": sha256(narration), "durationMs": narration_ms},
        "bgmAudio": {"path": str(args.bgm_audio), "sha256": sha256(args.bgm_audio), "gainDb": args.bgm_gain_db, "ducked": bool(args.bgm_duck)} if args.bgm_audio else None,
        "subtitleAss": {"path": str(args.subtitle_ass), "sha256": sha256(args.subtitle_ass)} if args.subtitle_ass else None,
        "output": str(args.output),
        "outputSha256": sha256(args.output),
        "probedDurationMs": output_ms,
        "fps": args.fps,
        "cover": str(cover_output) if cover_output else None,
        "filterGraph": filter_complex,
        "workDir": str(work),
    }
    record_path = args.output.parent / f"{args.output.stem}-装配记录-v0.1.json"
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "assembled", "output": str(args.output), "durationMs": output_ms, "segments": len(segments), "record": str(record_path), "cover": str(cover_output) if cover_output else None}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=True))
        raise SystemExit(2)
