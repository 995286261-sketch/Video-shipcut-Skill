# G3 目标素材视觉分析合同

G3 的目标主体筛选必须先完成“关键帧 → 多模态识图 → 结构化文字索引”。联系表、离线转写和候选段起/中/终帧都不能单独代替这一步。

## 产物

项目级视觉分析 manifest 建议写入：

`工作台/<projectId>/G3-剪辑计划/G3-目标素材视觉分析-v<version>.json`

每个目标素材至少记录：

- `assetId`
- 与 G0/G2 一致的 `sha256`
- 原片 `sourceRange.startMs/endMs`
- `keyframeRefs[]`，每帧含原片时间码和实际文件路径
- `analysisStatus`
- `identityStatus`：`confirmed`（已确认目标主体）、`person_only`（仅确认出现人物，未确认目标主体）、`uncertain`、`not_present` 或 `mixed`。除 `confirmed` 外一律不自动入选，只进入不可用素材统计。
- `observedVisuals`：只描述实际看到的画面
- `riskFlags`：例如 `channel_watermark`、`burned_subtitle`、`mixed_subject`、`overexposure`

## 缓存与文字索引

一次完成的视觉分析必须可复用，不能因为 G3 修改时间线、G4 接手或 G5 审计而重新识别相同图片。manifest 顶层必须记录 `cacheKey`，至少含：`assetId`、源文件 `sha256`、`sourceRange`、抽帧间隔、provider、model 和 promptVersion。

同时写入 `工作台/<projectId>/G3-剪辑计划/G3-视觉文字索引-v<version>.json`。索引从 manifest 派生，不得重新调用视觉模型；每个条目按源时间范围记录：

- `subjectStatus`：目标主体已确认、仅人物、混合/不确定或非目标；
- `observed`：仅描述已经看见的画面；
- `editingUse`：可承担的剪辑用途或默认排除理由；
- `risks`：台标、烧录字幕、混合主体、模糊等。

下游先比较缓存键。`assetId`、SHA-256、分析范围、模型与提示词版本一致时，必须读取文字索引和 manifest，不得重跑全量抽帧/识图。只有源文件哈希变化、分析范围扩展、用户确认的目标主体变化，或用户明确要求不同模型/提示词时，缓存才失效。

## 逐帧观察账本（强制）

除全片 manifest 外，项目还必须维护追加式 `G3-视觉观察账本-v<version>.json`。它解决“同一张帧图被不同 Agent 重复送去识图”的问题；现有文字索引和接触表是范围级发现结果，不能替代逐帧账本。

每条记录使用稳定 `recordId`，并至少包含 `sourceAssetId`、`sourceSha256`、`sourceMs`、`frameExtractionSpec`、`analysisPromptVersion`、`provider`、`model`、`analysisStatus`、`frameRef`、`observedVisuals`、`riskFlags`、`createdAt`。`analysisStatus` 只能是 `completed`、`failed`、`timeout` 或 `superseded`。同一 `sourceAssetId + sourceSha256 + sourceMs + frameExtractionSpec + analysisPromptVersion + provider + model` 是精确复用键。参与改判链的记录另有字段：改判产生的新记录带 `supersedesRecordId` 和非空 `correctionSource`；被改判的旧记录由工具自动写入 `supersededBy` 与 `supersededAt`。

每次多模态调用前必须先查账本：

```powershell
python skill/video-edit-plan/scripts/g3_visual_observation_ledger.py --ledger <G3-视觉观察账本.json> --lookup <精确复用键.json>
```

`--lookup` 默认只返回 active 记录：命中 `completed` 即复用文字观察；命中 `failed/timeout` 即回显该状态并停止静默重试；未命中才可抽取和分析，并立即通过 `--append <观察记录.json>` 写回账本。该工具拒绝与现有 active 记录重复的精确键。人工指认观察有误时必须走 `--supersede <改判载荷.json>` 改判：载荷含 `supersedesRecordId` 与完整 `newRecord`，新记录必须保持原记录的精确复用键并登记非空 `correctionSource`；旧记录进入 `superseded` 终态，不再被 lookup 或下游计划复用，`--lookup --history` 可读取完整改判链供审计。`analysisPromptVersion` 与 `model` 只能因真实更换提示词或模型而改变，禁止把改判伪装成版本变更来绕开查重。已分析的接触表只可作为范围级线索，精确候选验证帧则以账本记录为准；最终片段的 `visualVerification` 必须以 `derivedFromObservationIds` 回链账本，G3 校验器传入 `--ledger` 后，非 active（`superseded`/`failed`/`timeout`）或不存在的记录不能作为放行证据。仅当源 SHA 改变、时间点未覆盖、用户要求更高置信度/更密采样、明确变更模型或提示词、用户授权重试失败记录，或人工指认观察有误需 supersede 改判时才允许重新分析。

缓存索引只用于候选定位。某一候选要进入最终时间线时，仍只对该候选提取起点、中点、终点帧进行局部验证；不得以此为由重新扫描全片。

顶层还必须记录：

- `projectId`
- `node: G3`
- `status: completed` 或结构化 `blocked`
- `analysisScope`
- 多模态 provider、模型、prompt 版本和运行时间
- 失败/超时帧及原因；失败不能伪装为完成

## 门禁

只有 `status: completed` 且包含目标素材、哈希、关键帧和逐帧结构化结果，才能用于目标主体候选筛选。G3 validator 接受计划参数 `--visual-analysis <manifest>` 并校验项目 ID、节点、完成状态、目标 assetId/SHA-256 和关键帧结果。

G1 的参考视频技术分析只用于风格规则；历史 provider-specific 视觉分析 manifest 只覆盖其自身列明的素材，不能冒充其他素材的分析。模型无法可靠区分具体机体时，必须保留 `uncertain` 或 `mixed`：这类帧不自动入选，只进入不可用素材统计；身份分歧通过观察账本的 supersede 通道以实际帧证据改判解决。人工唯一审批是 G3 最终八列回显与 `确认 G3`，不设逐帧人工确认。
