#!/usr/bin/env python3
"""Capability preflight — 能力预检申报（v1.34.0，用户令 2026-10-22）。

借鉴源＝OpenMontage 的 preflight 申报纪律（"缺口必须在开工前申报，不许跑到素材
阶段才暴雷"）；形态按我方卡片纪律重做。本脚本**零新探针逻辑**：每一项都调用各
专员脚本里已在实战使用的现成探针函数（importlib 按仓库内路径加载，单一事实源），
自己只做点名单、拼表、版本自增落盘。治的是我方病史：say/bl 静音回退、网易云
SSRF 走到那步才暴雷（zaku-003 台账②）、Freesound token 当场缺当场配。

规则（合同唯一事实源 references/capability-audit-contract.md）：
- 点名单按项目特征（G0 九问答案）生成：--profile bgm,narration,subtitles,transitions；
  未入单的项＝ not_applicable，不探测、不报缺（转场通常 G3 才定，届时增量重跑）。
- 申报不是预授权：有缺口仍出盘点、仍开工；缺口节点走到前必须补齐或人工拍板降级。
- 凭据只验在场、永不回显值（token 泄露三次换来的纪律）。
- 产物版本自增、永不覆盖（㉘转场能力档形制）。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

AUDIT_PREFIX = "能力盘点"
VALID_PROFILES = ("bgm", "narration", "subtitles", "transitions")
REPO_ROOT = Path(__file__).resolve().parents[3]
RUNTIME_DEPS_DOC = REPO_ROOT / "skill" / "p0-c-pipeline" / "references" / "runtime-dependencies.md"


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def next_versioned_path(output_dir: Path, prefix: str) -> Path:
    """产物版本自动递增、永不覆盖（issue ㉘）：与 transition_probe_host 故意重复此
    10 行，专员脚本保持零依赖单文件。"""
    pattern = re.compile(rf"^{re.escape(prefix)}-v(\d+)\.(\d+)\.json$")
    best = (0, 0)
    for candidate in output_dir.glob(prefix + "-v*.json"):
        match = pattern.match(candidate.name)
        if match:
            best = max(best, (int(match.group(1)), int(match.group(2))))
    if best == (0, 0):
        return output_dir / f"{prefix}-v0.1.json"
    return output_dir / f"{prefix}-v{best[0]}.{best[1] + 1}.json"


def load_sibling(skill: str, filename: str):
    """按路径加载专员脚本（现成探针的单一事实源，不复制探针逻辑）。"""
    path = REPO_ROOT / "skill" / skill / "scripts" / filename
    spec = importlib.util.spec_from_file_location(f"audit_{skill}_{filename[:-3]}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess | None:
    if shutil.which("ffmpeg") is None:
        return None
    return subprocess.run(["ffmpeg", "-hide_banner"] + args, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=30, shell=False)


# ---------------------------------------------------------------- 探针（全部转调现成入口）

def probe_ffmpeg_core() -> tuple[str, dict, str]:
    result = run_ffmpeg(["-version"])
    if result is None or result.returncode != 0:
        return "missing", {"check": "ffmpeg -version", "result": "not runnable"}, \
            "装 ffmpeg 或把 P0C_FFMPEG_HOME 下的 bin 加进 PATH（见运行依赖清单）"
    banner = (result.stdout or "").splitlines()
    return "ready", {"versionLine": banner[0][:160] if banner else ""}, ""


def probe_loudness_meter() -> tuple[str, dict, str]:
    result = run_ffmpeg(["-filters"])
    if result is None or result.returncode != 0:
        return "missing", {"check": "ffmpeg -filters", "result": "ffmpeg not runnable"}, \
            "同上——响度测量与归一化都依赖 ffmpeg 滤镜"
    filters = result.stdout or ""
    found = sorted(name for name in ("ebur128", "loudnorm", "volumedetect") if name in filters)
    if len(found) < 3:
        return "missing", {"check": "ffmpeg -filters", "found": found}, \
            "本 ffmpeg 缺响度滤镜（ebur128/loudnorm/volumedetect 未齐），响度闸会罢工点名"
    return "ready", {"check": "ffmpeg -filters", "found": found}, ""


def probe_subtitles_render() -> tuple[str, dict, str]:
    try:
        module = load_sibling("subtitle-expert", "subtitle_probe_renderer.py")
        facts = module.probe_ffmpeg()
    except Exception as error:  # noqa: BLE001 - 探针模块加载失败也是要如实申报的事实
        return "missing", {"check": "subtitle_probe_renderer.probe_ffmpeg", "error": str(error)[:160]}, \
            "字幕渲染探针无法执行——字幕专员的渲染能力探测是本项唯一事实源，先修环境再声称"
    if facts is None or "error" in facts:
        return "missing", {"check": "subtitle_probe_renderer.probe_ffmpeg", "result": facts}, \
            "ffmpeg 不可跑或版本横幅解析失败（见运行依赖清单）"
    return "ready", {"check": "subtitle_probe_renderer.probe_ffmpeg", "evidence": facts}, ""


FONT_PATH_RE = re.compile(r"(/[^\s|`\u4e00-\u9fff]*?\.(?:ttf|ttc|otf))")


def probe_card_fonts() -> tuple[str, dict, str]:
    """字体名单唯一事实源＝runtime-dependencies.md；深检（字形覆盖）留在装配闸 ㉛，
    盘点只申报文件在场性——两层各司其职，不在此重复造覆盖矩阵。"""
    try:
        text = RUNTIME_DEPS_DOC.read_text(encoding="utf-8")
    except OSError as error:
        return "missing", {"check": "runtime-dependencies.md", "error": str(error)[:120]}, "依赖清单文档缺失"
    paths = sorted(set(FONT_PATH_RE.findall(text)))
    present = [p for p in paths if Path(p).is_file()]
    evidence = {"listSource": str(RUNTIME_DEPS_DOC), "declared": paths, "present": present}
    if not paths:
        return "missing", evidence, "依赖清单里没登记任何字体路径——清单本身坏了"
    if not present:
        return "missing", evidence, "清单登记的字体在本机全都不存在——换机后按清单补装"
    return "ready", evidence, ""


def probe_freesound_token() -> tuple[str, dict, str]:
    """凭据在场性核验：只报哪个变量在场，值永不读取、永不回显。网络连通与检索
    实测归 music-expert 实战入口——本项如实写明没测的部分。"""
    names = ("MUSIC_EXPERT_FREESOUND_TOKEN", "P0C_FREESOUND_TOKEN")
    found = next((name for name in names if os.environ.get(name)), None)
    if found is None:
        return "missing", {"check": "env present only", "lookedFor": list(names)}, \
            "申请 Freesound token（freesound.org/apiv2/apply）写入 ~/.zshrc（MUSIC_EXPERT_FREESOUND_TOKEN），别让 AI 经手值"
    return "ready", {"check": "env present only", "found": found,
                     "note": "网络连通未在本盘点实测，找乐实战时由 music-expert 核验"}, ""


def probe_listen() -> tuple[str, dict, str]:
    try:
        module = load_sibling("music-expert", "music_listen_omni.py")
        bl_path = module.resolve_bl(None)
        available, detail = module.probe_capability(bl_path)
    except Exception as error:  # noqa: BLE001
        return "missing", {"check": "music_listen_omni.probe_capability", "error": str(error)[:160]}, \
            "听觉探针无法执行——试听环节将按『这台机器暂时没耳朵』停靠点处理"
    evidence = {"check": "music_listen_omni.probe_capability", "binary": bl_path, "detail": detail[:200]}
    if not available:
        return "missing", evidence, "装/登录百炼 CLI（bl auth login）或把 MUSIC_EXPERT_BL_BIN 指向兼容 CLI；不配也能剪，选曲退回人工挑曲"
    return "ready", evidence, ""


def probe_narration_voices(voices: list[str]) -> tuple[str, dict, str]:
    if shutil.which("say") is None:
        return "missing", {"check": "say", "result": "not on PATH"}, "本机（macOS）语音工具不在——改走授权神经 TTS 或人工录音（见运行依赖清单）"
    try:
        module = load_sibling("media-evidence-prep", "local_tts.py")
        installed = module.available_voices()
    except Exception as error:  # noqa: BLE001
        return "missing", {"check": "local_tts.available_voices", "error": str(error)[:160]}, \
            "音色清单探测失败——口播合成会在这一步罢工点名，不会静默换声"
    wanted = [v for v in voices if v]
    absent = [v for v in wanted if v not in installed]
    evidence = {"check": "local_tts.available_voices", "installedCount": len(installed),
                "requested": wanted, "absent": absent}
    if absent:
        return "missing", evidence, f"缺音色：{ '、'.join(absent) }——系统设置里下载该音色，或改点已在场的音色（绝不静默换声）"
    return "ready", evidence, ""


def probe_transitions() -> tuple[str, dict, str]:
    try:
        module = load_sibling("transition-expert", "transition_probe_host.py")
        facts = module.probe()
    except Exception as error:  # noqa: BLE001
        return "missing", {"check": "transition_probe_host.probe", "error": str(error)[:160]}, \
            "转场能力探针无法执行——G3 出叠化/黑场计划前必须有一份真能力档"
    if not facts.get("available"):
        return "missing", {"check": "transition_probe_host.probe", "result": "ffmpeg not runnable"}, \
            "先修 ffmpeg（见运行依赖清单），转场能力档以实测为准、不猜"
    xfade = bool(facts.get("xfadeAvailable"))
    evidence = {"check": "transition_probe_host.probe", "xfadeAvailable": xfade,
                "transitionCount": len(facts.get("xfadeTransitions", []))}
    if not xfade:
        return "missing", evidence, "本 ffmpeg 无 xfade——计划只能硬切，或换带 xfade 的构建（探测不过不声称，能力档归转场专员）"
    return "ready", evidence, ""


# ---------------------------------------------------------------- 点名单与拼表

ITEM_PLAN = {
    "ffmpeg-core": {"label": "剪辑与渲染引擎（ffmpeg/ffprobe）", "affects": ["G2", "G4", "G5"], "profiles": None},
    "loudness-meter": {"label": "测响度的尺（ebur128/loudnorm）", "affects": ["G4", "G5"], "profiles": None},
    "bgm-search": {"label": "找乐通道（Freesound 凭据在场）", "affects": ["G1"], "profiles": ("bgm",)},
    "listen": {"label": "这台机器的耳朵（试听笔记模型）", "affects": ["G1"], "profiles": ("bgm",)},
    "narration-voices": {"label": "配音音色（系统语音）", "affects": ["G2", "G4"], "profiles": ("narration",)},
    "subtitles-render": {"label": "字幕烧录渲染", "affects": ["G4", "G5"], "profiles": ("subtitles",)},
    "card-fonts": {"label": "字卡/字幕字体在场", "affects": ["G4"], "profiles": ("subtitles",)},
    "transitions-xfade": {"label": "转场引擎（ffmpeg xfade）", "affects": ["G3", "G4"], "profiles": ("transitions",)},
}

NOT_APPLICABLE_NOTE = {
    "transitions-xfade": "本轮未涉（转场通常 G3 计划才定，届时增量重跑本盘点）",
}


def run_audit(profile: set[str], voices: list[str]) -> list[dict]:
    items = []
    for item_id, meta in ITEM_PLAN.items():
        involved = meta["profiles"] is None or bool(profile & set(meta["profiles"]))
        if not involved:
            items.append({"id": item_id, "labelPlain": meta["label"], "status": "not_applicable",
                          "evidence": {"probed": False},
                          "affects": meta["affects"],
                          "note": NOT_APPLICABLE_NOTE.get(item_id, "不在本轮点名单内")})
            continue
        if item_id == "narration-voices":
            status, evidence, remedy = probe_narration_voices(voices)
        elif item_id == "transitions-xfade":
            status, evidence, remedy = probe_transitions()
        else:
            status, evidence, remedy = {
                "ffmpeg-core": probe_ffmpeg_core,
                "loudness-meter": probe_loudness_meter,
                "bgm-search": probe_freesound_token,
                "listen": probe_listen,
                "subtitles-render": probe_subtitles_render,
                "card-fonts": probe_card_fonts,
            }[item_id]()
        item = {"id": item_id, "labelPlain": meta["label"], "status": status,
                "evidence": evidence, "affects": meta["affects"]}
        if status == "missing":
            item["remedy"] = remedy
        items.append(item)
    return items


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path, help="工作台/<projectId> 目录")
    parser.add_argument("--profile", default="", help="逗号分隔：" + ",".join(VALID_PROFILES) + "（G0 九问特征；转场常留待 G3 增量）")
    parser.add_argument("--voice", action="append", default=[], help="项目点名的配音音色（可重复）")
    parser.add_argument("--output-dir", type=Path, default=None, help="默认 <project>/G0-素材包")
    args = parser.parse_args()

    project = args.project
    if not project.is_dir():
        emit({"status": "blocked", "blockers": [{"type": "missing_project", "detail": f"项目目录不在盘上: {project}"}]})
        return 2
    profile_raw = [p.strip() for p in (args.profile or "").split(",") if p.strip()]
    bad = [p for p in profile_raw if p not in VALID_PROFILES]
    if bad:
        emit({"status": "blocked", "blockers": [{"type": "bad_profile", "detail": f"未知特征 {bad}，合法集合 {list(VALID_PROFILES)}"}]})
        return 2
    profile = set(profile_raw)

    output_dir = args.output_dir or (project / "G0-素材包")
    output_dir.mkdir(parents=True, exist_ok=True)

    items = run_audit(profile, args.voice)
    summary = {
        "ready": sum(1 for i in items if i["status"] == "ready"),
        "missing": sum(1 for i in items if i["status"] == "missing"),
        "notApplicable": sum(1 for i in items if i["status"] == "not_applicable"),
        "missingIds": [i["id"] for i in items if i["status"] == "missing"],
    }
    report = {
        "schemaVersion": "0.1", "kind": "capability-audit",
        "skill": "p0-c-pipeline", "projectId": project.name,
        "profile": sorted(profile), "probedAt": now(),
        "host": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
        "items": items, "summary": summary,
        "basis": "能力预检申报——探针全部转调各专员现成入口（合同见 references/capability-audit-contract.md）；申报非预授权，缺口节点前必须补齐或人工拍板降级",
    }
    out = next_versioned_path(output_dir, AUDIT_PREFIX)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not out.is_file() or out.stat().st_size == 0:
        emit({"status": "blocked", "blockers": [{"type": "write_failed", "detail": f"盘点未落盘: {out}"}]})
        return 2
    emit({"status": "completed", "file": str(out), "probedAt": report["probedAt"],
          "summary": summary,
          "missing": [{"id": i["id"], "label": i["labelPlain"], "affects": i["affects"]} for i in items if i["status"] == "missing"]})
    return 0


if __name__ == "__main__":
    sys.exit(main())
