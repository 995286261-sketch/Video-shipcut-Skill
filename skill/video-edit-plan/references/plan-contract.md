# 编辑计划合同

当前已实现的 G1 输入是：通过 `material-pack-intake validate` 的素材包、由用户逐步确认的创作方向，以及逐条事实主张的证据引用。

G1 输出是调用方工作区中的方向简报（Markdown 和 JSON），至少包含：`projectId`、创作方向、输出偏好、表达边界、`claims[]` 和 `evidenceRefs[]`。`supported` 主张必须有素材包 `03_事实依据/` 内的可定位证据；`pending` 主张不是已确认事实。

G3 编辑计划已实现为人工审核规划，输入为已校验素材包、G2 审核决定、证据产物、输出规格和编辑约束；输出为带 `assetId` 与原片 `startMs/endMs` 的候选/最终片段、叙事排序、转场/音频/字幕/封面指令、来源层级、人工确认记录和警告。它不执行语义自动选段、G4 渲染、ChatCut 项目创建、上传或发布；任何外部上传/分发需用户单独授权。

## G3 时长决定

每份 G3 计划必须含有 `durationDecision`，将 G1 的目标时长、G2 已批准口播的自然估计时长和用户明确决定连在一起：

```json
{
  "targetDurationSec": 150,
  "narrationEstimatedDurationSec": 115,
  "resolution": "preserve_target_with_editorial_padding",
  "decisionReason": "用户确认以有目的的章节转场、片头和片尾 BGM 留白补足叙事节奏。",
  "intentionalSilence": [
    {"startMs": 0, "endMs": 4000, "purpose": "片头建立氛围", "bgmPolicy": "approved_bgm_fade_in"}
  ],
  "antiFillRule": {
    "disallowRepeatedSegments": true,
    "disallowLoops": true,
    "disallowMeaninglessSlowMotion": true,
    "disallowUnverifiedFactPadding": true
  }
}
```

`resolution` 只能是 `preserve_target_with_editorial_padding`、`follow_narration_natural_duration` 或 `rewrite_narration`。完整时间线确认必须记录在计划级 `timelineReview` 中；用户一次确认整表，局部修改按 `segmentId` 记录。设计性留白只可用于片头、章节转场、情绪停顿或片尾；每段必须记录原始成片时间轴范围、表达目的和获准 BGM 规则。普通视频镜头必须显式记录 `sourceDurationMs`、`outputDurationMs` 和 `mappingMode`，默认一比一播放；连续动作候选还应记录 `actionUnitId`、`continuityGroup`、`continuityRole`、`preAction/action/reaction/recovery`、`retainPolicy` 和 `handleFrames`，以避免在动作因果链中间硬切；不得用重复片段、循环、无目的慢放、冻结、隐式 padding、重复口播或未确认事实填充时长。同一源 SHA-256 的源区间不得相交，紧邻区间可以相接。
