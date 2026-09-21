#!/usr/bin/env python3
"""Probe this host's subtitle renderer facts and emit a capability profile JSON.

Measurable facts: ffmpeg availability and version banner, the libass version it was
built with, and whether a font file exists on disk. `autoWrap` is NOT measurable
without pixel analysis — it stays at the conservative default false unless the caller
supplies evidence (issue 002-⑧: local libass builds do not auto-wrap CJK, and a
validator green light built on the wrong assumption shipped clipped subtitles).
能力可以缺、事实不能编：claiming true without evidence is refused outright.

The profile is an INPUT to the G3 layout contract (lanes.narration.autoWrap), never a
gate by itself. Output is verified to exist and be non-empty (issue 022 rule).
"""
from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

PROFILE_NAME = "字幕-渲染器能力档-v0.1.json"
# 09-21 实测抓到误解析：configuration 行的 "--enable-libass --enable-libfreetype" 曾被
# 当成版本号。只接受独立成行的 libass 版本（如 "libass 0.17.3"）；configuration 行只用于
# 判定编译开关是否启用，版本拿不到就如实 unknown——事实可以缺，不能解析错。
LIBASS_LINE = re.compile(r"^libass\s+(\d\S*)", re.M)
LIBASS_FLAG = re.compile(r"--enable-libass\b")


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def probe_ffmpeg() -> dict | None:
    if shutil.which("ffmpeg") is None:
        return None
    try:
        # Constant argv (same pattern as decode probes across the pipeline); availability
        # already gated by shutil.which above. Never a shell string.
        result = subprocess.run(["ffmpeg", "-hide_banner", "-version"],
                                capture_output=True, text=True, encoding="utf-8", errors="replace",
                                timeout=30, shell=False)
    except (OSError, subprocess.TimeoutExpired):
        return {"error": "ffmpeg -version failed to run"}
    return parse_version_output(result.stdout or "")


def parse_version_output(stdout: str) -> dict:
    banner = stdout.splitlines()
    version_line = banner[0] if banner else ""
    libass = LIBASS_LINE.search(stdout)
    enabled = bool(LIBASS_FLAG.search(stdout))
    return {"versionLine": version_line[:200],
            "libass": libass.group(1) if libass else ("unknown (enabled at build, no version line)" if enabled else "absent"),
            "libassEnabled": enabled or bool(libass)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--font", type=Path, help="font file the subtitles will use (existence check only; glyph coverage is G4's ㉛ preflight)")
    parser.add_argument("--auto-wrap", choices=("true", "false"), default="false",
                        help="true requires --auto-wrap-evidence; false is the conservative default (002-⑧)")
    parser.add_argument("--auto-wrap-evidence", help="quote or file path proving this renderer auto-wraps CJK")
    args = parser.parse_args()

    ffmpeg = probe_ffmpeg()
    if ffmpeg is None or "error" in (ffmpeg or {}):
        emit({"status": "blocked", "blockers": [{"type": "missing_toolchain",
              "detail": "ffmpeg not runnable; install it or declare P0C_FFMPEG_HOME on PATH. Never guess renderer facts without a probe."}]})
        return 2

    auto_wrap = args.auto_wrap == "true"
    if auto_wrap and not (args.auto_wrap_evidence and args.auto_wrap_evidence.strip()):
        emit({"status": "invalid", "error": "--auto-wrap true requires --auto-wrap-evidence (a quote or file path); claiming a capability without proof is forbidden (002-⑧)"})
        return 2

    profile = {
        "schemaVersion": "0.1", "skill": "subtitle-expert", "purpose": "subtitle_renderer_profile",
        "probedAt": now(),
        "host": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
        "ffmpeg": ffmpeg,
        "font": {"path": str(args.font), "exists": bool(args.font and args.font.is_file())} if args.font else None,
        "autoWrap": {"value": auto_wrap,
                     "evidence": args.auto_wrap_evidence if auto_wrap else None,
                     "basis": "measured evidence" if auto_wrap else "conservative default — CJK runs must carry explicit line breaks (002-⑧)"},
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = args.output_dir / PROFILE_NAME
    out.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not out.is_file() or out.stat().st_size == 0:
        emit({"status": "blocked", "blockers": [{"type": "write_failed", "detail": f"profile did not land on disk: {out}"}]})
        return 2
    emit({"status": "completed", "profile": str(out), "autoWrap": auto_wrap, "libass": ffmpeg.get("libass")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
