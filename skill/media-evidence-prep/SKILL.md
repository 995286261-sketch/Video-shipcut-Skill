---
name: media-evidence-prep
description: 从已校验的本地素材包中准备媒体证据，包括离线时间戳转写、SRT/TXT 产物、联系表和证据溯源。适用于下游视频流程需要理解用户视频或音频、但不能使用云端服务的场景；不负责素材整理、脚本、剪辑决策、渲染或 QA。
metadata:
  pipelineNode: G2
---

# 媒体证据准备

这是 G2 证据与口播 Skill，正式项目产物写入 `工作台/<projectId>/G2-证据与口播/`。仅在 `$material-pack-intake` 校验输入包后使用；不能写回素材包。用户回显遵循 [P0-C 路径展示合同](../p0-c-pipeline/references/path-display-contract.md)；证据 JSON 和转写 manifest 中的机器路径保持原始字符串。

若任务为“参考口播稿/转写 + 自有资料 → 原创口播稿”，还必须读取 `references/g2-script-review-gates.md` 和 `references/g2-script-input-template.md`：用户已定稿段落为锁定输入，只能从用户指定锚点之后续写；事实必须逐条回指来源，参考稿只借抽象结构。

## 输入定位

1. 先读项目状态：`工作台/<projectId>/pipeline-state.json`。不得读取、修复或从归档、旧 `run-manifest.json` 推断状态。
2. 从索引或调用方参数取得素材包根目录和 `material-pack.json`。不要把交接单、审核包 README 或 G1 方向产物误当作素材包。
3. 输出目录固定为 `工作台/<projectSlug>/G2-证据与口播/`。若目录已存在，先核对已有产物与源文件哈希；不要覆盖无法确认归属的旧产物。归档产物不得读取。

若输入是项目级风格参考片，而不是 G2 的事实/原始素材，交由 G1 处理，并只写入 `工作台/<projectId>/G1-创作方向/G1-参考视频分析/`。保留源文件 SHA-256、时间码和“仅风格分析”限制；不得把这类转写写进 G2 清单、当作事实依据，或视为可复用字幕/输出素材。

## 工作流

1. 读取 `references/evidence-contract.md`。
2. 对照 `material-pack.json` 校验每个选中本地源文件的 SHA-256、授权字段和媒体探测信息；发现不一致时停止。
3. 为每个视频源生成低成本联系表，文件命名为 `<asset-short-id>-contact-sheet.jpg`，只用于人工定位画面类别和下游精看片。
4. 视频没有可用字幕/文稿时，用配置好的离线 Faster-Whisper 模型运行 `scripts/local_transcribe.py`，并传 `--source-pack` 指向素材包根目录以启用输出边界校验。脚本会从 `P0C_FASTER_WHISPER_HOME` 加载受控运行时，并优先使用 `P0C_FASTER_WHISPER_MODEL_HOME` 中唯一的缓存快照；禁止上传云端、下载模型或让运行时刷新模型缓存。缺少运行时或缓存模型时返回 `blocked`，报告给调用方。
   在运行前先检查已有转写 JSON 的 `cacheKey`；源 assetId、SHA-256、语言、模型、设备、compute type 和运行时版本一致时直接复用，不得重复转写。
5. 对每份转写运行 `scripts/write_transcript_artifacts.py`（同样传 `--source-pack`），生成 `transcript.srt`、`transcript.txt` 和 `manifest.json`，并校验时间轴单调、不重叠、`segmentId` 唯一。
6. 汇总生成 `G2-证据准备报告-v0.1.md` 和 `G2-证据清单-v0.1.json`。报告给人看，JSON 给 G3 机器读取。随后读取 `references/g2-choice-cards.md`，用事实处理卡、口播方向卡和继承的音频策略生成自动回显；回显不是人工审批。
7. 更新项目索引中的 G2 节点产物路径和状态；下一节点应指向 G3 编辑计划。

## Pipeline Integration

Read `工作台/<projectId>/pipeline-state.json` and accept only state-registered inputs; archived files are never inputs. Record only G2 output references, warnings, and review points through `$p0-c-pipeline`; do not advance G3. Read `references/g2-choice-cards.md` before presenting G2 decisions. Before G2 approval, generate a short local voice audition and explicitly confirm language, accent, voice type, and speaking rate; record its reference as `voiceDecisionRef`. A narration is invalid for G3 until G2 approval registers `approvedNarrationRef`, `factDecisionRef`, and `voiceDecisionRef`.

## 标准产物

在 `工作台/<projectSlug>/G2-证据与口播/` 下至少生成：

- `G2-证据准备报告-v0.1.md`：写明输入核验、可供 G3 使用的证据、限制、给 G3 的交接。
- `G2-证据清单-v0.1.json`：包含 `projectId`、`status`、`evidencePolicy`、`sourceEvidence[]`、`factEvidenceRefs[]` 和 `handoff`。
- `<asset-short-id>-contact-sheet.jpg`：每个源视频一张或多张，必须能回指 `assetId`。
- `转写/<asset-short-id>-transcript.json`：离线转写原始 JSON。
- `转写/<asset-short-id>/transcript.srt`、`transcript.txt`、`manifest.json`：可审阅转写产物和校验结果。

## 证据规则

- 所有时间码始终对应原始素材时间轴，不是输出成片时间轴。
- 所有机器转写均标记为草稿证据，只能帮助理解画面语境；不能自动升级为事实、口播、字幕或产品承诺。
- 风格参考转写仅支持节奏、句式、信息层级等抽象规则分析；不得写入项目事实证据、成片字幕或口播文案。
- 保留 `assetId`、源文件 SHA-256、`startMs/endMs` 和产物相对路径，供 G3/G4/G5 追溯。
- 若源素材授权为 `personal_practice_unverified` 或 `not_for_distribution`，在报告、JSON 和交接中明确禁止分发或上传第三方平台。
- 若联系表发现烧录字幕、剧情剧透、人物台词、版权音乐或其他冲突风险，只记录为 warning；不要替 G3 做镜头选择。

## 边界

- 不修改素材包中的源文件。

两个脚本的错误均为结构化 JSON（`status: invalid/blocked/failed`）写到 stdout，退出码 0=成功、2=输入非法或边界被拦截、1=运行时失败。按此解析，不要依赖 stderr traceback。
- 不将转写自动升级为已确认事实、口播或字幕。
- 不使用云端转写，也不下载模型。
- 不选择镜头，也不生成编辑计划。
- 不生成口播稿、字幕文案、封面或渲染配置。
