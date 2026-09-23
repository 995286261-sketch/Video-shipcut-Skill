#!/usr/bin/env python3
"""Audition-notes layer: A/B listening comparison against the reference track.

Honesty contract (user 2026-09-11, mirroring the edit nodes' visual-analysis
fallback): this layer records ONLY what the audio model actually produced. When no
audio-capable model is reachable it emits a structured `capability_missing` block and
an echo card that says so in plain words — it never invents a track description.
Notes are reference text for the human gate; they are never a pass/fail criterion.

Default backend is Aliyun Bailian `bl omni` (qwen-omni family); point
MUSIC_EXPERT_BL_BIN (legacy alias P0C_BL_BIN) or --bl at any compatible CLI.
Cost discipline: only the shortlist is listened to.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROMPT_TEMPLATE = (
    "你是资深音乐总监。第一段是【参照曲】（用户已确认想要的风格），第二段是【候选曲】。"
    "认真听完两段后回答：1) 候选曲与参照曲在流派、乐器、气质、节奏型上的差距；"
    "2) 候选曲能否{role}；3) 贴合度0-10分并一句话理由。简体中文，150字内。"
)
ABSOLUTE_TEMPLATE = (
    "你是资深音乐总监。认真听完这段音乐后回答：1) 曲风流派（精确到子流派）；2) 主要乐器与音色；"
    "3) 情绪与气质；4) 能量结构：铺垫段与高潮段大约在几分几秒到几分几秒；"
    "5) 适合与不适合的剪辑场景各一句。简体中文，200字内。"
)
REFERENCE_NOTE_TEMPLATE = (
    "你是资深音乐总监，正在为一部片子定背景音乐的检索方向。这是【参照曲】——用户想要的感觉。"
    "认真听完（可能有多段节选，合起来听整体）后回答：1) 曲风流派，精确到子流派；2) BPM 大致区间；"
    "3) 主要乐器与音色；4) 节奏型：有无持续鼓点/驱动感，还是氛围铺底；5) 情绪与气质；"
    "6) 若要去音乐库检索同风格成品曲，给 3-5 个英文检索词。简体中文，220字内。"
)
PROMPT_VER = "v1"


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def resolve_bl(explicit: str | None) -> str:
    # Generic name first so the skill stays portable; P0C_* kept as a legacy alias.
    return (explicit or os.environ.get("MUSIC_EXPERT_BL_BIN")
            or os.environ.get("P0C_BL_BIN") or "bl")


def probe_capability(bl_path: str) -> tuple[bool, str]:
    """Can this environment actually listen? Absence is a fact to report, not to hide."""
    binary = shutil.which(bl_path)
    if not binary:
        return False, (f"audio-model CLI `{bl_path}` not found; install it or point "
                       "--bl/MUSIC_EXPERT_BL_BIN at one")
    try:
        version = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, f"`{binary} --version` failed: {str(error)[:150]}"
    if version.returncode != 0:
        return False, f"`{binary} --version` exit {version.returncode}: {(version.stderr or '')[:150]}"
    try:
        auth = subprocess.run([binary, "auth", "status"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        auth = None
    if auth is not None:
        key_lines = [line for line in (auth.stdout or "").splitlines() if "API key" in line]
        if key_lines and not any("not configured" in line for line in key_lines):
            return True, version.stdout.strip()
        return False, "audio-model CLI present but no API key configured (run `bl auth login`)"
    return True, version.stdout.strip()


def media_duration(path: Path) -> int | None:
    probe = shutil.which("ffprobe")
    if not probe:
        return None
    try:
        result = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration",
                                 "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                                capture_output=True, text=True, timeout=60)
        return int(float(result.stdout.strip()) * 1000)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def excerpt(src: Path, workdir: Path, start_ms: int, dur_sec: int, suffix: str = "") -> Path:
    target = workdir / f"excerpt-{src.stem[:40]}{suffix}.mp3"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(start_ms / 1000.0), "-t", str(dur_sec),
                    "-i", str(src), "-c:a", "libmp3lame", "-q:a", "4", str(target)],
                   check=True, capture_output=True, timeout=180)
    return target


def load_shortlist(manifests: list[Path]) -> tuple[list[dict], list[str]]:
    tracks, skipped = [], []
    for manifest in manifests:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        entries = data.get("candidates") or data.get("ranked") or []
        for entry in entries:
            preview = entry.get("previewPath")
            if not preview or not Path(preview).is_file():
                skipped.append(str(entry.get("title") or preview))
                continue
            tracks.append(entry)
    return tracks, skipped


def file_sha(path: Path) -> str:
    import hashlib
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def listen(binary: str, model: str | None, audios: list[Path],
           message: str, timeout: int) -> tuple[str | None, str | None]:
    cmd = [binary, "omni", "--text-only"]
    for audio in audios:
        cmd += ["--audio", str(audio)]
    cmd += ["--message", message]
    if model:
        cmd += ["--model", model]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, f"audio model call timed out after {timeout}s"
    except OSError as error:
        return None, str(error)[:200]
    if result.returncode != 0:
        return None, f"exit {result.returncode}: {(result.stderr or result.stdout or '')[:300]}"
    text = (result.stdout or "").strip()
    lines = [line for line in text.splitlines() if not line.startswith("[Model:")]
    if lines and lines[0].strip().startswith("content:"):
        # block scalar 头（"content: |-"）去掉；同行直接带正文的（"content: xxx"）保留正文
        same_line = lines[0].split(":", 1)[1].strip().strip("-|>").strip()
        lines = ([same_line] if same_line else []) + lines[1:]
    text = "\n".join(line.strip() for line in lines).strip()
    if not text:
        return None, "audio model returned an empty response"
    return text, None


def render_echo(result: dict, path: Path) -> None:
    lines = ["# BGM 模型试听笔记 v0.1", ""]
    capability = result["capability"]
    if not capability["available"]:
        lines += [f"> ⚠ 当前环境**没有听觉分析能力**（{capability['detail']}）。",
                  "> 本文件不含任何曲目描述——没有真实听过，就不会有笔记；此处不编造。",
                  "> 配好音频模型（如 `bl auth login`）后重跑本层即可补全。", ""]
    else:
        ref_part = f"｜参照曲：{result['reference']}" if result.get("reference") else "｜绝对属性模式（笔记可入库复用）"
        lines += [f"- 模型：{capability['audioModel']}{ref_part}",
                  "- 本层只记录模型真实听到的输出；每条失败如实标注，未听曲目绝不配文字。", ""]
    note = result.get("referenceNote")
    if note:
        head = "## 参照曲风格画像（绝对属性·检索词证据）" if note.get("notes") else "## 参照曲风格画像"
        lines += [head, "", note["notes"] or f"❌ 未获得笔记（{note.get('error')}）", ""]
    for track in result["tracks"]:
        lines += [f"## {track['title']}", "", track["notes"], ""]
    for failure in result["partialFailures"]:
        lines += [f"## {failure['title']}", "", f"❌ 未获得笔记（{failure['error']}）", ""]
    if result.get("skippedWithoutPreview"):
        lines += [f"- 无试听件跳过：{len(result['skippedWithoutPreview'])} 首。", ""]
    lines += ["---", "", result["disclaimer"], ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, help="anchor audio the user approved (A/B mode)")
    parser.add_argument("--reference-note", action="store_true",
                        help="先对参照曲本体出一张绝对风格画像（出检索词前的耳朵证据，验收003-⑤）；"
                             "不给 --manifest 时只出参照曲笔记")
    parser.add_argument("--absolute", action="store_true",
                        help="listen to each track on its own (reusable absolute attributes; write-back eligible)")
    parser.add_argument("--library", type=Path, default=None,
                        help="experience/music root: reuse heard notes, ingest ledger, write back absolute notes")
    parser.add_argument("--project", default=None, help="project id for ledger records")
    parser.add_argument("--manifest", action="append", required=False, type=Path, default=[],
                        help="candidate manifest or recommendation JSON (repeatable)")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--bl", default=None,
                        help="audio-model CLI (default $MUSIC_EXPERT_BL_BIN, legacy $P0C_BL_BIN, or `bl`)")
    parser.add_argument("--model", default=None, help="model id override (default: CLI profile default)")
    parser.add_argument("--project-brief", default="给本项目当高燃卡点 BGM", help="fit role phrasing")
    parser.add_argument("--excerpt-sec", type=int, default=90, help="0 = send original files")
    parser.add_argument("--max-tracks", type=int, default=10, help="cost cap: shortlist size")
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()

    if args.absolute:
        args.reference = None
    if (args.reference_note or not args.absolute) and (not args.reference or not args.reference.is_file()):
        emit({"status": "invalid", "errors": [{"field": "reference", "rule": "file not found (A/B or --reference-note needs the anchor; or run --absolute)",
                                               "detail": str(args.reference)}]})
        return 2
    if args.reference_note and args.manifest:
        emit({"status": "invalid", "errors": [{"field": "referenceNote",
              "rule": "--reference-note profiles the anchor alone; drop --manifest to get the reference style picture, or run a separate A/B pass"}]})
        return 2
    if not args.reference_note and not args.manifest:
        emit({"status": "invalid", "errors": [{"field": "manifest", "rule": "a candidate A/B/absolute pass needs --manifest", "detail": None}]})
        return 2
    library = None
    if args.library:
        if not args.library.is_dir():
            emit({"status": "invalid", "errors": [{"field": "library", "rule": "directory not found",
                                                   "detail": str(args.library)}]})
            return 2
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import music_library
        library = args.library
    for manifest in args.manifest:
        if not manifest.is_file():
            emit({"status": "invalid", "errors": [{"field": "manifest", "rule": "file not found",
                                                   "detail": str(manifest)}]})
            return 2

    binary = resolve_bl(args.bl)
    available, detail = probe_capability(binary)
    from versioned_output import next_versioned  # Issue ⑬: multi-run echoes never overwrite
    echo_path, _ = next_versioned(args.output.parent, "BGM-试听笔记回显", ".md")
    if not available:
        result = {"schemaVersion": "0.1", "purpose": "bgm_audition_notes",
                  "capability": {"available": False, "audioModel": None, "detail": detail},
                  "reference": str(args.reference) if args.reference else None, "tracks": [], "partialFailures": [],
                  "disclaimer": "模型试听笔记仅供参考，不作为门禁通过条件；最终取舍在人耳。"}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        render_echo(result, echo_path)
        emit({"status": "blocked", "blockers": [{"type": "capability_missing", "detail": detail,
                                                 "echo": str(echo_path)}]})
        return 2
    audio_binary = shutil.which(binary)

    if args.excerpt_sec > 0 and shutil.which("ffmpeg") is None:
        emit({"status": "blocked", "blockers": [{"type": "missing_toolchain",
                                                 "detail": "ffmpeg required for excerpts (or pass --excerpt-sec 0)"}]})
        return 2

    if args.reference_note:
        # 验收003-⑤: genre facts about the anchor must come from EARS before search terms
        # are written (N8-⑫ and the live 002 re-run both burned a full round on imagined
        # "orchestral" terms). Long anchors get 2-3 excerpts across the timeline so a single
        # quiet passage cannot masquerade as the whole song's style.
        workdir = args.output.parent / "listen-excerpts"
        workdir.mkdir(parents=True, exist_ok=True)
        ref_ms = media_duration(args.reference) or 0
        audios: list[Path] = [args.reference]
        if args.excerpt_sec > 0 and ref_ms > args.excerpt_sec * 1000:
            starts = [0.2, 0.5, 0.8] if ref_ms >= args.excerpt_sec * 3000 else [0.2, 0.7]
            audios = [excerpt(args.reference, workdir, int(ref_ms * s), args.excerpt_sec,
                              suffix=f"-ref{int(s * 100)}") for s in starts]
        text, error = listen(audio_binary, args.model, audios, REFERENCE_NOTE_TEMPLATE, args.timeout)
        note = {"reference": str(args.reference), "promptVersion": PROMPT_VER, "mode": "reference-note",
                "excerpts": [str(a) for a in audios], "notes": text, "error": error}
        result = {"schemaVersion": "0.1", "purpose": "bgm_audition_notes", "mode": "reference-note",
                  "capability": {"available": True, "audioModel": detail, "modelOverride": args.model},
                  "reference": str(args.reference), "referenceNote": note,
                  "tracks": [], "partialFailures": [] if text else [{"title": args.reference.name, "error": error}],
                  "writebackFailures": [], "skippedWithoutPreview": [],
                  "disclaimer": "模型试听笔记仅供参考，不作为门禁通过条件；最终取舍在人耳。"}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        render_echo(result, echo_path)
        emit({"status": "ok", "heard": 1 if text else 0, "failures": 0 if text else 1,
              "output": str(args.output), "echo": str(echo_path)})
        return 0 if text else 2

    tracks, skipped = load_shortlist(args.manifest)
    if not tracks:
        emit({"status": "blocked", "blockers": [{"type": "no_candidates",
                                                 "detail": "no candidate with an existing previewPath"}]})
        return 2
    tracks = tracks[: args.max_tracks]
    mode = "absolute" if args.absolute else "ab"
    message = ABSOLUTE_TEMPLATE if args.absolute else PROMPT_TEMPLATE.format(role=args.project_brief)
    workdir = args.output.parent / "listen-excerpts"
    ref = None
    if args.excerpt_sec > 0:
        workdir.mkdir(parents=True, exist_ok=True)
        if args.reference:
            ref_ms = media_duration(args.reference) or 0
            ref = excerpt(args.reference, workdir, max(0, int(ref_ms * 0.2)), args.excerpt_sec)

    # 验收003-⑥: A/B re-ranking re-burns identical (anchor, candidate) pairs. The A/B note
    # is a RELATIVE verdict -- red line says it never becomes a library fact -- so the cache
    # is a project-local sidecar, deliberately kept outside experience/music.
    ab_cache: dict = {}
    ab_cache_path = args.output.parent / "试听AB-缓存.json"
    if mode == "ab" and ab_cache_path.is_file():
        try:
            ab_cache = json.loads(ab_cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            ab_cache = {}
    ref_sha = file_sha(args.reference) if (mode == "ab" and args.reference) else None
    notes, failures, writeback_failures = [], [], []
    for track in tracks:
        candidate = Path(track["previewPath"])
        sha = str(track.get("sha256") or "").upper() or (music_library.sha256_file(candidate) if library else None)
        entry = {"title": track.get("title"), "neteaseId": track.get("neteaseId"), "sha256": sha}
        if library and args.absolute and sha:
            cached = music_library.latest_listen_note(library, sha, detail, PROMPT_VER)
            if cached:
                entry["reused"] = True
                entry["notes"] = f"（复用库内 {cached[0]} 笔记，零成本）\n\n{cached[1]}"
                notes.append(entry)
                continue
        cache_key = None
        if mode == "ab" and sha and ref_sha:
            cache_key = f"{sha}|{ref_sha}|{PROMPT_VER}|{args.model or 'default'}|{args.project_brief}"
            hit = ab_cache.get(cache_key)
            if hit:
                entry["reused"] = "ab-cache"
                entry["notes"] = f"（复用本项目 A/B 试听缓存，零成本）\n\n{hit}"
                notes.append(entry)
                continue
        audio_arg = candidate
        if args.excerpt_sec > 0:
            duration_ms = track.get("durationMs") or media_duration(candidate) or 0
            if duration_ms > args.excerpt_sec * 1000:
                audio_arg = excerpt(candidate, workdir, max(0, int(duration_ms * 0.2)), args.excerpt_sec)
        audios = [audio_arg] if args.absolute else [ref, audio_arg]
        text, error = listen(audio_binary, args.model, audios, message, args.timeout)
        if error is not None:
            failures.append({**entry, "error": error})
            continue
        entry.update({"reused": False, "notes": text})
        notes.append(entry)
        if cache_key:
            ab_cache[cache_key] = text
        if library and sha:
            try:
                music_library.upsert_track(library, sha, title=track.get("title"),
                                           netease_id=track.get("neteaseId"),
                                           source_url=track.get("sourceUrl"),
                                           provenance=track.get("provenance") or "netease_search",
                                           project=args.project,
                                           license_value=track.get("license") or track.get("licenseType"),
                                           boundary=track.get("distributionBoundary"),
                                           audio_ref=candidate)
                if args.absolute:
                    music_library.put_listen(library, sha, text, detail, PROMPT_VER)
            except Exception as error:  # 写回失败不伪装成"没听到"，也不中断笔记
                writeback_failures.append({"title": entry.get("title"), "error": str(error)[:200]})

    if mode == "ab" and ab_cache:
        ab_cache_path.parent.mkdir(parents=True, exist_ok=True)
        ab_cache_path.write_text(json.dumps(ab_cache, ensure_ascii=False, indent=2), encoding="utf-8")

    result = {"schemaVersion": "0.1", "purpose": "bgm_audition_notes", "mode": mode,
              "capability": {"available": True, "audioModel": detail, "modelOverride": args.model},
              "reference": str(args.reference) if args.reference else None, "projectBrief": args.project_brief,
              "library": str(library) if library else None,
              "tracks": notes, "partialFailures": failures, "writebackFailures": writeback_failures,
              "skippedWithoutPreview": skipped,
              "disclaimer": "模型试听笔记仅供参考，不作为门禁通过条件；最终取舍在人耳。"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    render_echo(result, echo_path)
    emit({"status": "ok", "heard": len(notes), "failures": len(failures),
          "output": str(args.output), "echo": str(echo_path)})
    return 0 if notes else 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
