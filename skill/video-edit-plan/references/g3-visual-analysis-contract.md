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
- `identityStatus`：`confirmed`、`uncertain`、`not_present` 或 `mixed`
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

每条记录使用稳定 `recordId`，并至少包含 `sourceAssetId`、`sourceSha256`、`sourceMs`、`frameExtractionSpec`、`analysisPromptVersion`、`provider`、`model`、`analysisStatus`、`frameRef`、`observedVisuals`、`riskFlags`、`createdAt`。`analysisStatus` 只能是 `completed`、`failed`、`timeout` 或 `superseded`。同一 `sourceAssetId + sourceSha256 + sourceMs + frameExtractionSpec + analysisPromptVersion + provider + model` 是精确复用键。

每次多模态调用前必须先查账本：

```powershell
python skill/video-edit-plan/scripts/g3_visual_observation_ledger.py --ledger <G3-视觉观察账本.json> --lookup <精确复用键.json>
```

命中 `completed` 即复用文字观察；命中 `failed/timeout` 即回显该状态并停止静默重试；未命中才可抽取和分析，并立即通过 `--append <观察记录.json>` 写回账本。该工具拒绝重复精确键。已分析的接触表只可作为范围级线索，精确候选验证帧则以账本记录为准；最终片段的 `visualVerification` 必须以 `derivedFromObservationIds` 回链账本。仅当源 SHA 改变、时间点未覆盖、用户要求更高置信度/更密采样、明确变更模型或提示词，或用户授权重试失败记录时才允许重新分析。

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

G1 的参考视频技术分析只用于风格规则；历史 provider-specific 视觉分析 manifest 只覆盖其自身列明的素材，不能冒充其他素材的分析。模型无法可靠区分具体机体时，必须保留 `uncertain` 或 `mixed`，并转入人工确认。
