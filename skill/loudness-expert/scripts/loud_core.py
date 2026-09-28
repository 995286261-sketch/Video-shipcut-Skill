"""loudness-expert 共享内核（只许 import，不单独调用）。

三件事：ebur128 验收口径测量、loudnorm 规划口径测量与线性可行性算术、
版本命名（多轮产物永不静默覆盖，㉘ 先例）。

口径纪律（references/loudness-contract.md 为唯一事实源）：
- 规划口径 = loudnorm pass1（print_format=json）——它产出的 input_i/input_tp/
  input_lra/input_thresh 正是喂给 linear=true 第二遍的 measured_* 同源数，
  规划与执行零换算；
- 验收口径 = ebur128——交付侧独立测量，与执行链不同滤镜，互不背书；
- 引擎可以缺（capability_missing 结构化摊牌），事实不能编（无实测不出数）。

依赖全靠 PATH（ffmpeg/ffprobe，插件可迁移四标准，禁硬编码主机路径）；
ffmpeg 缺席=结构化 capability_missing，不猜数。
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

SKILL_ID = "loudness-expert"
SCHEMA_VERSION = "0.1"

# 目标档（合同 §2；video 档=现行 g4 实链验证值，podcast 档=ffmpeg-normalize 预设调研值）
PROFILES = {
    "video": {"integratedLufs": -14.0, "truePeakDbtp": -1.5, "lraTargetLu": 9.0},
    "podcast": {"integratedLufs": -16.0, "truePeakDbtp": -2.0, "lraTargetLu": 7.0},
}
# 验收容差（合同 §3 工程惯例常数，随报告如实带出，不是隐藏默认）
DEFAULT_TOLERANCE_LU = 1.0
# 线性模式实测 TP 允许超出 TP 上限的余量（loudnorm 保证的是估算值，非硬限幅）
TP_SLACK_DB = 0.3


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def capability_missing() -> dict:
    """结构化摊牌块——无能力如实声明，下游不得把缺能力当达标。"""
    return {
        "available": False,
        "engine": "ffmpeg",
        "probe": "which ffmpeg",
        "hint": ("ffmpeg 不在 PATH。装好或导出 PATH 后重跑本入口；"
                 "不得用估计数替代实测（能力可以缺、事实不能编）。"),
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(str(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def parse_ebur128_text(text: str) -> dict:
    """纯函数：ebur128 汇总文本 → I/TP/LRA（取最后一次汇总，拒绝静音哨兵值）。"""
    integrated, true_peak, lra = None, None, None
    matches = re.findall(r"I:\s+(-?\d+\.?\d*)\s*LUFS", text)
    if matches:
        value = float(matches[-1])
        integrated = None if value <= -69.9 else value
    matches = re.findall(r"True peak:\s*\n?\s*Peak:\s+(-?\d+\.?\d*)\s*dBFS", text)
    if matches:
        value = float(matches[-1])
        true_peak = None if value <= -99.9 else value
    matches = re.findall(r"Loudness range:\s*\n?\s*LRA:\s+(-?\d+\.?\d*)\s*LU", text)
    if matches:
        lra = float(matches[-1])
    return {"integratedLufs": integrated, "truePeakDbtp": true_peak, "loudnessRangeLu": lra}


def measure_ebur128(path: Path) -> dict:
    """验收口径：ebur128 实测（解析层为纯函数 parse_ebur128_text，单测无 ffmpeg 也锁死）。"""
    result = subprocess.run(["ffmpeg", "-hide_banner", "-nostats",
                             "-i", str(path),
                             "-filter:a", "ebur128=peak=true",
                             "-f", "null", "-"],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=300)
    parsed = parse_ebur128_text((result.stderr or "") + (result.stdout or ""))
    parsed["engine"] = "ffmpeg-ebur128"
    return parsed


def render_with_chain(path: Path, chain: str, out_path: Path, timeout: int = 300) -> bool:
    """专员自测用：把规划 chain 真跑一遍产出归一化文件（端到端自证链可用）。
    注意：接线后 G4 的执行由节点专员自己做，节点零 import 本函数——跨专员只走
    产物文件握手（chain 字符串与计划 JSON）。"""
    result = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-y",
                             "-i", str(path),
                             "-af", chain,
                             "-vn", str(out_path)],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=timeout)
    return result.returncode == 0 and Path(out_path).is_file()


def measure_loudnorm_pass1(path: Path, profile: dict):
    """规划口径：loudnorm pass1 的 print_format=json 四实测（measured_* 同源数）。"""
    chain = "loudnorm=I={}:TP={}:LRA={}:print_format=json".format(
        profile["integratedLufs"], profile["truePeakDbtp"], profile["lraTargetLu"])
    result = subprocess.run(["ffmpeg", "-hide_banner", "-nostats",
                             "-i", str(path),
                             "-af", chain,
                             "-f", "null", "-"],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=300)
    text = (result.stderr or "") + (result.stdout or "")
    start = text.rfind("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        blob = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    required = ("input_i", "input_tp", "input_lra", "input_thresh")
    if any(key not in blob for key in required):
        return None
    return {"engine": "ffmpeg-loudnorm-pass1",
            "inputI": float(blob["input_i"]), "inputTp": float(blob["input_tp"]),
            "inputLra": float(blob["input_lra"]), "inputThresh": float(blob["input_thresh"])}


def linear_feasibility(measured: dict, profile: dict) -> dict:
    """纯函数：linear=true 前提条件对账 + ffmpeg-normalize 式可修数值算术。

    官方文档（ffmpeg filters 8.97）：linear 要求目标 LRA 不低于源 LRA、且线性
    增益后的真峰值不超 TP 上限，任一不满足滤镜**静默退回 dynamic**——所以这里
    必须先算再放行，绝不把回退交给执行者事后发现。
    """
    gain = profile["integratedLufs"] - measured["inputI"]
    estimated_tp = measured["inputTp"] + gain
    reasons, exits = [], []
    tp_ok = estimated_tp <= profile["truePeakDbtp"] + 1e-9
    lra_ok = measured["inputLra"] <= profile["lraTargetLu"] + 1e-9
    ceiling = profile["truePeakDbtp"] - measured["inputTp"] + measured["inputI"]
    if not tp_ok:
        reasons.append("true-peak")
        exits.append("把 TP 上限提到至少 {:.1f} dBTP（线性增益 {:.2f} dB 后估算 TP 将到 {:.2f}）"
                     .format(estimated_tp, gain, estimated_tp))
        exits.append("把目标响度降到至多 {:.1f} LUFS（保住现 TP 上限 {:.1f}）"
                     .format(ceiling, profile["truePeakDbtp"]))
        exits.append("先压缩后测：源峰均比过高属素材天花板，先跑压缩链再对本产物重新规划")
    if not lra_ok:
        reasons.append("loudness-range")
        exits.append("把 LRA 目标提到至少 {:.1f} LU（当前源 LRA {:.1f}）"
                     .format(measured["inputLra"], measured["inputLra"]))
        exits.append("先压缩收窄动态后重新规划")
    return {"gainDb": round(gain, 2), "estimatedTruePeak": round(estimated_tp, 2),
            "feasible": tp_ok and lra_ok, "blockedReasons": reasons,
            "exits": exits, "ceilingLufs": round(ceiling, 1)}


def linear_chain(profile: dict, measured: dict) -> str:
    """第二遍线性归一化滤镜串（执行者逐字使用，不许改写参数）。"""
    return ("loudnorm=I={}:TP={}:LRA={}"
            ":measured_I={}:measured_TP={}:measured_LRA={}:measured_thresh={}"
            ":offset=0.0:linear=true:print_format=json"
            .format(profile["integratedLufs"], profile["truePeakDbtp"],
                    profile["lraTargetLu"], measured["inputI"], measured["inputTp"],
                    measured["inputLra"], measured["inputThresh"]))


def next_versioned(directory: Path, prefix: str, suffix: str):
    """版本命名：扫 v0.N 取下一号，永不覆盖旧文件（㉘ 先例，import-only）。"""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    pattern = re.compile(r"^{0}-v0\.(\d+){1}$".format(re.escape(prefix), re.escape(suffix)))
    highest = 0
    for entry in directory.iterdir():
        match = pattern.match(entry.name)
        if match:
            highest = max(highest, int(match.group(1)))
    version = "v0.{0}".format(highest + 1)
    return directory / "{0}-{1}{2}".format(prefix, version, suffix), version


def emit(payload: dict, code: int = 0) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if code:
        raise SystemExit(code)


def artifact_header(purpose: str, project_id, source: Path) -> dict:
    # source 落盘为解析后的绝对路径：调用方传相对路径（真实编排层从仓库根起跑）
    # 时，产物仍是自描述的可对账证据（09-28 zaku 实测彩排抓出）。
    return {"skill": SKILL_ID, "purpose": purpose, "schemaVersion": SCHEMA_VERSION,
            "projectId": project_id, "source": str(Path(source).resolve())}
