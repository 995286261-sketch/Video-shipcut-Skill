#!/usr/bin/env python3
"""Assemble the flattened G4 master from the editable manifest: concat, audio mix,
subtitle burn-in, and cover compositing. This is the only sanctioned entry point for
final assembly; hand-stitched ffmpeg command lines are not reproducible (issue 027).

The command always checks that every ffmpeg output exists and is non-empty (issue 022
rule reused here), and writes an auditable assembly record next to the master.

BGM (N6, 2026-09-10): mixing executes a music-expert mix contract verbatim —
this script never picks gains, ducking windows, or fades itself, and refuses a
--bgm-audio without --bgm-mix-contract.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
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


# The standard narration chain proven on the kshatriya runs (issue ㊌): a
# broadband compressor with makeup first, then loudnorm to the target. TTS
# sources with a high peak-to-loudness ratio cannot reach -14 LUFS by
# normalization alone — the compressor is what makes it reachable.
NARRATION_STANDARD_CHAIN = "acompressor=threshold=0.1:ratio=8:attack=15:release=250:makeup=2,loudnorm=I={target:g}:TP=-1.5:LRA=9"


def audio_filter_chain(narration_index: int, bgm_index: int | None, mix_contract: dict | None,
                       narration_pre: str | None = None) -> str:
    """BGM mixing is executed verbatim from the music-expert mix contract (N6):
    bed gain, per-narration-window ducking automation, and fades all come from
    the artifact that was reconciled against the approved G3 plan. The node
    skill renders; it does not make music decisions."""
    narration = f"[{narration_index}:a]"
    pre = ""
    if narration_pre:
        pre = f"{narration}{narration_pre}[narr];"
        narration = "[narr]"
    if bgm_index is None:
        return f"{pre}{narration}anull[aud]"
    fades = mix_contract.get("fades") or {}
    bed_parts = [f"volume={float(mix_contract['bedGainDb']):g}dB"]
    segments = mix_contract.get("duckSegments") or []
    if segments:
        expr = "+".join(f"between(t,{s['fromMs'] / 1000:.3f},{s['toMs'] / 1000:.3f})" for s in segments)
        bed_parts.append(f"volume=-{float(mix_contract['duckReductionDb']):g}dB:enable='{expr}'")
    if int(fades.get("fadeInMs") or 0) > 0:
        bed_parts.append(f"afade=t=in:st=0:d={int(fades['fadeInMs']) / 1000:.3f}")
    if int(fades.get("fadeOutMs") or 0) > 0:
        bed_parts.append(f"afade=t=out:st={int(fades['fadeOutStartMs']) / 1000:.3f}:d={int(fades['fadeOutMs']) / 1000:.3f}")
    return (f"{pre}[{bgm_index}:a]" + ",".join(bed_parts)
            + f"[bed];[bed]{narration}amix=inputs=2:duration=longest:normalize=0[aud]")


def measure_ebur128(path: Path) -> dict:
    """Post-render loudness truth (issue ㊌: measure, never improvise). Takes the LAST
    ebur128 match and rejects silence-floor sentinels, same discipline as music-expert."""
    result = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
                             "-filter:a", "ebur128=peak=true", "-f", "null", "-"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    text = (result.stderr or "") + (result.stdout or "")
    integrated, true_peak = None, None
    matches = re.findall(r"I:\s+(-?\d+\.?\d*)\s*LUFS", text)
    if matches:
        value = float(matches[-1])
        integrated = None if value <= -69.9 else value
    matches = re.findall(r"True peak:\s*\n?\s*Peak:\s+(-?\d+\.?\d*)\s*dBFS", text)
    if matches:
        value = float(matches[-1])
        true_peak = None if value <= -99.9 else value
    return {"integratedLufs": integrated, "truePeakDbtp": true_peak, "engine": "ffmpeg-ebur128"}


def measure_bgm_in_place(bgm_path: Path, contract: dict, timeline_ms: int) -> float | None:
    """Render the bed chain alone through ebur128: the level the listener actually
    hears under the voice. The zaku lesson — a bed 25 LU under the narration is
    'mixed in' yet inaudible; that must be a measured number, never an ear-witness."""
    fades = contract.get("fades") or {}
    parts = [f"volume={float(contract['bedGainDb']):g}dB"]
    segments = contract.get("duckSegments") or []
    if segments:
        expr = "+".join(f"between(t,{s['fromMs'] / 1000:.3f},{s['toMs'] / 1000:.3f})" for s in segments)
        parts.append(f"volume=-{float(contract['duckReductionDb']):g}dB:enable='{expr}'")
    parts.append("ebur128=peak=true")
    # Cap the looped read with an input-side -t: atrim-EOF does not reliably stop
    # a -stream_loop -1 mp3 reader (zaku live run hung the measurement for 21 CPU-minutes).
    result = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-stream_loop", "-1",
                             "-t", f"{timeline_ms / 1000:.3f}", "-i", str(bgm_path),
                             "-af", ",".join(parts), "-f", "null", "-"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    matches = re.findall(r"I:\s+(-?\d+\.?\d*)\s*LUFS", (result.stderr or "") + (result.stdout or ""))
    if not matches:
        return None
    value = float(matches[-1])
    return None if value <= -69.9 else value


def build_assemble_command(list_file: Path, inputs: list[Path], filter_complex: str, output: Path, fps: int, duration_s: float,
                           bgm_seek_s: float | None = None, segment_files: list | None = None) -> list[str]:
    command = ["ffmpeg", "-y"]
    audio_start = 1
    if segment_files:
        # 转场路径：逐段独立输入供 xfade/concat 滤镜链使用（网格由指令的 offset 算术保证）。
        for path in segment_files:
            command += ["-i", str(path)]
        audio_start = len(segment_files)
    else:
        command += ["-f", "concat", "-safe", "0", "-i", str(list_file)]
    for offset, path in enumerate(inputs):
        index = audio_start + offset
        loop = ["-stream_loop", "-1"] if path.suffix.lower() in {".mp3", ".m4a", ".wav", ".ogg", ".flac", ".aac"} and offset > 0 else []
        seek = ["-ss", f"{bgm_seek_s:.3f}"] if bgm_seek_s and offset == 1 else []
        command += [*loop, *seek, "-i", str(path)]
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


def build_video_chain(video_layers: list[str], card_filters: list[str], fade_layers: list[str],
                      segment_ids: list[str], transition_by_pair: dict, fps: int, use_xfade: bool) -> str:
    """无转场：旧路径 [0:v] 分层，逐字节不变。有转场：逐段 [i:v] 先统一 fps/format/sar
    （xfade 前提），再按批准边界逐个 xfade、硬切边保持 concat，字幕/标题栏/章节卡等
    叠加层落在链接输出之后——网格不变 ⇒ 这些时间坐标与旧路径完全一致。"""
    if not use_xfade:
        return ",".join([*video_layers, *card_filters, *fade_layers]) + "[v]"
    parts = [f"[{index}:v]fps=fps={fps},format=yuv420p,setsar=1[segv{index}]" for index in range(len(segment_ids))]
    current = "segv0"
    for index in range(len(segment_ids) - 1):
        following = f"segv{index + 1}"
        output = f"vcat{index}"
        boundary = transition_by_pair.get((segment_ids[index], segment_ids[index + 1]))
        if boundary:
            duration = int(boundary["durationMs"]) / 1000
            offset = int(boundary["offsetMs"]) / 1000
            parts.append(f"[{current}][{following}]xfade=transition={boundary['transition']}:duration={duration:.3f}:offset={offset:.3f}[{output}]")
        else:
            parts.append(f"[{current}][{following}]concat=n=2:v=1:a=0[{output}]")
        current = output
    overlays = ",".join([*video_layers[1:], *card_filters, *fade_layers])
    return ";".join(parts + [f"[{current}]{overlays}"]) + "[v]"


SUBTITLE_TRIM_SCRIPT = Path(__file__).resolve().parents[2] / "subtitle-expert" / "scripts" / "subtitle_trim_cues.py"


def run_specialist_trim(ass_path: Path, out_path: Path, card_ranges: list[tuple[int, int]]) -> int:
    """Hide-under-chapter-card cue trimming is subtitle presentation logic and lives in
    subtitle-expert (plugin handshake: CLI args in, derived .ass + JSON report out;
    zero in-process imports, G4 burns only what the specialist writes)."""
    if not SUBTITLE_TRIM_SCRIPT.is_file():
        fail(f"subtitle-expert trim script not found: {SUBTITLE_TRIM_SCRIPT}; "
             "install skill/subtitle-expert alongside this skill (cue trimming is not G4's job)")
    command = [sys.executable, str(SUBTITLE_TRIM_SCRIPT), "--ass", str(ass_path), "--out", str(out_path)]
    for start, end in card_ranges:
        command += ["--card-range", f"{start}:{end}"]
    result = subprocess.run(command, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", shell=False)
    try:
        report = json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        report = {}
    if result.returncode != 0 or report.get("status") != "completed":
        detail = report.get("error") or (result.stderr or result.stdout or "").strip()[:300]
        fail(f"subtitle-expert cue trim failed (exit {result.returncode}): {detail}")
    return int(report.get("trimmedCues") or 0)


def _cmap_codepoints(data: bytes, off: int) -> set[int]:
    """Codepoints of one cmap subtable (formats 0/4/6/12); stdlib-only parser
    because drawtext silently renders tofu for missing glyphs (issue ㉛)."""
    fmt = int.from_bytes(data[off:off + 2], "big")
    if fmt == 0:
        return {i for i in range(256) if data[off + 2 + i]}
    if fmt == 4:
        seg_count = int.from_bytes(data[off + 6:off + 8], "big") // 2
        cursor = off + 14
        ends = [int.from_bytes(data[cursor + 2 * i:cursor + 2 * i + 2], "big") for i in range(seg_count)]
        cursor += 2 * seg_count + 2
        starts = [int.from_bytes(data[cursor + 2 * i:cursor + 2 * i + 2], "big") for i in range(seg_count)]
        cursor += 2 * seg_count
        deltas = [int.from_bytes(data[cursor + 2 * i:cursor + 2 * i + 2], "big") for i in range(seg_count)]
        cursor += 2 * seg_count
        range_off_base = cursor
        result: set[int] = set()
        for i in range(seg_count):
            start, end = starts[i], ends[i]
            if start == 0xFFFF:
                continue
            range_offset = int.from_bytes(data[range_off_base + 2 * i:range_off_base + 2 * i + 2], "big")
            for cp in range(start, min(end, 0xFFFF) + 1):
                if range_offset:
                    probe = range_off_base + 2 * i + range_offset + (cp - start) * 2
                    gid = int.from_bytes(data[probe:probe + 2], "big")
                    if gid:
                        result.add(cp)
                elif (cp + deltas[i]) & 0xFFFF:
                    result.add(cp)
        return result
    if fmt == 6:
        first = int.from_bytes(data[off + 6:off + 8], "big")
        count = int.from_bytes(data[off + 8:off + 10], "big")
        return {first + i for i in range(count) if data[off + 10 + i]}
    if fmt == 12:
        groups = int.from_bytes(data[off + 12:off + 16], "big")
        result = set()
        for i in range(groups):
            base = off + 16 + 12 * i
            start = int.from_bytes(data[base:base + 4], "big")
            end = int.from_bytes(data[base + 4:base + 8], "big")
            gid = int.from_bytes(data[base + 8:base + 12], "big")
            if gid and end - start < 2_000_000:
                result.update(range(start, end + 1))
        return result
    raise ValueError(f"unsupported cmap subtable format {fmt}")


def font_face_cmaps(font: Path) -> list[set[int]]:
    """One codepoint set per face, in file order. `ttcf` collections matter here:
    FreeType/drawtext renders the FIRST face, which on PingFang.ttc lacks
    several simplified-Chinese glyphs that later faces carry (issue ㉛)."""
    data = font.read_bytes()
    if data[:4] == b"ttcf":
        face_count = int.from_bytes(data[8:12], "big")
        offsets = [int.from_bytes(data[12 + 4 * i:16 + 4 * i], "big") for i in range(face_count)]
    else:
        offsets = [0]
    faces = []
    for base in offsets:
        if len(data) < base + 12:
            raise ValueError("truncated font header")
        num_tables = int.from_bytes(data[base + 4:base + 6], "big")
        cmap_off = None
        for i in range(num_tables):
            record = base + 12 + 16 * i
            if data[record:record + 4] == b"cmap":
                cmap_off = int.from_bytes(data[record + 8:record + 12], "big")
        if cmap_off is None:
            raise ValueError("font has no cmap table")
        table_count = int.from_bytes(data[cmap_off + 2:cmap_off + 4], "big")
        cps: set[int] = set()
        for i in range(table_count):
            entry = cmap_off + 4 + 8 * i
            platform = int.from_bytes(data[entry:entry + 2], "big")
            encoding = int.from_bytes(data[entry + 2:entry + 4], "big")
            if platform == 0 or (platform == 3 and encoding in (1, 10)):
                cps |= _cmap_codepoints(data, cmap_off + int.from_bytes(data[entry + 4:entry + 8], "big"))
        faces.append(cps)
    return faces


def shown(codepoints: set[int]) -> str:
    return "、".join(sorted({chr(cp) for cp in codepoints}))


def require_glyph_coverage(font: Path, text: str, label: str) -> None:
    """Fail before ffmpeg does: a missing glyph in drawtext output is a silent
    tofu rectangle on the client's deliverable (issue ㉛)."""
    wanted = {ord(ch) for ch in text if not ch.isspace()}
    if not wanted:
        return
    try:
        faces = font_face_cmaps(font)
    except ValueError as error:
        fail(f"{label} font {font.name} cannot be checked for glyph coverage: {error}; refusing to risk silent tofu (issue ㉛)")
    covered_all = set().union(*faces)
    hard_missing = wanted - covered_all
    if hard_missing:
        fail(f"{label} font {font.name} has no glyphs for 「{shown(hard_missing)}」; drawtext would render tofu (issue ㉛) — pick a covering font or burn the text in via libass")
    if len(faces) > 1:
        first_missing = wanted - faces[0]
        if first_missing:
            fail(f"{label} font {font.name} 是 TTC 字体集合，drawtext 只会渲染第一个 face，而「{shown(first_missing)}」只在其后的 face 中（㉛ 活测：PingFang.ttc 首 face 缺简体「战场队」渲成豆腐块）——改用单 face 字体文件，或走 libass 烧录路线")


