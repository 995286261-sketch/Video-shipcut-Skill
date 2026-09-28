"""响度专员唯一入口①：单文件 ebur128 实测报告（验收口径）。

用法：loud_measure.py --input <音频/视频文件> --output-dir <目录> [--project-id <ID>]
产物：《响度-实测报告-v0.N.json》——I/TP/LRA 全部实测，无 ffmpeg 即结构化
capability_missing 摊牌（exit 2），绝不出估计数。
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import loud_core  # noqa: E402


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="响度实测（ebur128 验收口径）")
    parser.add_argument("--input", required=True, help="待测音频/视频文件")
    parser.add_argument("--output-dir", required=True, help="报告目录（版本自增，不覆盖）")
    parser.add_argument("--project-id", default=None)
    args = parser.parse_args(argv)

    src = Path(args.input)
    if not src.is_file():
        loud_core.emit({"status": "error", "error": "输入文件不存在: {0}".format(src)}, 1)
    if not loud_core.ffmpeg_available():
        loud_core.emit({"status": "capability_missing",
                        "capability": loud_core.capability_missing(),
                        "note": "无实测即无报告；不得由人代填数字"}, 2)

    measured = loud_core.measure_ebur128(src)
    if measured["integratedLufs"] is None or measured["truePeakDbtp"] is None:
        loud_core.emit({"status": "error",
                        "error": "ebur128 未产出可读汇总（探测失败，非结果）",
                        "raw": measured}, 1)

    out_path, version = loud_core.next_versioned(Path(args.output_dir),
                                                 "响度-实测报告", ".json")
    doc = loud_core.artifact_header("loud_measure", args.project_id, src)
    doc.update({"version": version, "output": str(out_path),
                "measured": measured,
                "sha256": loud_core.sha256_file(src),
                "status": "measured",
                "measuredAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "unitsNote": "LUFS=集成响度（平均有多响）；dBTP=真峰值（会不会爆）；LU=动态范围宽度"})
    out_path.write_text(__import__("json").dumps(doc, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    loud_core.emit(doc, 0)


if __name__ == "__main__":
    main()
