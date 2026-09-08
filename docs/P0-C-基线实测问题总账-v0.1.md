# P0-C 基线实测问题总账 v0.1

项目：`kshatriya-intro-001`  
范围：未修改 skill 代码的真实 G0–G5 跑通；G5 已完成人工确认。  
统计口径：纸面审查的“瑕疵”与现场编号发现均计入；不把正面控制项重复算成缺陷。

## 统计结论

- **共记录 30 项**：纸面瑕疵 1–3 共 3 项；编号发现 ⑤–㉛ 共 27 项（㉛ 为 2026-09-08 修复阶段对复用机制复查时新增）。
- **需要统一修复或做设计决策：26 项**。
- **观察/预期行为：2 项**：⑦（参考素材哈希登记待决策）、⑩（640×360 低清预警按合同正常触发）。
- **正面控制项：1 项**：⑬（G2 缺依赖时结构化 blocked，未编造/未静默跳过）。
- **本轮没有边跑边改 skill 代码**；项目产物中的必要重渲与字幕修复仅用于完成基线证据，正式改动留到统一修复批次。

## 按性质统计

| 类别 | 数量 | 编号 |
|---|---:|---|
| 卡片、合同、schema 与审批设计 | 14 | 瑕疵1、瑕疵2、瑕疵3、⑧、⑫、⑯、⑰、⑲、⑳、㉑、㉔、㉖、㉗、㉘ |
| 脚本、运行时与产物链实现 | 11 | ⑥、⑨、⑭、⑮、⑱、㉒、㉓、㉕、㉙、㉚、㉛ |
| 质量保障/能力降级 | 2 | ⑤、⑪ |
| 观察或合同预期 | 2 | ⑦、⑩ |
| 正面控制 | 1 | ⑬ |
| **合计** | **30** | |

## 逐项清单

### 纸面瑕疵

- **瑕疵1**：v1.1 质量字段进入 SKILL.md，但没有同步进入固定 G3/G5 卡片模板；人工审批可能对着旧清单。
- **瑕疵2**：G0/G2 卡片示例残留旧路径 `工作区/素材包/<projectId>/…`。
- **瑕疵3**：G1 示例过于具体，存在标题/风格锚定照抄风险。

### 编号发现

