# 编辑计划合同

当前已实现的 G1 输入是：通过 `material-pack-intake validate` 的素材包、由用户逐步确认的创作方向，以及逐条事实主张的证据引用。

G1 输出是调用方工作区中的方向简报（Markdown 和 JSON），至少包含：`projectId`、创作方向、输出偏好、表达边界、`claims[]` 和 `evidenceRefs[]`。`supported` 主张必须有素材包 `03_事实依据/` 内的可定位证据；`pending` 主张不是已确认事实。

G3 编辑计划已实现为人工审核规划，输入为已校验素材包、G2 审核决定、证据产物、输出规格和编辑约束；输出为带 `assetId` 与原片 `startMs/endMs` 的候选/最终片段、叙事排序、转场/音频/字幕/封面指令、来源层级、人工确认记录和警告。它不执行语义自动选段、G4 渲染、ChatCut 项目创建、上传或发布；任何外部上传/分发需用户单独授权。

## G3 时长决定

每份 G3 计划必须含有 `durationDecision`，将 G1 的目标时长、G2 已批准口播的时长和用户明确决定连在一起。`narrationEstimatedDurationSec` 在旁白已合成时必须取 `G2-配音清单-v0.1.json` 的 `measuredTotalDurationMs/1000` 实测值；只有尚未合成才能用文本估计并标记待合成——基线实测文本估时与真实 TTS 偏差约 40%，估时不得冒充实测。

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

## G3 BGM 计划（bgmPlan，机器化）

素材包 `07_授权音频` 中存在带 `bgmRegistration` 的音频资产时，计划**必须**含 `bgmPlan`，且校验必须同时传 `--material-pack <material-pack.json> --bgm-alignment <BGM-对齐建议-v0.2.json>`。BGM 数字禁止手抄：002 的教训是"数字有出处，但人肉抄写让出处不可查证"。规格：

```json
{
  "bgmPlan": {
    "audioSha256": "<G0 登记的音频文件哈希>",
    "reportSha256": "<G0 登记的分析报告文件哈希>",
    "alignmentRef": "工作台/<projectId>/G3-剪辑计划/BGM/BGM-对齐建议-v0.2.json",
    "alignmentSha256": "<对齐产物逐字节哈希>",
    "trackOffsetMs": 0,
    "fades": {"fadeInMs": 2000, "fadeOutStartMs": 111310, "fadeOutMs": 2000},
    "duckingPolicy": "口播活跃区间 BGM 压低；深度参数在 G4 执行前拍板（§6-②）"
  }
}
```

机器强制（厚）：`validate_g3_plan.py` 对账全链哈希——音频哈希命中素材包登记、报告磁盘内容哈希=登记哈希（防 G0 后篡改）、报告 cacheKey=音频哈希（防换曲）、对齐产物字节哈希=`alignmentSha256`（**手改对齐数字即拒绝，想变只能改参数重跑 music_align**）、`trackOffsetMs`/`fades`/`timelineDurationMs` 逐项等于对齐产物；逐段口播映射区间的端点必须精确铺满 G2 声音简报的每个句子区间（句时值冻结，句内切段合法，如 seg-05a/05b）。乐句表本体只存于对齐产物 `layout.phrasesOnTimeline`，计划与回显引用不复制。

人工判断（薄）：每段 `layoutTier` 从受控词表 `快切/推进/常规/留白` 中取值——music_align 给出的段能量分位数草稿（默认 `0.75,0.5,0.25`，`--tier-quantiles` 可调）只是机械建议，最终档位以 G3 终审八列回显逐行人工定夺；validator 只查词表合法与回显-计划一致。

终审回显卡 v0.2：计划含 `bgmPlan` 时，`G3-回显数据` 必须升 `schemaVersion "0.2"` 并带 `bgmBasis` 块（偏移/吸附 n/m/ducking 句数/对齐文件指认），校验传 `--alignment`；每行必须有与计划一致的 `layoutTier`，渲染进"BGM 乐句"格（`乐句 · 档位`）。BGM 专员对齐回显卡按 D12 原样内联在终审卡之后，**不单独设门禁请批**——G3 人工干预点只有终审回显这一处。