def drawtext_filter(font: Path, text_file: Path, fontsize: int, position: str, enable: str | None) -> str:
    font_arg = str(font.resolve()).replace(":", "\\:")
    text_arg = str(text_file.resolve()).replace(":", "\\:")
    filter_text = (
        f"drawtext=fontfile={font_arg}:textfile={text_arg}:fontsize={fontsize}:fontcolor=white"
        ":borderw=2:bordercolor=black@0.7:box=1:boxcolor=black@0.55:boxborderw=18"
        f":x=(w-text_w)/2:{position}"
    )
    if enable:
        filter_text += f":enable='{enable}'"
    return filter_text


def build_chapter_card_filters(contract: dict, work: Path, timeline_ms: int) -> tuple[list[str], list[tuple[int, int]]]:
    cards = contract.get("cards")
    if not isinstance(cards, list) or not cards:
        fail("chapter cards contract requires a non-empty cards list")
    font = require_file(Path(str(contract.get("fontFile") or "")), "chapter cards font")
    fontsize = int(contract.get("fontsize", 26))
    # yRatio pins the card top edge to a fraction of frame height so the node can honour
    # the approved subtitle layout contract's title lane; default stays vertically centred.
    y_ratio = contract.get("yRatio")
    position = "y=(h-text_h)/2" if y_ratio is None else f"y=h*{float(y_ratio):.4f}"
    filters, ranges, previous_end = [], [], 0
    for index, card in enumerate(cards, 1):
        start, end = card.get("startMs"), card.get("endMs")
        title = str(card.get("title") or "").strip()
        if not isinstance(start, int) or not isinstance(end, int) or end <= start:
            fail(f"chapter card {index} needs integer startMs/endMs with end > start")
        if not title:
            fail(f"chapter card {index} requires a title")
        if start < previous_end or end > timeline_ms:
            fail(f"chapter card {index} [{start},{end}) overlaps a previous card or exceeds the timeline {timeline_ms}ms")
        previous_end = end
        require_glyph_coverage(font, title, f"chapter card {index}")
        text_file = work / f"chapter-card-{index}.txt"
        text_file.write_text(title, encoding="utf-8")
        filters.append(drawtext_filter(font, text_file, fontsize, position, f"between(t,{start / 1000:.3f},{end / 1000:.3f})"))
        ranges.append((start, end))
    return filters, ranges


