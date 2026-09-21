#!/usr/bin/env python3
"""Probe this host's ffmpeg xfade facts and emit a capability profile JSON.

Measurable facts: ffmpeg availability and version banner, whether the xfade
filter exists, and its exact transition-name list (parsed from
`ffmpeg -h filter=xfade`). xfade needs ffmpeg >= 4.3 — but the version number
is never the claim, the parsed filter help IS the evidence. Anything that
cannot be parsed stays absent/unknown rather than guessed
（能力可以缺、事实不能编；照 subtitle-expert probe 的误解析教训：只认结构化的行，
不把 configuration 参数行当事实）。

The profile is an INPUT to transition_validate_plan.py: a plan that wants
叠化 without a probe profile is refused ("先探测，再声称").
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

PROFILE_NAME = "转场-宿主能力档-v0.1.json"
VERSION_LINE = re.compile(r"ffmpeg version (\S+)")
# `ffmpeg -h filter=xfade` lists constants as indented rows: name, value, flags
# (starting "..FV"), description. Only accept that exact shape (mirrors the
# LIBASS_LINE lesson).
TRANSITION_ROW = re.compile(r"^\s{3,}([a-z][a-z0-9]+)\s+-?\d+\s+\.\.FV", re.M)


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def run_ffmpeg(args: list) -> subprocess.CompletedProcess | None:
    if shutil.which("ffmpeg") is None:
        return None
    # Constant argv across the pipeline; availability gated by shutil.which. Never a shell string.
    return subprocess.run(["ffmpeg"] + args, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=30, shell=False)


def parse_version_banner(stdout: str) -> dict:
    match = VERSION_LINE.search(stdout or "")
    banner = (stdout or "").splitlines()
    return {"versionLine": banner[0][:200] if banner else "",
            "version": match.group(1) if match else "unknown"}


def parse_xfade_names(stdout: str) -> list:
    # "custom" 是自定义表达式的开关值，不是可用的转场名。
    return sorted({m.group(1) for m in TRANSITION_ROW.finditer(stdout or "")} - {"custom"})


def probe() -> dict:
    version = run_ffmpeg(["-hide_banner", "-version"])
    if version is None or version.returncode != 0:
        return {"available": False}
    help_run = run_ffmpeg(["-hide_banner", "-h", "filter=xfade"])
    help_out = (help_run.stdout or "") if help_run else ""
    xfade_available = help_run is not None and help_run.returncode == 0 and "xfade" in help_out
    names = parse_xfade_names(help_out) if xfade_available else []
    return {"available": True,
            "banner": parse_version_banner(version.stdout),
            "xfadeAvailable": xfade_available,
            "xfadeTransitions": names}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    facts = probe()
    if not facts.get("available"):
        emit({"status": "blocked", "blockers": [{"type": "missing_toolchain",
              "detail": "ffmpeg not runnable; install it or declare P0C_FFMPEG_HOME on PATH. Never guess transition facts without a probe."}]})
        return 2

    names = facts["xfadeTransitions"]
    profile = {
        "schemaVersion": "0.1", "skill": "transition-expert", "purpose": "transition_host_profile",
        "probedAt": now(),
        "host": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
        "ffmpeg": facts["banner"],
        "xfade": {"available": facts["xfadeAvailable"], "transitions": names,
                  "evidence": "ffmpeg -hide_banner -h filter=xfade (parsed constant rows)"},
        "capabilities": {
            "dissolve": "dissolve" in names,
            "wipe": "wipeleft" in names,
            "fadeBlackBoundary": "fadeblack" in names,
        },
        "basis": "measured probe — capabilities not listed here must not be claimed by any plan",
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = args.output_dir / PROFILE_NAME
    out.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not out.is_file() or out.stat().st_size == 0:
        emit({"status": "blocked", "blockers": [{"type": "write_failed", "detail": f"profile did not land on disk: {out}"}]})
        return 2
    emit({"status": "completed", "profile": str(out),
          "xfadeAvailable": profile["xfade"]["available"], "transitionCount": len(names),
          "dissolve": profile["capabilities"]["dissolve"]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
