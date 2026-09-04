---
name: local-video-render
description: 执行 G4 本地剪辑与 ChatCut 可编辑交接。用于把已批准的 G3 编辑计划从原始视频裁成分段画面，处理源字幕/原声、生成独立口播和 BGM 轨、完成本地预览渲染，并将可编辑产物导入 ChatCut 时间线和字幕卡；禁止把压平 MP4 当作 ChatCut 时间线源。
metadata:
  pipelineNode: G4
  g4InteractionReference: references/g4-choice-cards.md
---

# G4 本地剪辑与 ChatCut 交接

G4 是单一节点、单一 Skill，正式项目产物写入 `G4_ROOT`。读取 [渲染合同](references/render-contract.md) 和 [项目布局合同](../p0-c-pipeline/references/project-layout-contract.md) 后执行。用户回显遵循 [P0-C 路径展示合同](../p0-c-pipeline/references/path-display-contract.md)；工程 JSON 和验证报告中的机器路径保持原始字符串。

当用户要求固定字幕、或预览显示字幕因自适应换行而产生位置/字号跳动时，读取 [固定字幕条合同](references/caption-style-contract.md)。

当成片需要封面、章节卡、配音、背景音乐或烧录字幕时，必须读取 [客户演示成片质量补丁](references/demo-quality-patch.md)。该补丁来自 TASK-050 的实际渲染与人工评审，优先于本文件中与画幅、旁白和最终合成有关的旧默认值。

执行入口：先运行 `scripts/g4_prepare.py` 生成 `G4-可编辑工程-v0.2.json`，再运行 `scripts/g4_render.py` 按该清单裁切，使用 `scripts/g4_build_handoff.py` 生成交接包，最后运行 `scripts/g4_validate.py` 验证清单及交接包。不要使用项目 `work/` 中的临时脚本作为新项目执行入口。

## 前置门禁

- 只接受状态为 `approved_for_g4` 的 G3 编辑计划。
- 使用计划中登记的源资产、口播稿、BGM、目标规格、`durationDecision` 和源音频策略；不根据文件名或最近修改时间猜输入。
- 只能执行 G3 已登记的设计性留白；不得通过重复片段、循环 BGM、无意义慢放或更改播放速度自行消化时长差异。
- 核对源文件哈希。任何不登记的音乐、字体、参考视频或素材都不得写进输出。
- 所有产物写入 `G4_ROOT`；中间文件只能放其 `work/`。归档目录不得读取。保持原始媒体不变。
- 外部编辑器（包括 ChatCut）下载的最终交付文件不得留在 `Downloads` 或临时盘符，必须写入 `CHATCUT_EXPORT_ROOT` 的新批次；绝不覆盖已有批次。
- 未明确指定目标画幅时，使用 `aspectRatioPolicy: preserve_source`，按主素材或批准计划的画幅输出；不得把横版或竖版一律强制改成 16:9。
- 封面、章节卡、字幕和 CTA 属于图形层。每次最终渲染前确认输入是无新字幕、无新章节卡、无新 CTA 的 clean master；已压平版本不得再次作为图形渲染源。

## 阶段 A：本地剪辑产物

1. 按 G3 的镜头顺序和源时间码，逐段从原始视频裁出 `seg-001.mp4`、`seg-002.mp4`…；记录 `segmentId`、源资产、源起止时间、输出顺序和时长。
2. 对源字幕、频道边框或其他画面污染执行 G3 批准的裁切/遮罩。底部烧录字幕方案若规定裁屏，按批准比例（本项目为底部约 14%）处理；之后统一缩放/补边/裁切到目标画幅。
3. 移除原片音频。画面切片不得混入口播、BGM 或烧录的新字幕。
4. 分别生成/保留独立口播音频、独立 BGM 与可编辑字幕参考（SRT/审核稿）。
   - 默认字幕参考可保持 SRT；若选择 `fixed_bottom_band`，在压平预览/成片前将审核过的字幕转换为具固定锚点与固定字号的 ASS 样式。不得依赖渲染器的自动换行、自动字号或逐句动画。
   - 旁白按完整句子分别生成或切分，只在句子边界安排章节卡或新增画面停顿。字幕起止时间必须来自实际生成音频的时长或转写对齐结果，不得按字符数估算。
   - BGM 和旁白保持独立文件；混音时旁白优先，旁白出现期间对 BGM 做 ducking。不得用复制左右声道的方式伪造立体声，也不得意外叠加两份同一旁白。
