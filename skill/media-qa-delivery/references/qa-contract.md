# G5 QA Contract

## Input

Rendered final media, approved edit plan, source/segment manifest, subtitle and cover assets, export profile, and authorization policy.

## Output

Write to `G5_BUNDLE_ROOT` defined in [Project Layout Contract](../../p0-c-pipeline/references/project-layout-contract.md):

```text
final-video.mp4
cover.jpg
clips/chapter-01.mp4 ... chapter-05.mp4
source-timecode-list.json
edit-plan.json
edit-timeline.md
subtitles.srt
subtitle-srt-check.json
export-config.json
metadata-validation-report.json
delivery-manifest.json
README.md
failure-samples/README.md
```

Chapter count may be 3–5. The internal edit can contain more fine-grained segments; the traceability JSON must expand each chapter to those segments and then to original source timecodes.

The exact JSON shape of every component above (field names, required keys, artifact hashing, `--media` re-probe rules) is fixed in [Delivery Bundle Schema](delivery-bundle-schema.md) — the single source of truth shared by `g5_build_delivery_manifest.py` and `g5_validate_delivery.py` (N8 ㉜㉝). Any field expectation change must edit that contract first.

## Contract entry point

`edit-timeline.md` is mandatory. It is the approved G3 row-by-row timeline, covering the full output without gaps or overlaps. Each row must state output start/end, source asset and source time interval, crop/mask/replace treatment, motion, narration, visible text, and BGM/source-audio rule. The final delivery manifest must include it in `artifacts`.

`delivery-manifest.json` is the single machine-readable G5 contract entry point. It must expose `schemaVersion`, `projectId`, `sourceProbe`, `segments`, `editPlan`, `artifacts`, `qaReport`, `humanReviewPoints`, `evidenceRefs`, `warnings`, `status`, and `finishedAt` or an explicit pending-human-review status. It may link to the detailed JSON records, but must retain the source-probe, segment, artifact, warning, and boundary data needed for an independent audit.

`metadata-validation-report.json` remains the detailed QA record. It must contain machine checks, detected anomalies, file hashes, and manual-review status; it is not the combined workflow contract.

## Required QA checks

Check decode, codec, dimensions, frame rate, audio tracks, duration delta, cover dimensions, subtitle syntax, file hashes, black frames, silence, duplicate segments, and source traceability. Detector limitations and anomalies are warnings, not passes.

### 检测器判读纪律（002 验收问题 ⑪⑭）

- **字幕面检查（⑪等）**：判读纪律唯一口径已剥入字幕专员 `skill/subtitle-expert/references/qa-contract.md`（越界只对描边/底带 ROI 出结论、告警须目视确认、绿灯不背渲染正确性的锅）；G5 按该合同消费，检查帧证据仍登记在收据 `check_frames` 项。
- **重复帧检测对动漫平涂过敏（⑭）**：mpdecimate 一类检测器对平涂/赛璐璐画风会大量误标（002 实测 2842→1741 帧）。标准解释链 = **源区间互斥机验**（traceability 中各段源时间区间两两不重叠）**+ 抽帧目视**双确认；两者一致时按"检测器判读差异"如实记警告并附解释链，不得据此报"无重复画面"通过，也不得把误标帧当作重复画面缺陷。
- **finishedAt 语义（⑬）**：`finishedAt` = **机器质检收口时刻**（metadata QA 完成、报告落盘的时间），不是交付关单时刻；交付关单以 pipeline-state 的 `确认G5` 审批记录为准。pending-human-review 状态的 manifest 允许暂缺 `finishedAt`，质检收口后必须回填。

## Human gate

Human review is mandatory for burned subtitles, subtitle overlap, safe area, narration-picture sync, key shots, complete playback, audio mix, confirmed voice language/accent/voice type/speaking rate, and authorization. Do not mark G5 complete before the human decision is recorded.