def build_title_bar_filter(contract: dict, work: Path) -> str:
    font = require_file(Path(str(contract.get("fontFile") or "")), "title bar font")
    title = str(contract.get("text") or "").strip()
    if not title:
        fail("title bar contract requires text")
    fontsize = int(contract.get("fontsize", 14))
    margin_pct = float(contract.get("marginPct", 8))
    if not 0 < margin_pct < 50:
        fail("title bar marginPct must be between 0 and 50")
    require_glyph_coverage(font, title, "title bar")
    text_file = work / "title-bar.txt"
    text_file.write_text(title, encoding="utf-8")
    return drawtext_filter(font, text_file, fontsize, f"y=h*{margin_pct / 100:.4f}", None)


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
    require_glyph_coverage(font, title, "cover title")
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
    parser.add_argument("--bgm-mix-contract", type=Path,
                        help="music-expert BGM-混音合同-v0.1.json (required with --bgm-audio; run music_mix_plan.py first)")
    parser.add_argument("--cover", type=Path, help="cover contract JSON: imagePath, fontFile, title, output")
    parser.add_argument("--chapter-cards", type=Path, help="chapter cards contract JSON: fontFile, fontsize, cards[{chapterId,title,startMs,endMs}]")
    parser.add_argument("--title-bar", type=Path, help="title bar contract JSON: fontFile, text, fontsize, marginPct")
    parser.add_argument("--normalize-narration-lufs", type=float, default=None,
                        help="apply the standard narration loudness chain to this integrated-loudness target (e.g. -14); result is measured and recorded, never assumed")
    parser.add_argument("--fps", type=int, default=None,
                        help="override; by default inherit the manifest targetFps from the approved plan (issue 002-⑨)")
    parser.add_argument("--duration-tolerance-ms", type=int, default=400)
    args = parser.parse_args()

    manifest = load(require_file(args.manifest, "G4 manifest"))
    if manifest.get("status") != "prepared_for_render":
        fail("manifest is not prepared_for_render")
    if args.fps is None:
        inherited = manifest.get("targetFps")
        if isinstance(inherited, int) and not isinstance(inherited, bool) and inherited > 0:
            args.fps, fps_source = inherited, "manifest-targetFps"
        else:
            args.fps, fps_source = 24, "default-24"
    else:
        fps_source = "explicit-override"
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

    # 转场指令（transition-expert 经 prepare 透传）：加载即对账——哈希新鲜、网格一致、
    # 段文件确已按指令扩切。执行==批准，缺做的转场在这里就拦下，不留到成片。
    directive = None
    bound = manifest.get("transitionDirective")
    if isinstance(bound, dict) and bound:
        directive_path = require_file(Path(str(bound.get("path"))), "transition directive")
        if sha256(directive_path) != str(bound.get("sha256", "")).upper():
            fail("transition directive hash drifted from the manifest registration (stale — regenerate directive, then rerun prepare)")
        directive = load(directive_path)
        if directive.get("skill") != "transition-expert" or directive.get("purpose") != "transition_directive":
            fail("manifest.transitionDirective is not a transition-expert transition_directive artifact")
        if int(directive.get("timelineDurationMs") or 0) != timeline_ms:
            fail(f"transition directive grid {directive.get('timelineDurationMs')}ms != manifest timeline {timeline_ms}ms")
    use_xfade = bool(directive and directive.get("boundaries"))
    transition_by_pair = {(b["fromSegmentId"], b["toSegmentId"]): b for b in (directive or {}).get("boundaries", [])}
    if use_xfade:
        directive_extras = {item.get("segmentId"): item for item in directive.get("segments", [])}
        for segment, path in zip(segments, ordered_files):
            head = int((segment.get("transition") or {}).get("headExtraMs") or 0)
            tail = int((segment.get("transition") or {}).get("tailExtraMs") or 0)
            wanted = directive_extras.get(segment.get("segmentId"), {})
            if head != int(wanted.get("headExtraMs", 0)) or tail != int(wanted.get("tailExtraMs", 0)):
                fail(f"{segment.get('segmentId')} manifest transition extras do not match the directive")
            expected_ms = segment["timeline"]["endMs"] - segment["timeline"]["startMs"] + head + tail
            file_ms = probe_duration_ms(path)
            if abs(file_ms - expected_ms) > max(90, 2000 // args.fps):
                fail(f"{segment.get('segmentId')} rendered file {file_ms}ms != 网格+手柄 {expected_ms}ms——段文件未按指令扩切，重跑 g4_render")

    narration = require_file(args.narration_audio, "narration audio")
    narration_ms = probe_duration_ms(narration)
    if narration_ms + args.duration_tolerance_ms < timeline_ms:
        fail(f"narration audio ({narration_ms}ms) is shorter than the timeline ({timeline_ms}ms); align audio before assembly")
    narration_pre = None
    if args.normalize_narration_lufs is not None:
        if not -24.0 <= args.normalize_narration_lufs <= -8.0:
            fail("--normalize-narration-lufs must sit between -24 and -8 LUFS")
        narration_pre = NARRATION_STANDARD_CHAIN.format(target=args.normalize_narration_lufs)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    work = args.output.parent / f"{args.output.stem}-assemble-work"
    work.mkdir(exist_ok=True)
    list_file = work / "concat.txt"
    list_file.write_text("\n".join(concat_line(path.resolve()) for path in ordered_files) + "\n", encoding="utf-8")

    inputs = [narration]
    mix_contract = None
    if args.bgm_audio:
        require_file(args.bgm_audio, "BGM audio")
        if not args.bgm_mix_contract:
            fail("BGM mixing requires a music-expert mix contract (--bgm-mix-contract): run music_mix_plan.py against the approved plan; node skills execute, specialists decide (N6)")
        mix_contract = load(require_file(args.bgm_mix_contract, "BGM mix contract"))
        if mix_contract.get("purpose") != "bgm_mix_contract" or mix_contract.get("schemaVersion") != "0.1":
            fail("--bgm-mix-contract is not a music-expert BGM-混音合同-v0.1 artifact")
        if mix_contract.get("bgmAudio", {}).get("sha256") != sha256(args.bgm_audio):
            fail("BGM file hash does not match the mix contract — regenerate the contract with music_mix_plan.py")
        if int(mix_contract.get("timelineMs") or 0) != timeline_ms:
            fail(f"mix contract timeline {mix_contract.get('timelineMs')}ms does not match manifest {timeline_ms}ms")
        inputs.append(args.bgm_audio)
    card_filters: list[str] = []
    card_ranges: list[tuple[int, int]] = []
    if args.chapter_cards:
        card_contract = load(require_file(args.chapter_cards, "chapter cards contract"))
        card_filters, card_ranges = build_chapter_card_filters(card_contract, work, timeline_ms)
    trimmed_cues = 0
    video_layers = [f"[0:v]fps=fps={args.fps}", "format=yuv420p"]
    if args.subtitle_ass:
        require_file(args.subtitle_ass, "subtitle ASS")
        if not subtitles_filter_available():
            fail("this ffmpeg build lacks the libass subtitles filter; install full FFmpeg before burning captions")
        if card_ranges:
            trimmed_cues = run_specialist_trim(args.subtitle_ass, work / "captions.ass", card_ranges)
        else:
            shutil.copyfile(args.subtitle_ass, work / "captions.ass")
        video_layers.append("subtitles=captions.ass")
    title_contract = load(require_file(args.title_bar, "title bar contract")) if args.title_bar else None
    if title_contract:
        video_layers.append(build_title_bar_filter(title_contract, work))
    fade_layers: list[str] = []
    if directive:
        master = directive.get("masterFades") or {}
        if int(master.get("fadeInMs") or 0) > 0:
            fade_layers.append(f"fade=t=in:st=0:d={int(master['fadeInMs']) / 1000:.3f}")
        if int(master.get("fadeOutMs") or 0) > 0:
            fade_layers.append(f"fade=t=out:st={(timeline_ms - int(master['fadeOutMs'])) / 1000:.3f}:d={int(master['fadeOutMs']) / 1000:.3f}")
    video_chain = build_video_chain(video_layers, card_filters, fade_layers,
                                    [seg.get("segmentId") for seg in segments], transition_by_pair, args.fps, use_xfade)
    audio_base = len(ordered_files) if use_xfade else 1
    filter_complex = video_chain + ";" + audio_filter_chain(audio_base, audio_base + 1 if len(inputs) == 2 else None, mix_contract, narration_pre)
    bgm_seek_s = (int(mix_contract.get("trackOffsetMs") or 0) / 1000) if mix_contract else None
    command = build_assemble_command(list_file.resolve(), [path.resolve() for path in inputs], filter_complex, args.output.resolve(),
                                     args.fps, timeline_ms / 1000, bgm_seek_s=bgm_seek_s,
                                     segment_files=[path.resolve() for path in ordered_files] if use_xfade else None)
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

    bgm_in_place = None
    if mix_contract:
        bgm_in_place = measure_bgm_in_place(args.bgm_audio, mix_contract, timeline_ms)
        if bgm_in_place is not None and bgm_in_place < -33.0:
            fail(f"measured in-place BGM is {bgm_in_place:.1f} LUFS — inaudible under the voice; rerun music_mix_plan.py with a shallower bed/duck (zaku guard)")
        predicted = (mix_contract.get("predictedLufs") or {}).get("bedDuckedLufs")
        if bgm_in_place is not None and predicted is not None and abs(bgm_in_place - float(predicted)) > 3.0:
            fail(f"measured in-place BGM {bgm_in_place:.1f} LUFS deviates from the contract prediction {predicted} LUFS by more than 3 LU — chain drift, investigate before delivering")

    narration_loudness = None
    if narration_pre is not None:
        narration_loudness = measure_ebur128(args.output)
        narration_loudness["targetIntegratedLufs"] = args.normalize_narration_lufs
        narration_loudness["chain"] = "standard-narration-chain (acompressor+loudnorm, issue ㊌)"
        if args.bgm_audio:
            narration_loudness["caveat"] = "measured on the assembled master including the BGM bed, not narration alone"
        measured = narration_loudness["integratedLufs"]
        if measured is not None and abs(measured - args.normalize_narration_lufs) > 1.5:
            narration_loudness["note"] = ("achieved loudness deviates from target by more than 1.5 LU — likely the source peak-to-loudness "
                                          "ratio ceiling (kshatriya-002: -23.9 LUFS/+0.5 TP TTS tops out near -15.2); treat as a review item, do not re-chain blindly")

    cover_output = render_cover(args.cover, work) if args.cover else None

    record = {
        "schemaVersion": "0.1",
        "node": "G4",
        "projectId": manifest.get("projectId"),
        "status": "assembled",
        "manifest": str(args.manifest),
        "timelineDurationMs": timeline_ms,
        "segments": [{"segmentId": seg.get("segmentId"), "file": str(path), "sha256": sha256(path)} for seg, path in zip(segments, ordered_files)],
        "narrationAudio": {"path": str(narration), "sha256": sha256(narration), "durationMs": narration_ms,
                           "loudness": narration_loudness},
        "bgmMix": {
            "audio": {"path": str(args.bgm_audio), "sha256": sha256(args.bgm_audio)},
            "contract": {"path": str(args.bgm_mix_contract), "sha256": sha256(args.bgm_mix_contract)},
            "trackOffsetMs": mix_contract.get("trackOffsetMs"),
            "bedGainDb": mix_contract.get("bedGainDb"),
            "duckReductionDb": mix_contract.get("duckReductionDb"),
            "duckSegments": mix_contract.get("duckSegments"),
            "fades": mix_contract.get("fades"),
            "measuredInPlaceLufs": bgm_in_place,
        } if mix_contract else None,
        "subtitleAss": {"path": str(args.subtitle_ass), "sha256": sha256(args.subtitle_ass)} if args.subtitle_ass else None,
        "output": str(args.output),
        "outputSha256": sha256(args.output),
        "probedDurationMs": output_ms,
        "fps": args.fps,
        "fpsSource": fps_source,
        "cover": str(cover_output) if cover_output else None,
        "chapterCards": {
            "path": str(args.chapter_cards), "sha256": sha256(args.chapter_cards),
            "cards": len(card_ranges), "subtitleCuesTrimmed": trimmed_cues,
        } if args.chapter_cards else None,
        "titleBar": {
            "path": str(args.title_bar), "sha256": sha256(args.title_bar),
            "text": str(title_contract.get("text")),
        } if title_contract else None,
        "transitionDirective": {
            "path": str(bound.get("path")), "sha256": bound.get("sha256"),
            "boundaries": len((directive or {}).get("boundaries", [])),
            "masterFades": (directive or {}).get("masterFades"),
        } if directive else None,
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
