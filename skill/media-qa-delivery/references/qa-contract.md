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
export-config.json
metadata-validation-report.json
delivery-manifest.json
README.md
failure-samples/README.md
```

Chapter count may be 3–5. The internal edit can contain more fine-grained segments; the traceability JSON must expand each chapter to those segments and then to original source timecodes.

## Contract entry point

`edit-timeline.md` is mandatory. It is the approved G3 row-by-row timeline, covering the full output without gaps or overlaps. Each row must state output start/end, source asset and source time interval, crop/mask/replace treatment, motion, narration, visible text, and BGM/source-audio rule. The final delivery manifest must include it in `artifacts`.

`delivery-manifest.json` is the single machine-readable G5 contract entry point. It must expose `schemaVersion`, `projectId`, `sourceProbe`, `segments`, `editPlan`, `artifacts`, `qaReport`, `humanReviewPoints`, `evidenceRefs`, `warnings`, `status`, and `finishedAt` or an explicit pending-human-review status. It may link to the detailed JSON records, but must retain the source-probe, segment, artifact, warning, and boundary data needed for an independent audit.

`metadata-validation-report.json` remains the detailed QA record. It must contain machine checks, detected anomalies, file hashes, and manual-review status; it is not the combined workflow contract.

## Required QA checks

Check decode, codec, dimensions, frame rate, audio tracks, duration delta, cover dimensions, subtitle syntax, file hashes, black frames, silence, duplicate segments, and source traceability. Detector limitations and anomalies are warnings, not passes.

## Human gate

Human review is mandatory for burned subtitles, subtitle overlap, safe area, narration-picture sync, key shots, complete playback, audio mix, confirmed voice language/accent/voice type/speaking rate, and authorization. Do not mark G5 complete before the human decision is recorded.
