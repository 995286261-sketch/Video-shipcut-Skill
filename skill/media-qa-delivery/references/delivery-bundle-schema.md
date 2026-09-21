# 交付包组件 Schema（唯一事实源）

- **现象**：`g5_build_delivery_manifest.py` 与 `g5_validate_delivery.py` 对同一文件的形状期望此前只存在于代码里，builder/validator 各信一边，只能靠撞错反推（N8 ㉜㉝）。
- **改法**：本文件写死每个组件的形状；改任一脚本的字段期望必须先改本合同。validator 保持 `REQUIRED + CONTRACT_FIELDS + QA_CHECKS` 为机器清单，本节逐字对应。

## 目录与必备文件（validator `REQUIRED`，全部大小写精确）

```text
交付包-v<版本>/
├── final-video.mp4  cover.jpg  subtitles.srt
├── source-timecode-list.json  edit-plan.json  edit-timeline.md
├── export-config.json  metadata-validation-report.json
├── human-review-decision.json  delivery-manifest.json
├── README.md  failure-samples/README.md
├── clips/（3–5 个章节短片，被 source-timecode-list 引用）
└── qa/ 等审计件（合同外，validator 不查）
```

`subtitles.srt` 至少含一行合法时间戳：`HH:MM:SS,mmm --> HH:MM:SS,mmm`。`failure-samples/README.md` 若机器检查全绿、零失败，正文必须是真实说明（"为何为空"），不允许缺文件。

## delivery-manifest.json（builder 产出，validator `CONTRACT_FIELDS` 逐项非空）

`schemaVersion`（当前 `"0.1"`）、`projectId`、`sourceProbe`（数组，每项含 `assetId`+`sourceProbe`）、`segments`（顶层扁平数组，每项含 `segmentId`，必须与 source-timecode-list 的 segments **集合相等**）、`editPlan`、`artifacts`（含 `editTimeline`：`{path, sha256}`）、`qaReport`、`humanReviewPoints`、`evidenceRefs`、`warnings`、`status`、`finishedAt`（非空字符串；**语义=机器质检收口时刻，不是交付关单时刻**——关单以 pipeline-state 的 `确认G5` 审批为准。`status` 以 `pending` 开头时允许暂缺，质检收口后必须回填；002 问题⑬裁决）。`status` 以 `completed` 开头时，`human-review-decision.json` 必须已是 `approved`+`accepted`。`authorization`、`distribution` 两个边界字段必须非空。

## source-timecode-list.json

顶层 `projectId` + 两个数组：

- `segments[]`：`{segmentId, assetId, sourceSha256, sourceStartMs, sourceEndMs}`，`end > start`；
- `chapters[]`（3–5 条）：`{chapterId, output, segments}`。`output` 是**相对包根**的文件路径（如 `clips/chapter-01.mp4`），必须真实存在于包内；`segments` 每项写**段 ID 字符串**——validator 兼容 `{"segmentId": …}` 对象（㉜ 归一化），但 builder 与文档口径统一用字符串，避免再分叉。段 ID 必须是 `segments[]` 的子集。

## metadata-validation-report.json

- `checks`：必须**恰好覆盖**十个键（可多不可少）：`decode`、`videoCodec`、`dimensions`、`fps`、`audio`、`duration`、`blackFrames`、`silence`、`duplicateSegments`、`cover`；每项 `{status: "pass"}` 或带说明的失败项。
- `artifacts`：固定键 `finalVideo`、`cover`、`subtitles`、`chapterClips`（数组，对应 clips/ 全部文件）；每项 `{path, sha256}`，`path` 相对包根、`sha256` 大写十六进制，validator 逐一重算比对。

## export-config.json

`projectId` 必填；`video`：`codec`（如 `h264`）及可选 `width`/`height`/`fps`/`durationActualMs`；`audio`：`codec`；**`authorization` 与 `distribution` 必填**（002 问题⑫补记：builder 从这两个字段抬进 manifest 的边界栏，缺省填 `not_specified` 虽能过机器校验，但等于边界未声明——G5 回显卡必须如实呈出）。这些值只在 validator 带 `--media` 时对真实成片复核：解码全片、ffprobe 对 codec/分辨率/fps（±0.1）/时长（±150ms）、音轨 codec。不传 `--media` 时只查 JSON 形状。

## human-review-decision.json

`{projectId, status: "approved", decision: "accepted", acceptedWarnings: [...]}`；人工 QA 停靠点不可由机器检查代签。

## 与审计副本的接缝

`g5_mirror_audit_copy.py` 把交付包镜像进 `归档/` 时整目录替换、清除过期件；归档只读审计，恢复项目状态一律以 `工作台/<projectId>/pipeline-state.json` 为准。
