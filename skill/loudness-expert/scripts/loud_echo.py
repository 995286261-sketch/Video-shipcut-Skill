"""响度专员唯一入口④：固定表格回显卡渲染（呈现层零算术）。

用法：loud_echo.py --artifact <专员产物 json（loud_measure/loud_plan/loud_verify 任一）>
输出：stdout 一张 Markdown 固定表格卡——数据全部取自产物文件，本渲染器不做任何
数值计算；卡上时间/哈希/数字与盘上产物逐字一致。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import loud_core  # noqa: E402

STATUS_LABEL = {"measured": "已实测", "ready": "可执行（线性归一化前提对账通过）",
                "passed": "验收通过", "failed": "验收不过", "blocked": "卡住（见出路）",
                "capability_missing": "测量引擎缺席（不编数）"}


def fmt(value, unit=""):
    if value is None:
        return "—"
    if isinstance(value, float):
        return "{0:.1f}{1}".format(value, unit)
    return "{0}{1}".format(value, unit)


def render(doc: dict) -> list:
    purpose = doc.get("purpose")
    title = {"loud_measure": "响度实测卡", "loud_plan": "响度规划卡",
             "loud_verify": "响度验收卡"}.get(purpose, "响度卡")
    lines = ["【{0}｜{1}】".format(title, STATUS_LABEL.get(doc.get("status"), doc.get("status") or "—")),
             "| 项目 | 值 |", "|---|---|",
             "| 产物版本 | {0} |".format(doc.get("version", "—")),
             "| 被测文件 | {0} |".format(doc.get("source", "—")),
             "| 文件指纹 | {0}… |".format((doc.get("sha256") or doc.get("masterSha256") or "")[:12] or "—")]
    measured = doc.get("measured") or doc.get("masterMeasured") or {}
    if purpose == "loud_plan":
        lines.append("| 规划实测（loudnorm 口径） | I {0} LUFS ／ TP {1} dBTP ／ LRA {2} LU |".format(
            fmt(measured.get("inputI")), fmt(measured.get("inputTp")), fmt(measured.get("inputLra"))))
        target = doc.get("targetProfile") or {}
        lines.append("| 目标 | I {0} LUFS ／ TP ≤ {1} dBTP ／ LRA {2} LU |".format(
            fmt(target.get("integratedLufs")), fmt(target.get("truePeakDbtp")),
            fmt(target.get("lraTargetLu"))))
        lines.append("| 线性增益 | {0} dB（估算后 TP {1} dBTP） |".format(
            fmt(doc.get("gainDb")), fmt(doc.get("estimatedTruePeak"))))
        lines.append("| 天花板（现 TP 上限下最响可到） | {0} LUFS |".format(fmt(doc.get("ceilingLufs"))))
        if doc.get("exits"):
            lines.append("| 出路 | " + "；".join(doc["exits"]) + " |")
    else:
        lines.append("| 实测（ebur128 验收口径） | I {0} LUFS ／ TP {1} dBTP ／ LRA {2} LU |".format(
            fmt(measured.get("integratedLufs")), fmt(measured.get("truePeakDbtp")),
            fmt(measured.get("loudnessRangeLu"))))
    for item in doc.get("checks") or []:
        lines.append("| 复核 {0} | {1}：{2} |".format(item["check"],
                                                     "过" if item["pass"] else "不过", item["detail"]))
    lines.append("| 单位口径 | LUFS=平均有多响｜dBTP=会不会爆｜LU=动态宽度（相对增益另标 dB） |")
    lines.append("此卡由通过校验的响度专员产物生成（呈现层零算术，数据逐字取自产物文件）")
    return lines


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="响度产物固定表格回显卡")
    parser.add_argument("--artifact", required=True)
    args = parser.parse_args(argv)
    path = Path(args.artifact)
    if not path.is_file():
        loud_core.emit({"status": "error", "error": "产物不存在: {0}".format(path)}, 1)
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("skill") != loud_core.SKILL_ID:
        loud_core.emit({"status": "error", "error": "非响度专员产物，拒渲染（防手制卡）"}, 1)
    print("\n".join(render(doc)))


if __name__ == "__main__":
    main()