5. 做本地技术检查：每段分辨率、fps、时长、无原声；切片总长与目标时间线的误差仅可来自帧取整。
6. 可制作压平预览 MP4 做 QA，但它仅是预览参考，绝不是 ChatCut 工程输入。

### 客户演示成片补充

- 正片前需要专用封面时，从已登记素材中选择最具代表性且清晰度合格的一帧，叠加品牌名称和主题；封面时长、是否口播、是否显示字幕均写入批准计划。
- 章节卡标题长度驱动展示时间，通常 1.2–1.5 秒；若章节卡覆盖旁白，必须从完整句子的自然边界开始，不能截断单词起音。
- 章节卡显示期间隐藏正文字幕，避免双重文字层竞争。
- 结尾 CTA 必须与业务目标和目标平台规则一致；不得凭空加入未确认的联系方式、承诺或品牌事实。
- 封面、正文字幕和 CTA 都先抽帧检查，再交付完整视频。

## 阶段 B：ChatCut 可编辑交接

1. 读取目标 ChatCut 项目的当前时间线，确认画幅/fps，避免覆盖现有内容。
2. 分批导入阶段 A 产物：每批最多四个文件。导入所有分段画面、口播、BGM；封面可放素材库但不自动入时间线。
3. 等每项可用后，将每个 `seg-*` 按精确帧连续排入 V1，保留每个切片边界，不能拼成一个单视频。
4. 将口播放入 A1，BGM 放入 A2；按 G3 批准的音量、淡入淡出设置原生音频参数。不得混入原片声音。
5. 从 A1 口播创建 ChatCut 可编辑字幕卡。自动识别只作初稿：按审核口播稿/SRT 修正专名、错字、断句和卡片时序。
6. 若 ChatCut 单源字幕筛选失效，可先用全部可听轨生成，再用字幕卡来源验证只来自 A1；BGM 不应生成文字。

## Visual verification hard gate

Before any G4 cut, every segment must carry `visualVerification.status=verified`, a frame manifest reference, start/middle/end frame references, and an observation based on the actual extracted frames. Candidate, estimated, contact-sheet-only, or `manual_identity_check` timecodes are blocked. G4 must never silently “fine tune” an unverified range.

## G4 routing update

Read `references/g4-choice-cards.md` before execution. The default branch is local rough-cut and render preview from the approved G3 plan. ChatCut handoff is optional and is entered only when the user requests micro-adjustments or an editable ChatCut project. For local-direct output, a validated local candidate plus explicit user review can route to G5; do not require an unrequested ChatCut export.

## Pipeline Integration

Read `工作台/<projectId>/pipeline-state.json` and work only at G4. Register local render, editable handoff, validation report, and the actual ChatCut export reference through `$p0-c-pipeline`. Do not advance to G5 without user-confirmed export.

## 验收

- V1 有多段可单独移动、裁剪、替换的画面；没有压平成品 MP4。
- A1 是连续的独立口播；A2 是可独立调音的 BGM。
- CC 能显示可编辑字幕卡；字幕随 A1 口播，不随画面切点漂移。
- 复核开头、切点、结尾以及术语；输出本地渲染报告、切片清单、字幕参考和 ChatCut 交接状态。所有产物路径必须写成可点击的 Markdown 超链接 `[文件名](相对路径)`。
- ChatCut 导出后，确认下载是否完成并把文件写入 `CHATCUT_EXPORT_ROOT`。仅报告实际找到并移动的文件；缺失的字幕或封面必须明确标记为未找到，不能拿工作台或历史工作区的草稿文件冒充导出件。
- 最终成片必须通过 FFmpeg 完整解码；检查封面存在且可读、字幕与实际旁白同步、章节卡不截断语音、无重复声道/重复旁白、无二次烧录文字，并保存至少一张封面检查帧和一张字幕检查帧。

## 故障处理

- 上传/数据库超时：先读取素材库与时间线，确认是否已部分成功；只续传同一资产，避免重复注册。
- 字幕源为空：恢复自动生成再核对卡片 source；不要因为筛选错误删除已有字幕卡。
- 口播被意外拆开：检查相邻片段的帧边界与 source offset，恢复无缝连续；不要重置字幕文字。
