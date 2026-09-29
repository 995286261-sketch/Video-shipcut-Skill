#!/usr/bin/env python3
"""Validate a G5 delivery bundle without needing its raw source media."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path


REQUIRED = ("final-video.mp4", "cover.jpg", "subtitles.srt", "subtitle-srt-check.json", "transition-audit.json", "source-timecode-list.json", "edit-plan.json", "edit-timeline.md", "export-config.json", "metadata-validation-report.json", "human-review-decision.json", "delivery-manifest.json", "README.md", "failure-samples/README.md")
CONTRACT_FIELDS = ("schemaVersion", "projectId", "sourceProbe", "segments", "editPlan", "artifacts", "qaReport", "humanReviewPoints", "evidenceRefs", "warnings", "status", "finishedAt")
QA_CHECKS = ("decode", "videoCodec", "dimensions", "fps", "audio", "duration", "blackFrames", "silence", "duplicateSegments", "cover")


def check_delivery_srt(bundle: Path, errors: list[str]) -> None:
    """SRT format rules belong to subtitle-expert (issue ㊍: a 10× timebase slip once
    shipped in a bundle). G5 holds no private timestamp regex; it consumes the
    specialist's report — same artifact-handshake pattern as G0's BGM registration
    receipt: report present, status passed, and its sha256 still matches the bundle
    file (freshness, per ⑦ lesson: a receipt must describe THIS file)."""
    report_path = bundle / "subtitle-srt-check.json"
    if not report_path.is_file():
        errors.append("missing subtitle-srt-check.json — run subtitle-expert/scripts/subtitle_check_srt.py on subtitles.srt and file the report before closing QA")
        return
    report = load(report_path)
    if report.get("skill") != "subtitle-expert" or report.get("purpose") != "subtitle_check_srt":
        errors.append("subtitle-srt-check.json is not a subtitle-expert check report")
        return
    if report.get("status") != "passed":
        errors.append(f"subtitles.srt failed subtitle-expert check: status={report.get('status')} {('; '.join(report.get('errors', [])) or report.get('error') or '')[:200]}")
        return
    srt = bundle / "subtitles.srt"
    if not srt.is_file():
        errors.append("subtitle-srt-check.json present but subtitles.srt missing")
        return
    if str(report.get("sha256", "")).upper() != digest(srt):
        errors.append("subtitle-srt-check.json is stale: recorded sha256 does not match the bundle's subtitles.srt (re-run the specialist checker after any edit)")


def check_transition_audit(bundle: Path, errors: list[str]) -> None:
    """转场执行==批准的唯一物证（transition-expert 批③握手，照 subtitle-srt-check 模式）：
    报告身份、status passed、且登记的成片哈希就是包内这一支 final-video.mp4——
    报告若指向旧成片即 stale。无转场项目该报告照常存在（transitions: []、passed）。"""
    report_path = bundle / "transition-audit.json"
    if not report_path.is_file():
        errors.append("missing transition-audit.json — run transition-expert/scripts/transition_report.py on the G4 assembly record and file the report before closing QA")
        return
    report = load(report_path)
    if report.get("skill") != "transition-expert" or report.get("purpose") != "transition_check":
        errors.append("transition-audit.json is not a transition-expert check report")
        return
    if report.get("status") != "passed":
        errors.append(f"transition audit failed: {('; '.join(report.get('errors', [])) or '')[:200]}")
        return
    if report.get("gridInvariant") is not True:
        errors.append("transition-audit.json does not assert gridInvariant — refuse to deliver a timeline the directive never promised")
    video = bundle / "final-video.mp4"
    recorded = str((report.get("master") or {}).get("sha256") or "").upper()
    if video.is_file() and recorded and recorded != digest(video):
        errors.append("transition-audit.json is stale: recorded master sha256 does not match the bundle's final-video.mp4 (re-run the audit after any re-render)")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def parse_ebur128_summary(text: str) -> dict:
    """合同 §4 验收口径解析（跨专员零 import，与 loudness-expert/g4_assemble 同源镜像、
    合同改时三处同步）：取最后一次汇总、拒绝静音哨兵。"""
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


def measure_ebur128(path: Path) -> dict:
    result = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
                             "-filter:a", "ebur128=peak=true", "-f", "null", "-"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    return parse_ebur128_summary((result.stderr or "") + (result.stdout or ""))


def check_loudness_audit(bundle: Path, plan: dict, review: dict, errors: list[str], allow_pending_acceptance: bool = False) -> None:
    """响度接线批四（2026-09-28，丙口径交付侧收口）。条件 REQUIRED=时代编码在产物里：
    包内 edit-plan.json 带 packagingDecisions.loudnessTarget（批二起新合同计划必带，
    validate_g3_plan 机验）即必须交《响度-验收审计》入册；批二前封存的老包无此字段、
    不追溯（R3）——sinjuku 基线不伤、也不许为老包补生成审计（补=造假）。
    校验四件：身份头；status ∈ passed/disclosed-exceedance（failed 拒关单；disclosed
    必须人工 acceptedWarnings 点名响度=知情接受留痕，永不静默）；审计对账的目标档==包内
    计划镜像（三口径在交付侧闭合）；masterSha256==包内成片实测（报告必须说这一支片子）。"""
    target = (plan.get("packagingDecisions") or {}).get("loudnessTarget")
    report_path = bundle / "loudness-audit.json"
    if not isinstance(target, dict):
        return
    if not report_path.is_file():
        errors.append("missing loudness-audit.json — run loudness-expert/scripts/loud_verify.py "
                      "(--plan 响度-归一化计划 --master final-video.mp4 --assembly-record G4装配记录) "
                      "and file the report in the bundle (响度批四)")
        return
    report = load(report_path)
    if report.get("skill") != "loudness-expert" or report.get("purpose") != "loud_verify":
        errors.append("loudness-audit.json is not a loudness-expert verification report")
        return
    status = report.get("status")
    if status == "failed":
        errors.append(f"loudness audit failed: {json.dumps(report.get('checks', []), ensure_ascii=False)[:180]}")
    elif status == "disclosed-exceedance":
        accepted = review.get("acceptedWarnings") or []
        if not any(("响度" in str(w)) or ("loudness" in str(w).lower()) for w in accepted) and not allow_pending_acceptance:
            errors.append("disclosed-exceedance needs explicit human acceptance: acceptedWarnings must name 响度/loudness "
                          "(批四丙口径——超差摊开经人知情接受才关单，不静默)")
    elif status != "passed":
        errors.append(f"loudness-audit.json status={status!r} not accepted (only passed/disclosed-exceedance)")
    if report.get("targetProfile") != target:
        errors.append(f"loudness-audit.json targetProfile {report.get('targetProfile')!r} != edit-plan "
                      f"packagingDecisions.loudnessTarget {target!r} — 验收拿的是另一档计划（卡说 X，机器渲 X）")
    video = bundle / "final-video.mp4"
    if video.is_file() and str(report.get("masterSha256", "")).upper() != digest(video):
        errors.append("loudness-audit.json is stale: recorded masterSha256 does not match the bundle's "
                      "final-video.mp4 (re-run loud_verify after any re-render)")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest().upper()


def inside(bundle: Path, relative: str) -> Path | None:
    path = (bundle / relative).resolve()
    return path if path == bundle or bundle in path.parents else None


def check_artifact(bundle: Path, artifact: dict, errors: list[str]) -> None:
    path = artifact.get("path")
    target = inside(bundle, path) if isinstance(path, str) else None
    if not target or not target.is_file():
        errors.append(f"missing artifact: {path}")
    elif artifact.get("sha256") and digest(target) != artifact["sha256"].upper():
        errors.append(f"sha256 mismatch: {path}")


def fraction(value: str | None) -> float | None:
    if not value or value == "0/0": return None
    numerator, denominator = value.split("/", 1)
    return float(numerator) / float(denominator) if float(denominator) else None


def fps_reconciliation_error(expected, actual_fps):
    """⑧丙 (转场实跑，用户 09-24 裁决): export-config 声明 fps 与成片实探 fps 必对账、
    不可跳过——缺声明本身就是病（24fps 事故当年正是"缺声明=不比对"放行的）。"""
    if expected is None:
        return "export-config.video.fps is missing (⑧丙: media acceptance never skips the fps reconciliation)"
    if actual_fps is None or abs(float(actual_fps) - float(expected)) > .1:
        return "final-video.mp4 fps does not match export-config"
    return None


def validate_media(bundle: Path, export: dict, errors: list[str]) -> dict:
    """⑭（zaku-003 测后批，用户 09-29 定案）起返回机器实测事实（measured facts），供
    --report-out 逐字填进 checks——报告只能写机器真正量过的数，没跑的一律「待补」，
    能力可缺、事实不能编。"""
    measured: dict = {}
    video = bundle / "final-video.mp4"
    result = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        errors.append("final-video.mp4 cannot be fully decoded")
        measured["decode"] = "fail"
    else:
        measured["decode"] = "pass"
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels", "-of", "json", str(video)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if probe.returncode:
        errors.append("final-video.mp4 cannot be probed")
    else:
        streams = json.loads(probe.stdout).get("streams", [])
        visual = next((item for item in streams if item.get("codec_type") == "video"), None)
        audio = [item for item in streams if item.get("codec_type") == "audio"]
        if visual:
            measured["videoCodec"] = str(visual.get("codec_name"))
            measured["dimensions"] = f"{visual.get('width')}x{visual.get('height')}"
            measured["fps"] = str(visual.get("r_frame_rate"))
        if len(audio) == 1:
            measured["audio"] = f"{audio[0].get('codec_name')} {audio[0].get('sample_rate')}Hz {audio[0].get('channels')}ch"
        elif audio:
            measured["audio"] = f"{len(audio)} 条音轨（多音轨需人审确认分发意图）"
        profile = export.get("video", {})
        audio_profile = export.get("audio", {})
        if not visual:
            errors.append("final-video.mp4 has no video stream")
        else:
            if profile.get("codec") and visual.get("codec_name") != profile["codec"]:
                errors.append("final-video.mp4 codec does not match export-config")
            if profile.get("width") and visual.get("width") != profile["width"] or profile.get("height") and visual.get("height") != profile["height"]:
                errors.append("final-video.mp4 dimensions do not match export-config")
            fps_error = fps_reconciliation_error(profile.get("fps"), fraction(visual.get("r_frame_rate")))
            if fps_error:
                errors.append(fps_error)
            actual_ms = round(float(json.loads(probe.stdout).get("format", {}).get("duration", 0)) * 1000)
            measured["durationMs"] = actual_ms
            expected_ms = profile.get("durationActualMs")
            if expected_ms and abs(actual_ms - expected_ms) > 150:
                errors.append("final-video.mp4 duration does not match export-config")
        if audio_profile.get("codec") and (len(audio) != 1 or audio[0].get("codec_name") != audio_profile["codec"]):
            errors.append("final-video.mp4 audio does not match export-config")
        # 响度批四：--media 复测对账——《响度-验收审计》记的数必须能在包内这一支成片上
        # 用同口径（ebur128）复现（合同 §4 同文件双口径差 >0.5 LU=引擎异常；这里是同口径
        # 复测，>0.3 即报告与成片不是同一份东西/引擎漂移，拒收）。哈希新鲜由主校验管，
        # 数值可复现由本复测管——两层各拦各的病。
        audit_path = bundle / "loudness-audit.json"
        if audit_path.is_file() and visual:
            try:
                audit = load(audit_path)
            except json.JSONDecodeError:
                audit = {}
            recorded = audit.get("masterMeasured") or {}
            if audit.get("purpose") == "loud_verify" and recorded.get("integratedLufs") is not None:
                remeasured = measure_ebur128(video)
                if remeasured["integratedLufs"] is None or abs(remeasured["integratedLufs"] - recorded["integratedLufs"]) > 0.3:
                    errors.append(f"loudness audit does not reproduce on --media re-measure: recorded {recorded['integratedLufs']} LUFS, re-measured {remeasured['integratedLufs']} LUFS (report is not about this file, or engine drift)")
                elif recorded.get("truePeakDbtp") is not None and remeasured["truePeakDbtp"] is not None \
                        and abs(remeasured["truePeakDbtp"] - recorded["truePeakDbtp"]) > 0.3:
                    errors.append("loudness audit true-peak does not reproduce on --media re-measure — re-run loud_verify before sealing")
    cover = bundle / "cover.jpg"
    if cover.is_file():
        dimensions = _probe_image_dimensions(cover)
        if dimensions:
            measured["cover"] = dimensions
    return measured


def _probe_image_dimensions(path: Path):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "json", str(path)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        return None
    streams = json.loads(result.stdout).get("streams", [])
    if not streams or not streams[0].get("width"):
        return None
    return f"{streams[0]['width']}x{streams[0]['height']}"


def _overlap_count(segments: list) -> int | None:
    """duplicateSegments 的机器实算：同素材源窗口两两相交对数（zaku-003 当年即人工比对的
    同一判据，落成代码=报告里这行从此是实测事实）。"""
    if not segments:
        return None
    windows = []
    for item in segments:
        start, end = item.get("sourceStartMs"), item.get("sourceEndMs")
        if not isinstance(start, (int, float)) or isinstance(start, bool) \
                or not isinstance(end, (int, float)) or isinstance(end, bool):
            return None
        windows.append((item.get("assetId"), start, end))
    pairs = 0
    for i in range(len(windows)):
        for j in range(i + 1, len(windows)):
            if windows[i][0] != windows[j][0]:
                continue
            if max(windows[i][1], windows[j][1]) < min(windows[i][2], windows[j][2]):
                pairs += 1
    return pairs


def build_machine_report(bundle: Path, manifest: dict, trace: dict, measured: dict) -> dict:
    """⑭（zaku-intro-003 实测，用户 09-29 定案）：质检报告标准生成器。
    artifacts＝包内**每一个证据文件**现算 path+sha256，R1 门禁从此不可能再撞上"只登
    path 未登 sha"漏项（当年 7 项握手产物全靠手搓 JSON 不忘才算全）。
    关单三件套＝metadata-validation-report.json（不能自指）、delivery-manifest.json、
    human-review-decision.json **不入 artifacts**——后两件在封版环节必被合法改写
    （status/finishedAt/acceptedWarnings），登记进报告指纹会让 R1 重算必炸；它们由
    收据 basisRefs+R2 basisHashes 绑定（zaku-003 封版实况即这条通道），不归报告管。
    checks＝机器实测事实逐字入册；本轮没跑的项写死「待补」，编排方只许替换这些占位行、
    不得改动 artifacts。status 停在 g5_pending_human_review：机器无权宣告完成，
    关单升级归人审闸后由编排方按批准记录回填。"""
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    report_name = "metadata-validation-report.json"
    close_out = {report_name, "delivery-manifest.json", "human-review-decision.json"}
    artifacts: dict = {}
    registered: set = set()
    for name, rel in (("finalVideo", "final-video.mp4"), ("cover", "cover.jpg"), ("subtitles", "subtitles.srt")):
        target = bundle / rel
        if target.is_file():
            artifacts[name] = {"path": rel, "sha256": digest(target)}
            registered.add(rel)
    clips = []
    for chapter in trace.get("chapters", []):
        rel = chapter.get("output")
        if isinstance(rel, str) and rel not in registered and (bundle / rel).is_file():
            clips.append({"path": rel, "sha256": digest(bundle / rel)})
            registered.add(rel)
    if clips:
        artifacts["chapterClips"] = clips
    for file in sorted(bundle.rglob("*")):
        if not file.is_file():
            continue
        rel = file.relative_to(bundle).as_posix()
        if rel in close_out or rel in registered:
            continue
        artifacts[rel] = {"path": rel, "sha256": digest(file)}
        registered.add(rel)
    segments = trace.get("segments", [])
    overlaps = _overlap_count(segments)
    pending = "待补（本轮机器未实测——编排方实测或人审后替换本行，artifacts 不得改动）"
    checks = {
        "decode": ("pass（完整解码零错误，机器实测）" if measured.get("decode") == "pass"
                   else "fail（解码未过，报告不应存在——请核对调用路径）" if measured.get("decode") == "fail" else pending),
        "videoCodec": f"{measured['videoCodec']}（机器实测，与 export-config 对账在 --media 校验中通过）" if measured.get("videoCodec") else pending,
        "dimensions": f"{measured['dimensions']}（机器实测）" if measured.get("dimensions") else pending,
        "fps": f"{measured['fps']}（机器实测，⑧丙对账通过）" if measured.get("fps") else pending,
        "audio": f"{measured['audio']}（机器实测）" if measured.get("audio") else pending,
        "duration": f"{measured['durationMs']}ms（机器实测）" if measured.get("durationMs") is not None else pending,
        "blackFrames": pending,
        "silence": pending,
        "duplicateSegments": (f"pass（{len(segments)} 段·同素材源窗口两两不相交，机器实算）" if overlaps == 0
                              else f"fail（{overlaps} 对源窗口相交，机器实算）") if overlaps is not None else pending,
        "cover": f"{measured['cover']}（机器实测尺寸；目视确认归人审）" if measured.get("cover") else pending,
    }
    report = {"schemaVersion": "0.1", "projectId": manifest.get("projectId"), "node": "G5",
              "subject": f"{manifest.get('projectId')} 交付包机器质检",
              "reviewedAt": now, "checks": checks, "artifacts": artifacts,
              "warnings": [], "humanReview": "待人工门禁关单后逐字回填（口令原文+批准记录指向）",
              "status": "g5_pending_human_review", "finishedAt": now,
              "generatedBy": "g5_validate_delivery.py --report-out"}
    (bundle / report_name).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--media", action="store_true", help="Also decode and probe final-video.mp4 with FFmpeg")
    parser.add_argument("--report-out", type=Path, default=None,
                        help="⑭（zaku-003 测后批）机器质检报告唯一生成入口：跑完全部机器校验后"
                             "把实测事实+包内每文件现算 sha256 写成 metadata-validation-report.json"
                             "（status=g5_pending_human_review，人审关单归门禁管）。校验不过=不落盘；"
                             "报告已存在=拒绝覆盖（需删旧重跑，编排序列自然重跑全部校验）。必须与 --media 同行。")
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    generating = args.report_out is not None
    errors: list[str] = []
    report_out = args.report_out.resolve() if generating else None
    if generating:
        if not args.media:
            print(json.dumps({"status": "invalid", "errors": ["⑭ 报告生成必须与 --media 同行——checks 只能写机器实测事实，没跑的一律待补；正式生成不许缺"]}, ensure_ascii=False)); return 2
        if report_out.parent != bundle or report_out.name != "metadata-validation-report.json":
            print(json.dumps({"status": "invalid", "errors": ["⑭ 报告唯一落盘位置=交付包根内 metadata-validation-report.json（R1 以报告所在目录为指纹基准，位置/文件名都不可自定）"]}, ensure_ascii=False)); return 2
        if report_out.exists():
            print(json.dumps({"status": "invalid", "errors": ["拒绝覆盖既有报告（⑭/㉘ 同源纪律：删旧报告后重跑——R2 basisHashes 会随重冻自动跟上，不许静默换报告）"]}, ensure_ascii=False)); return 2
    for name in REQUIRED:
        if generating and name in ("metadata-validation-report.json", "human-review-decision.json"): continue  # ⑭ 生成时点在人工批准之前
        if not (bundle / name).is_file(): errors.append(f"missing required file: {name}")
    if errors:
        print(json.dumps({"status": "invalid", "errors": errors}, ensure_ascii=True)); return 2
    try:
        manifest, trace, plan = load(bundle / "delivery-manifest.json"), load(bundle / "source-timecode-list.json"), load(bundle / "edit-plan.json")
        export = load(bundle / "export-config.json")
        qa = None
        review_path = bundle / "human-review-decision.json"
        if generating and not review_path.is_file():
            review = {}  # 生成时点在人工批准之前——决策文件此刻合法缺席（终验 --bundle 仍 REQUIRED）
        elif generating:
            review = load(review_path)
        else:
            qa, review = load(bundle / "metadata-validation-report.json"), load(review_path)
    except json.JSONDecodeError as error:
        print(json.dumps({"status": "invalid", "errors": [f"invalid JSON: {error}"]}, ensure_ascii=True)); return 2
    # Issue 002-⑬: the contract already allows "finishedAt OR explicit pending status"
    # (qa-contract); a pending-human-review manifest legitimately has no QA close time yet.
    manifest_status = str(manifest.get("status") or "")
    for field in CONTRACT_FIELDS:
        if field == "finishedAt" and manifest_status.startswith("pending"):
            continue
        if manifest.get(field) in (None, "", [], {}): errors.append(f"delivery manifest missing {field}")
    project_id = manifest.get("projectId")
    for label, data in (("traceability", trace), ("edit plan", plan), ("export config", export)) \
            + (() if generating else (("qa", qa), ("human review", review))):
        if data.get("projectId") != project_id: errors.append(f"projectId mismatch: {label}")
    if manifest.get("schemaVersion") != "0.1": errors.append("unsupported delivery manifest schemaVersion")
    if not all(item.get("assetId") and item.get("sourceProbe") for item in manifest.get("sourceProbe", [])):
        errors.append("sourceProbe entries are incomplete")
    segments = {item.get("segmentId"): item for item in trace.get("segments", [])}
    if not segments or {item.get("segmentId") for item in manifest.get("segments", [])} != set(segments): errors.append("manifest segments do not match traceability")
    for item in segments.values():
        if not item.get("assetId") or not item.get("sourceSha256") or not isinstance(item.get("sourceStartMs"), (int, float)) or item.get("sourceEndMs", 0) <= item.get("sourceStartMs", 0): errors.append(f"invalid source traceability: {item.get('segmentId')}")
    chapters = trace.get("chapters", [])
    if not 3 <= len(chapters) <= 5: errors.append("chapter clip count must be 3 to 5")
    for chapter in chapters:
        output = chapter.get("output"); target = inside(bundle, output) if isinstance(output, str) else None
        if not target or not target.is_file(): errors.append(f"missing chapter output: {output}")
        # Issue ㉜: segments entries may be bare IDs or objects carrying segmentId;
        # normalize before hashing, or a dict crashes the whole validator.
        refs = [item if isinstance(item, str) else item.get("segmentId") for item in chapter.get("segments", []) if isinstance(item, (str, dict))]
        if not refs or not set(refs).issubset(segments): errors.append(f"chapter traceability failed: {chapter.get('chapterId')}")
    if not generating:
        for item in [qa.get("artifacts", {}).get("finalVideo", {}), qa.get("artifacts", {}).get("cover", {}), qa.get("artifacts", {}).get("subtitles", {}), manifest.get("artifacts", {}).get("editTimeline", {})] + qa.get("artifacts", {}).get("chapterClips", []): check_artifact(bundle, item, errors)
        if not set(QA_CHECKS).issubset(qa.get("checks", {})): errors.append("qa report lacks required machine checks")
    check_delivery_srt(bundle, errors)
    check_transition_audit(bundle, errors)
    check_loudness_audit(bundle, plan, review, errors, allow_pending_acceptance=generating)
    if not generating and manifest.get("status", "").startswith("completed") and not (review.get("status") == "approved" and review.get("decision") == "accepted"):
        errors.append("completed bundle lacks accepted human review")
    if manifest.get("authorization") in (None, "") or manifest.get("distribution") in (None, ""): errors.append("authorization or distribution boundary missing")
    measured = validate_media(bundle, export, errors) if args.media else {}
    if generating and not errors:
        report = build_machine_report(bundle, manifest, trace, measured)
        pending_keys = [key for key, value in report["checks"].items() if str(value).startswith("待补")]
        print(json.dumps({"status": "report_written", "report": str(report_out), "projectId": project_id,
                          "artifacts": len(report["artifacts"]), "pendingChecks": pending_keys}, ensure_ascii=False))
        return 0
    result = {"status": "valid" if not errors else "invalid", "projectId": project_id, "chapters": len(chapters), "segments": len(segments), "errors": errors}
    if generating: result["reportWritten"] = False
    print(json.dumps(result, ensure_ascii=True)); return 0 if not errors else 2


if __name__ == "__main__":
    try: raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "invalid", "errors": [str(error)]}, ensure_ascii=True)); raise SystemExit(2)
