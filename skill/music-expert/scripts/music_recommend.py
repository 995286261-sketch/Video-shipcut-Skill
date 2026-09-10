#!/usr/bin/env python3
"""Rank BGM candidates against a requirements profile (optionally a style brief).

Deterministic and pure-stdlib: it only joins candidate records with their analysis
reports and scores them. It never fabricates a match — when too few candidates clear
the bar, it reports the gap (shorten output / restock) and leaves the choice to the
human gate, mirroring the ⑲ sufficiency-fallback discipline. Human-facing timecodes
use m:ss.mmm; integer milliseconds stay in the JSON.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import music_tags

LICENSE_WEIGHT = {"cc0": 1.0, "public-domain": 1.0, "cc-by": 0.9, "cc-by-sa": 0.85,
                  "owned": 1.0, "cleared-for-project": 1.0, "unknown": 0.3}


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True))


def mmss(ms: int) -> str:
    total_seconds = ms / 1000.0
    minutes = int(total_seconds // 60)
    seconds = total_seconds - minutes * 60
    return f"{minutes}:{seconds:06.3f}"


def load_reports(index_dir_candidates: list[Path]) -> dict:
    reports = {}
    for directory in index_dir_candidates:
        if not directory.is_dir():
            continue
        for path in directory.glob("BGM-分析报告-*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            sha = (data.get("source") or {}).get("sha256")
            if sha:
                reports[sha] = data
    return reports


def collect_candidates(paths: list[Path]) -> list[dict]:
    candidates = []
    for path in paths:
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            if "candidates" in payload:
                candidates.extend(payload["candidates"])
            elif "title" in payload or "provenance" in payload:
                candidates.append(payload)
    return candidates


def candidate_sha(candidate: dict) -> str | None:
    if candidate.get("sha256"):
        return candidate["sha256"]
    audio_path = candidate.get("audioPath")
    if audio_path and Path(audio_path).is_file():
        digest = hashlib.sha256()
        with Path(audio_path).open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest().upper()
    return None


def score(candidate: dict, report: dict | None, profile: dict) -> tuple[float, list[str]]:
    notes = []
    if report is None:
        return 0.0, ["no_analysis"]
    if (candidate.get("decodeProbe") or {}).get("status") != "passed":
        return 0.0, ["decode_probe_not_passed"]

    total = 0.0
    # duration coverage (40%)
    duration_ms = report["source"]["decodedDurationMs"]
    need_ms = int(profile.get("targetDurationSec", duration_ms / 1000) * 1000)
    if need_ms <= 0 or duration_ms >= need_ms:
        total += 0.40
    else:
        total += 0.40 * (duration_ms / need_ms)
        notes.append("shorter_than_target")

    # tempo fit (35%)
    tempo = report.get("tempoBpm") or 0.0
    bpm_range = profile.get("bpmRange") or ([None, None])
    low, high = (bpm_range + [None, None])[:2]
    if low is None and high is None:
        total += 0.35
    elif tempo and (low is None or tempo >= low) and (high is None or tempo <= high):
        total += 0.35
    else:
        notes.append("bpm_out_of_range")

    # energy/segment shape (15%)
    if profile.get("minSegments"):
        if len(report.get("energySegments", [])) >= int(profile["minSegments"]):
            total += 0.15
        else:
            notes.append("fewer_segments_than_requested")
    else:
        total += 0.15

    # loudness headroom for narration ducking (10%)
    integrated = (report.get("loudness") or {}).get("integratedLufs")
    ceiling = profile.get("maxIntegratedLufs")
    if ceiling is None or (integrated is not None and integrated <= ceiling):
        total += 0.10
    else:
        notes.append("loudness_above_ducking_ceiling")

    # coarse theme-tag matching (10% share, only when the profile asks for it;
    # rough vocabulary overlap by design — see references/tag-vocabulary.md)
    wanted = profile.get("styleTags")
    if wanted:
        wanted_slugs = [music_tags.resolve_tag(tag) for tag in wanted]
        candidate_slugs = candidate.get("styleTags") or music_tags.normalize_tag_list(candidate.get("tags") or [])
        hits = [slug for slug in wanted_slugs if slug and slug in candidate_slugs]
        ratio = len(hits) / len(wanted_slugs)
        total = round(total * 0.9 + 0.10 * ratio, 4)
        notes.append(f"tags {len(hits)}/{len(wanted_slugs)}")

    # license weight modulates the total
    license_value = str(candidate.get("licenseType") or candidate.get("license", "")).lower()
    if license_value == "uncleared-platform-catalog":
        # sourcing-contract 轨道三（网易云试听选型）：本池存在的意义就是内测选型，
        # internal_test 画像内不压分——"进剪辑计划前必须登记"由链子把关，不由打分假装；
        # 更严边界（商用）下重罚排除：未清权音乐不得为对外分发背书。
        if str(profile.get("distributionBoundary", "internal_test")).lower() == "internal_test":
            notes.append("uncleared_internal_test_only")
        else:
            notes.append("license_weighted_down")
            total = round(total * 0.3, 4)
    else:
        weight = LICENSE_WEIGHT.get(license_value, 0.3)
        if weight < 1.0:
            notes.append("license_weighted_down")
            total = round(total * weight, 4)
    return total, notes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True, type=Path, help="requirements JSON (targetDurationSec, bpmRange, minSegments, maxIntegratedLufs)")
    parser.add_argument("--candidates", action="append", type=Path, default=[], help="candidate manifest files (freesound pool or manual registrations)")
    parser.add_argument("--reports-dir", action="append", type=Path, default=[], help="directories containing BGM-分析报告-*.json")
    parser.add_argument("--min-score", type=float, default=0.7)
    parser.add_argument("--min-pass", type=int, default=3)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    if not args.profile.is_file():
        emit({"status": "invalid", "errors": [{"field": "profile", "rule": "file not found", "detail": str(args.profile)}]})
        return 2
    try:
        profile = json.loads(args.profile.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        emit({"status": "invalid", "errors": [{"field": "profile", "rule": "invalid json", "detail": str(error)}]})
        return 2

    wanted = profile.get("styleTags") or []
    unmapped = [tag for tag, slug in zip(wanted, (music_tags.resolve_tag(t) for t in wanted)) if slug is None]
    if unmapped:
        emit({"status": "invalid", "errors": [{"field": "profile.styleTags", "rule": "every profile tag must come from the controlled vocabulary",
              "detail": f"unknown tags: {', '.join(str(t) for t in unmapped)}; accepted — {music_tags.accepted_tags_text()}"}]})
        return 2

    report_index = load_reports(list(args.reports_dir))
    candidates = collect_candidates(args.candidates)
    if not candidates:
        emit({"status": "blocked", "blockers": [{"type": "no_candidates", "detail": "no candidate files were supplied; run the search or register candidates first"}]})
        return 2

    scored = []
    unanalyzed = []
    for candidate in candidates:
        sha = candidate_sha(candidate)
        report = report_index.get(sha) if sha else None
        if report is None:
            unanalyzed.append({"title": candidate.get("title"), "freesoundId": candidate.get("freesoundId"),
                               "hint": "run music_analyze.py on this candidate to make it rankable"})
            continue
        total, notes = score(candidate, report, profile)
        scored.append({
            "title": candidate.get("title"),
            "freesoundId": candidate.get("freesoundId"),
            "neteaseId": candidate.get("neteaseId"),
            "provenance": candidate.get("provenance"),
            "sourceUrl": candidate.get("sourceUrl"),
            "previewPath": candidate.get("previewPath") or candidate.get("audioPath"),
            "licenseType": candidate.get("licenseType") or candidate.get("license"),
            "attributionRequired": candidate.get("attributionRequired", str(candidate.get("attribution", "none")).lower() != "none"),
            "durationMs": report["source"]["decodedDurationMs"],
            "tempoBpm": report.get("tempoBpm"),
            "integratedLufs": (report.get("loudness") or {}).get("integratedLufs"),
            "hitPointCount": len(report.get("hitPoints", [])),
            "styleTags": candidate.get("styleTags") or music_tags.normalize_tag_list(candidate.get("tags") or []),
            "sha256": sha,
            "score": total,
            "notes": notes,
            "infringementRisk": str(candidate.get("licenseType") or candidate.get("license", "")).lower() == "uncleared-platform-catalog",
            "distributionBoundary": candidate.get("distributionBoundary", "internal_test"),
        })
    scored.sort(key=lambda item: item["score"], reverse=True)
    passing = [item for item in scored if item["score"] >= args.min_score]

    result = {
        "schemaVersion": "0.1",
        "purpose": "bgm_recommendation",
        "profile": profile,
        "minScore": args.min_score,
        "ranked": [{**item, "durationDisplay": mmss(item["durationMs"])} for item in scored],
        "passing": [{**item, "durationDisplay": mmss(item["durationMs"])} for item in passing],
        "unanalyzed": unanalyzed,
        "sufficiency": {
            "passing": len(passing),
            "minExpected": args.min_pass,
            "enough": len(passing) >= args.min_pass,
            "gapAction": None if len(passing) >= args.min_pass else "候选不足：向用户呈现 补检索 / 放宽画像 / 缩短成品 三项，不得自行拼凑",
        },
    }
    uncleared = [item for item in result["ranked"] if item.get("infringementRisk")]
    if uncleared:
        result["licenseWarning"] = (
            f"⚠ 侵权风险：{len(uncleared)}/{len(result['ranked'])} 条候选未清权（uncleared-platform-catalog，网易云试听选型）。"
            "平台曲库授权仅覆盖端内播放——未登记而将其用于成片即构成侵权。"
            "本池仅限 internal_test 选型；挑曲后整轨必须经官方渠道取得并经 music_register_candidate.py 登记真实许可后方可进剪辑计划。"
            "对外分发项目在任何清权完成前不得使用这些曲目。")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not args.output.is_file() or args.output.stat().st_size == 0:
        emit({"status": "blocked", "blockers": [{"type": "output_write_failed", "detail": str(args.output)}]})
        return 1
    echo_path = render_echo(result, args.output.parent / "BGM-推荐回显-v0.1.md")
    emit({"status": "completed", "output": str(args.output), "echo": str(echo_path), "scored": len(scored),
          "passing": len(passing), "unanalyzed": len(unanalyzed),
          "licenseWarning": bool(uncleared), "enough": result["sufficiency"]["enough"]})
    return 0


def render_echo(result: dict, path: Path) -> Path:
    """Human-facing recommendation card: infringement banner first, table second."""
    lines = ["# BGM 推荐回显 v0.1", ""]
    if result.get("licenseWarning"):
        lines += [f"> {result['licenseWarning']}", ""]
    profile = result["profile"]
    sufficiency = result["sufficiency"]
    lines += [f"- 画像：时长 ≥{profile.get('targetDurationSec', '?')}s｜BPM {profile.get('bpmRange', '不限')}"
              f"｜通过线 {result['minScore']}｜通过 {sufficiency['passing']}/{sufficiency['minExpected']}"
              + ("" if sufficiency["enough"] else f"｜❌不足：{sufficiency['gapAction']}"),
              "", "| # | 曲目 | BPM | 时长 | 响度 | 分 | 侵权风险 | 注记 |", "|---|---|---|---|---|---|---|---|"]
    for index, item in enumerate(result["ranked"], 1):
        lines.append(f"| {index} | {item['title']} | {item['tempoBpm']} | {item['durationDisplay']} "
                     f"| {item['integratedLufs']} | {item['score']:.3f} "
                     f"| {'⚠ 未清权' if item.get('infringementRisk') else '—'} | {'、'.join(item['notes']) or '—'} |")
    if result["unanalyzed"]:
        lines += ["", f"- 未分析隔离：{len(result['unanalyzed'])} 条（先跑 music_analyze 再打分）。"]
    lines += ["", "- 分数并列时的最终取舍在人耳：试听件路径见候选清单 `previewPath`；挑曲后必须登记，未登记不得进剪辑计划。", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


if __name__ == "__main__":
    raise SystemExit(main())
