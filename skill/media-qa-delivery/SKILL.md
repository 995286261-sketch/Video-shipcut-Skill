---
name: media-qa-delivery
description: Run G5 final QA for locally rendered video, package an auditable delivery bundle, and record machine checks, human review points, traceability, warnings, and distribution limits. Use after G4 or ChatCut export when the user needs a final video delivery package, chapter clips, source timecode mapping, metadata validation, or a reproducible README.
metadata:
  pipelineNode: G5
  g5InteractionReference: references/g5-choice-cards.md
---

# Media QA and Delivery

This is the G5 QA and delivery Skill. `G5_BUNDLE_ROOT` in [Project Layout Contract](../video-shipcut-pipeline/references/project-layout-contract.md) is the only canonical delivery and audit closure. Do not create or use `G5-交付`; report a legacy directory if one exists, and remove it only with explicit user authorization. Use this skill only after G4 has produced a candidate final render or a ChatCut export. User-facing QA and delivery responses follow [Video-shipcut path display contract](../video-shipcut-pipeline/references/path-display-contract.md); delivery manifests and QA JSON retain plain machine paths.

Read `references/g5-choice-cards.md` before presenting G5. Run automatic QA and show the delivery-bundle draft first; the only user gate is the final playback/acceptance decision. A validated local-direct G4 export is a valid G5 input and does not require ChatCut.

## Required inputs

- The actual final export from the G4 local-direct branch or `CHATCUT_EXPORT_ROOT` when ChatCut was selected.
- The approved G3 edit plan and G4 render metadata.
- Source and segment traceability data with `assetId`, source path, SHA-256, and source `startMs/endMs`.
- Final subtitle and cover assets when present.
- Authorization and distribution policy.

Do not modify source media. Do not treat a flattened preview as a ChatCut-editable timeline source.

## Delivery location

Write the finished bundle to:

`G5_BUNDLE_ROOT`

Keep working files, logs, temporary renders, and editable handoff assets in `工作台/<projectId>/G4-剪辑与渲染/`. Do not put raw source media, credentials, caches, or unlicensed music in the delivery bundle.

The canonical bundle is already inside the active project. Run `scripts/g5_mirror_audit_copy.py` only when an explicitly requested second audit copy is required; it replaces the version directory atomically enough to prevent stale artifacts. Register the canonical bundle and validation report in pipeline state before requesting G5 human review.

## Bundle contract

The default review and audit bundle contains:

- `final-video.mp4`: final exported video.
- `cover.jpg`: selected cover.
- `clips/`: 3–5 chapter-level clips. Preserve finer internal segments in the traceability map instead of exposing them as the default review entry point.
- `source-timecode-list.json`: chapter -> internal segment -> original asset, source path, source SHA-256, source timecodes, and output timeline.
- `edit-plan.json`: machine-readable operation, ordering, audio, subtitle, cover, artifact, and human-review fields.
- `edit-timeline.md`: the approved G3 row-by-row edit timeline. It must list each output time interval, source asset and source interval, crop/mask/replace treatment, motion, narration, on-screen text, and BGM or source-audio rule. This is a required delivery artifact, not a chat-only summary.
- `subtitles.srt`: final narration subtitles.
- `export-config.json`: platform, aspect ratio, target duration, subtitle, cover, audio, music, and authorization settings. Use `not_specified` rather than hard-coding an unknown platform profile.
- `metadata-validation-report.json`: machine checks, warnings, file hashes, and manual review status.
- `delivery-manifest.json`: the single machine-readable G5 contract entry point. It consolidates source probes, segment traceability, edit-plan summary, artifact hashes, QA reference, human-review references, warnings, and delivery boundary.
- `README.md`: purpose, file relationships, reproducibility notes, authorization, and distribution boundary.
- `failure-samples/README.md`: only real failures and their handling; never invent a passing result.

## QA procedure

1. Probe the final export with FFprobe and verify decodability with FFmpeg.
2. Check codec, dimensions, frame rate, audio tracks, duration, cover dimensions, file hashes, and subtitle parseability.
3. Run black-frame, silence, and duplicate checks when available. Record detected intervals; a detector limitation or detected anomaly is a warning, never an automatic pass.
4. Validate that every delivered chapter maps to the internal segment list and original source timecodes.
5. Perform human review of the entire final video and explicitly record: burned source subtitle residue, subtitle overlap/safe area, narration-picture sync, opening, key comparison footage, priority action section, outro, audio mix, confirmed voice language/accent/voice type/speaking rate, and authorization boundary.
6. Mark the bundle `g5_pending_human_review` until all required human checks are confirmed. Mark it complete only after accepted warnings are recorded.
7. 向用户回显 QA 结果和交付包清单时，所有产物路径必须写成可点击的 Markdown 超链接 `[文件名](相对路径)`，让用户能直接点开预览视频、封面、字幕等交付物。

## Reproducible validation

After the component records exist, create the contract entry point with `scripts/g5_build_delivery_manifest.py --bundle <delivery-bundle> --evidence <approved-g2-evidence.json>`. Run `scripts/g5_validate_delivery.py --bundle <delivery-bundle>` before requesting human G5 approval. Add `--media` to re-run FFmpeg decode/probe checks on the final export. A validation failure must keep G5 in `review_required` or `blocked`; do not infer completion from an old QA report.

## Pipeline Integration

Read `工作台/<projectId>/pipeline-state.json` and work only at G5. Record only G5 artifacts, machine results, human-review points, and accepted warnings through `$video-shipcut-pipeline`. Do not complete the overall project until pipeline records user G5 approval.

## Non-negotiable boundaries

- Do not claim a duration target was hit when the export differs; record target, actual, and delta.
- Do not infer that burned-in subtitles are absent from the lack of a subtitle track.
- Do not upgrade `user_manually_verified` facts into official evidence.
- Do not distribute practice or authorization-uncertain media. Preserve `personal_practice_unverified` and `not_for_distribution` when applicable.