- **⑤**：G1 参考视频分析复用只有合同约束，没有脚本强制；项目级缓存不能自动验证跨项目复用。
- **⑥**：G0 模板字段与 `material_pack.py` 标签不一致，按模板填写会使 register 必失败。高优先级真 bug。**状态：已验证（2026-09-08）**；已将初始化模板统一为六个机器字段与唯一的 `BGM decision` 行，未放宽解析器。验证：`~/.local/bin/python3 skill/material-pack-intake/tests/test_material_pack.py`（8/8 通过）；模板驱动的 `init → register → validate` 正向 CLI 回归通过；非法 `BGM decision` 负向 CLI 回归继续返回 `incomplete`。修复提交：`ad5d7c4`（Fix G0 template field contract）。
- **⑦**：风格参考未纳入 material-pack 哈希清单，跨项目缓存命中需要手工 SHA-256 比对。观察/待决策。
- **⑧**：固定回显卡与批准串没有机器强制，Agent 漏弹回显时用户无法按合同复核。**状态：已验证（2026-09-08）**；G1–G5 现均要求节点处于 `review_required`、登记通过校验的固定回显门禁收据，并以当前节点精确确认串 `确认 Gx` 才能推进。收据固定检查卡片类型、完整 checklist、项目内卡片/证据/依据引用；返工会清除旧收据和审批。验证：`~/.local/bin/python3 skill/p0-c-pipeline/tests/test_pipeline_state.py`（7/7 通过，覆盖五节点无收据阻断、错误确认串阻断、收据完整性、G2 引用和返工失效）。修复提交：`339da03`（Enforce node review gates and readable timecodes）。
- **⑨**：`g1_direction.py write` 写入旧路径，违反项目布局合同。
- **⑩**：源素材 640×360@23.98fps，低清 warning 正常触发，不是脚本 bug。
- **⑪**：macOS `say` 音色缺失时静默回退英文，中文几乎不读；需 ASR 回环自检。**状态：已验证（2026-09-08）**；新增 G2 `local_tts.py` 统一配音合成入口：合成前用 `say -v ?` 预检声线，未安装即 `missing_voice` 结构化 blocked，macOS 静默回退被机器拦截；可选 `--verify-asr` 用受控 Faster-Whisper 运行逐句回读，归一化文本相似度低于阈值即阻断，`--asr-initial-prompt` 传入专名词表防止 ASR 误听专有名被误归因于音色。验证：`~/.local/bin/python3 skill/media-evidence-prep/tests/test_local_tts.py`（3/3 通过；含未安装音色阻断，及受控运行时下婷婷合成→whisper 回读相似度 ≥0.6 的端到端用例）。修复提交：待本批次验收后创建。
- **⑫**：原始设计没有 BGM 内容/节奏分析能力；这是新增 Skill 设计，不是代码遗失。
- **⑬**：G2 缺依赖时结构化 blocked，行为正确，作为正面控制项。
- **⑭**：Faster-Whisper 路径、模型目录与 CLI 参数没有被脚本化声明，运行依赖靠环境变量 workaround。**状态：已验证（2026-09-08）**；`g3_align_narration_audio.py` 按 `local_transcribe.py` 的受控运行时模式重写：`P0C_FASTER_WHISPER_HOME` 加载运行时包，新增 `--model-dir`（缺省 `P0C_FASTER_WHISPER_MODEL_HOME`）与 `--language`，只用本地缓存快照；缺目录/缺快照/缺依赖均返回结构化 `blocked` 退出码 2（不再顶层 import、不再 traceback、禁止下载），同音频+模型+语言按 `cacheKey` 直接 `reused`。验证：`~/.local/bin/python3 skill/video-edit-plan/tests/test_g3_align_narration_audio.py`（4/4 通过，三类 blocked 均为可解析 JSON、无 traceback）。修复提交：待本批次验收后创建。
- **⑮**：macOS `say` 直接输出 wav 的格式兼容问题，需要 CAF→FFmpeg 转换 workaround。**状态：已验证（2026-09-08）**；workaround 固化进 `local_tts.py`：`say --data-format "LEI16@22050" -o *.caf` 后 FFmpeg 转 22050Hz 单声道 wav，两步都核验产物真实落盘且非空（沿用㉒规则），不再靠调用方临场处理。验证：与⑪同一 `test_local_tts.py`（真实中文句子合成出可探测时长的 wav）。修复提交：待本批次验收后创建。
- **⑯**：BGM onset/卡点产物没有可运行生成脚本，无法机器复现。
- **⑰**：G2 文本估时与实际 TTS 时长偏差约 40%，应先合成再估时。**状态：已验证（2026-09-08）**；`local_tts.py` 输出逐句 `durationMs` 与 `measuredTotalDurationMs` 配音清单（`G2-配音清单-v0.1.json`）；合同改为：旁白已合成时 `narrationEstimatedDurationSec` 必须取实测值，未合成才可文本估计并须标注，G2 声音卡试听记录强制附实测总时长。验证：`test_local_tts.py` 断言总时长=逐句之和且逐句>100ms。修复提交：待本批次验收后创建。
- **⑱**：脚本要求 `sourceEvidence[].relativePath`，evidence contract 未声明该字段。**状态：已验证（2026-09-08）**；`relativePath` 已成为 G2 evidence contract 的必填字段，G3 抽帧脚本会拒绝缺失或越出素材包的路径。验证：`~/.local/bin/python3 skill/video-edit-plan/tests/test_validate_g3_plan.py`（26/26 通过）；黑盒 `missing`、`escape` 路径均被结构化拒绝，合法路径可进入 G3 消费。修复提交：`a29f951`（Unify G2 G3 evidence and approval contracts）。
- **⑲**：目标主体人工确认门与项目所有者裁决冲突；应改为 Agent 自动闭环 + 充分性分流，人工只看最终 G3 回显。**状态：已验证（2026-09-08）**；目标主体确认重定义为政策级一次性确认：`userConfirmed` 只确认主体身份、识别规则与排除规则，不再要求逐片段人工确认；Agent 以实际抽帧与观察账本证据逐帧判定 `identityStatus`，`uncertain/mixed/person_only/not_present` 一律不入选、只进入不可用统计；人工唯一审批为最终八列回显与 `确认 G3`。目标主体素材不足时，仅当确认文件含完整 `sufficiencyFallback` 预授权（`preApproved: "shorten_output"` + `approvedBy`/`approvedAt`）才可自动采用缩短成品，且预授权不免除最终回显；未预授权必须停下列出缺口并呈现三项选择。`validate_g3_plan.py` 新增可选 `--subject-confirmation` 与 `--ledger`：校验政策确认完整性与账本活性，`approved_for_g4` 的 `timelineReview.basisRefs` 必须引用两者，每段观察回链必须为 `completed` 的 active 记录；不传新参数的历史计划保持兼容。验证：`~/.local/bin/python3 skill/video-edit-plan/tests/test_validate_g3_plan.py`（30/30 通过，含未确认政策、预授权字段不完整与 superseded 观察作证据的负向阻断）。修复提交：`f0ce687`（Automate G3 subject closure and ledger supersede chain）。
- **⑳**：视觉账本没有正式 supersede/作废通道，只能升 promptVersion 变通。**状态：已验证（2026-09-08）**；`g3_visual_observation_ledger.py` 新增 `--supersede` 改判通道：载荷须含 `supersedesRecordId` 与保留精确复用键、`correctionSource` 非空的完整新记录；旧记录写入 `supersededBy`/`supersededAt` 进入终态。`--lookup` 默认只返回 active 记录，`--history` 返回完整改判链供审计；校验强制互链一致、无环、同键 active 唯一、终态不可再改判，无改判字段的老账本保持兼容。合同明确 `analysisPromptVersion`/`model` 只能因真实提示词或模型变更而改变，禁止借版本变更绕过查重实现改判。验证：`~/.local/bin/python3 skill/video-edit-plan/tests/test_g3_visual_observation_ledger.py`（5/5 通过，覆盖改判后旧记录不再复用、缺 `correctionSource`、目标不存在与复用键漂移阻断）。修复提交：`f0ce687`（Automate G3 subject closure and ledger supersede chain）。
- **㉑**：G2 决定 schema 与 G3 validator 漂移，顶层字段与 FILE ref 要求未对齐。**状态：已验证（2026-09-08）**；G2 与 G3 统一使用 `approvedNarrationRef`、`factCitationRef`、`voiceBriefRef`，且引用必须为项目内真实文件而非目录；G3 直接复用 G2 decision validator。验证：`~/.local/bin/python3 skill/video-edit-plan/tests/test_validate_g3_plan.py`（26/26 通过，含合法 G2→G3 闭环、旧字段拒绝和目录引用拒绝）；`~/.local/bin/python3 skill/p0-c-pipeline/tests/test_pipeline_state.py`（7/7 通过，G2 审批字段与门禁同步）。修复提交：`a29f951`（Unify G2 G3 evidence and approval contracts）。
- **㉒**：末尾抽帧 ffmpeg 退出 0 但不落盘，脚本不检查文件存在。**状态：已验证（2026-09-08）**；两个抽帧脚本（验证帧、关键帧）对每张帧图核验存在且非空，未落盘时以 100ms 步长最多回退 500ms 重试，清单同时记录 `requestedSourceMs` 与实际 `sourceMs`，回退窗口内仍无产物即结构化失败；`g4_assemble.py` 复用同一"产物必须真实存在"规则。验证：`~/.local/bin/python3 skill/video-edit-plan/tests/test_g3_frame_extraction.py`（5/5 通过，真实 ffmpeg 正向落盘、假成功 shim 拒绝、末尾边界回退到 1499ms 均被断言）。修复提交：`20497ee`（Make frame extraction, caption layout, and G4 assembly machine-verified）。
- **㉓**：G0 音频 register 只哈希不解码探针，损坏网易云加密文件一路流到 G3 才暴露。
- **㉔**：用户回显没有规定人类可读时间码，首版裸毫秒不可读。**状态：已验证（2026-09-08）**；G3 最终回显保留整数毫秒为唯一机器真相，并强制由切点派生 `outputTimecode`、`sourceTimecode`（`mm:ss.mmm`）后生成固定八列 Markdown 卡。validator 会拒绝缺失或与毫秒不一致的展示时间码。验证：`~/.local/bin/python3 skill/video-edit-plan/tests/test_validate_g3_callback.py`（9/9 通过，含格式化边界、缺失/漂移阻断和渲染器）。修复提交：`339da03`（Enforce node review gates and readable timecodes）。
- **㉕**：`g4_prepare.py` 不读取 `durationDecision`，产出 `targetDurationMs:0`。
- **㉖**：G3 ASS 字号20下长句折三行，违反自身 maxLines=2；没有行数/宽度机器校验。**状态：已验证（2026-09-08）**；新增 `validate_g3_subtitle_layout.py`：对照 `G3-字幕布局合同` 的 `lanes.narration.fontsize/maxLines` 强制 ASS 样式字号一致，并按 PlayResX、样式左右边距与保守字符宽度模型（全角 1em、半角 0.55em，空格与任意字符处可断）估计每条 cue 渲染行数，超过 `maxLines` 即拒绝；合同规定未过机器校验不得进入最终回显，`approved_for_g4` 放行清单加入"字幕布局机器校验通过"。注：模型刻意保守，对已交付 v0.3 的临界长句也报超行（该 cue 已由人工播放接受），估计语义已在合同注明。验证：`~/.local/bin/python3 skill/video-edit-plan/tests/test_validate_g3_subtitle_layout.py`（6/6 通过，含字号漂移拒绝、自动折行三行拒绝、`\N` 硬换行超限拒绝）。修复提交：`20497ee`（Make frame extraction, caption layout, and G4 assembly machine-verified）。
- **㉗**：G4 没有最终合成脚本入口，concat、混音、字幕烧录、封面合成依靠临场 FFmpeg。**状态：已验证（2026-09-08）**；新增 `g4_assemble.py` 作为压平预览/成片的唯一入口：按清单顺序核验切片存在非空、旁白不短于时间线，单遍 filter_complex 完成 concat+fps 归一、可选 libass 字幕烧录（缺 libass 时结构化拒绝）、口播与 BGM 混音（`--bgm-duck` 侧链压缩）、可选封面 drawtext 合成，产出 `<成片名>-装配记录-v0.1.json`（全部输入哈希、滤镜图、实测时长）供 G5 审计；SKILL.md 执行链同步，禁止临场拼接命令。验证：`~/.local/bin/python3 skill/local-video-render/tests/test_g4_assemble.py`（5/5 通过，真实 ffmpeg 合成含烧录+ducking+封面，缺切片与短旁白负向阻断）。修复提交：`20497ee`（Make frame extraction, caption layout, and G4 assembly machine-verified）。
- **㉘**：人工 QA 否决系统 TTS 的人机感；G2 没显式标注系统 TTS 仅预览级，也没有在声音卡上强制神经 TTS/真人替代路径。**状态：已验证（2026-09-08）**；声音卡每个选项新增强制"成片分级"列：神经 TTS（如已授权百炼 CosyVoice）/真人可为成品级，macOS 系统声音一律预览级且必须注明人机感与升级路径，未告知分级不得让用户按"能听"通过；`local_tts.py` 清单固定输出 `voiceTier: preview_only` 与分级说明，试听确认字段加入分级与实测总时长；G2 SKILL 与选择卡合同同步。修复提交：待本批次验收后创建。
- **㉙**：`g4_prepare.py` 固定写 `G4-可编辑工程-v0.2.json`，重跑会覆盖上一批次清单。
- **㉚**：`g4_render.py --output-dir` 直接平铺切片，与合同约定的 `clean-segments/` 子目录语义不一致。
- **㉛**（2026-09-08 复用机制复查新增）：G3 全片关键帧抽取无代码级缓存复用——`cacheKey` 只写在合同里，重跑必重新抽帧，下游再烧识图 Token；且 `analysisScope` 把间隔硬编码为 15000ms。**状态：已验证（2026-09-08）**；`g3_extract_visual_analysis_keyframes.py` 引入抽取级 `cacheKey`（`assetId`+SHA-256+范围+`intervalMs`）并在抽取前扫描输出目录与 `--cache-root`：同键且全部帧图真实存在 → `cache_hit` 直接返回；键不同 → 写新版本文件不覆盖旧 manifest；帧图缺失 → 同键原地重建；`analysisScope` 按实际间隔生成。基线实测佐证：kshatriya 账本中 18 帧曾因 ⑳ 缺改判通道被迫以 promptVersion 升版重复识图。验证：`~/.local/bin/python3 skill/video-edit-plan/tests/test_g3_frame_extraction.py`（8/8 通过，含缓存命中零重抽、间隔漂移双 manifest 共存、缺帧重建）。修复提交：待本批次验收后创建。

## 统一修复批次建议顺序

1. 先修状态、审批、schema、路径和覆盖风险：瑕疵1/2、⑥、⑧、⑨、⑱、⑲、⑳、㉑、㉒、㉓、㉙、㉚。
2. 再修可复现质量链：⑤、⑪、⑭、⑮、⑯、⑰、㉕、㉖、㉗、㉘、㉛。
3. 单独立项新增能力：⑫ BGM 内容分析；⑦ 参考素材哈希登记策略；瑕疵3 作为低优先级示例清理。

本文件只记录问题与修复顺序，不代表已经修改 skill。任何修复应在单独批次完成后重新跑针对性测试。
