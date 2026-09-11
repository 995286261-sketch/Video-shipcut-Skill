---
name: music-expert
description: 对音乐做确定性分析与找乐：分析任意音频或参考视频音轨的 BPM、节拍、起音、卡点表、能量分段与响度，产出可复用的分析报告和风格简报；找乐三轨——Freesound 自动检索（带真实许可证据链）、网易云搜索（中文全曲库试听选型，候选一律标未清权）、人工下载加许可证据登记（Pixabay/Mixkit/官方渠道整轨）；受控标签词表做主题粗匹配；再与口播时间轴做节奏对齐（轨偏移、高潮锚点、句边界卡点吸附、ducking 区间）并出混音合同（可听窗守卫）。作为 BGM 领域专员已接入六节点（G0 登记链、G1 音轨分析、G2 节拍蓝图、G3 对齐、G4 混音合同、G5 链审计）。适用于需要理解或获取背景音乐的场景；不负责素材包整理、剪辑决策、渲染、QA 或交付。
metadata:
  pipelineNode: support
---

# BGM 专家（music-expert）

覆盖基线总账 ⑫（缺 BGM 内容/节奏分析）与"AI 自动找 BGM"的确定性前置，把过去只能靠运行时临场发挥的音乐能力沉淀为可复现、可审计的本地引擎。本 Skill 是**领域专员**（`pipelineNode: support`）：音乐决策全在这里出合同，节点型专员只逐字执行（用户 2026-09-10 定调）。范围四块：确定性分析引擎、找乐三轨、需求打分推荐、对齐与混音合同。接线现状见 `references/sourcing-contract.md` 末节（G0/G1/G2/G3/G4/G5 已通，仅 G0 `use_library_later` 自动调检索未接）。

合同先行：动手前读 `references/music-analysis-contract.md`、`references/sourcing-contract.md`、`references/style-brief-contract.md`、`references/search-terms-contract.md`；来源选型的实测证据在 `references/library-probes.md`。

## 执行入口（唯一）

- 分析：`scripts/music_analyze.py`。找乐自动轨道（真实许可）：`scripts/music_search_freesound.py`。找乐试听选型轨道（中文全曲库，候选写死未清权+internal_test）：`scripts/music_search_netease.py`。找乐人工轨道：`scripts/music_register_candidate.py`（主题标签必须用 `references/tag-vocabulary.md` 受控词表）。推荐排序：`scripts/music_recommend.py`（画像可带 `styleBrief` 锚定与 `styleTags` 粗匹配）。模型试听笔记：`scripts/music_listen_omni.py`（可选增强层，见合同；无听觉能力时结构化提示，绝不编造）。节奏对齐：`scripts/music_align.py`。混音合同：`scripts/music_mix_plan.py`。不要用临时脚本或手敲 ffmpeg 替代。

## 前置依赖

- `ffmpeg`/`ffprobe` 在 PATH。
- 节奏/能量分析库（numpy、librosa）只能从托管运行时加载，路径由 `MUSIC_EXPERT_RUNTIME_HOME` 声明（`P0C_MUSIC_RUNTIME_HOME` 为历史别名）；缺失即结构化 `blocked`，禁止运行时下载或 pip 安装（与 faster-whisper 同一纪律）。
- Freesound 自动检索需 `MUSIC_EXPERT_FREESOUND_TOKEN`（历史别名 `P0C_FREESOUND_TOKEN`）；缺失即 `blocked`，不静默换到无授权来源。
- 模型试听笔记层需具备**听觉分析能力**（默认百炼 `bl`，`P0C_BL_BIN` 可指向其他兼容 CLI 或本地开源音频模型包装）；探测不过 → 结构化 `capability_missing` 并明确告知用户"当前模型没有听觉分析能力"，**不允许以任何文字冒充听过**。
- 本 Skill 不假设任何仓库内路径或宿主目录：输入输出全靠显式参数，依赖全靠环境变量，可整体迁移到其他仓库或平台。

## 工作流

1. 要理解一段音乐或某个参考视频的配乐感觉 → `music_analyze.py --input <文件> --output-dir <目录>`，需要风格简报再加 `--style-brief-out`。每次分析自动产出《BGM-分析回显》固定表格卡（头部简述+逐段分析表，样式与剪辑 skill 的回显卡同源）；重跑同文件同版本命中 `cache_hit` 不重算，卡丢了可从报告 JSON 免费重渲，请求过的简报也会从缓存报告免费重派生。简报的 `energyShape` 是最多 16 桶的宏观曲线（滤掉解说音轨逐句 ducking 噪声），详见 style-brief-contract。
2. 要自动找候选 → `music_search_freesound.py --query/--tags/--similar-to ... --output-dir <目录>`，得到带授权证据链的候选清单。
2.5 要在中文全曲库里找审核者听过的歌（内测选型）→ 先出检索词卡（见 2.6），再 `music_search_netease.py --terms-file <检索词json>`（逐词检索合池去重；单查也可 `--query`）+ `--output-dir <目录>`（可选 `--no-preview`）。候选一律 `uncleared-platform-catalog`：试听件只用于选型，整轨必须由人经官方渠道取得后走第 3 条登记，**试听件直接进成片是红线违规**；风控/网络失败结构化 `blocked`，不静默换源。
2.6 检索词怎么来 → 按 `references/search-terms-contract.md`：**Agent 推导（口头偏好＞主题翻译＞风格简报锚定，简报可选；口播稿不做主源），脚本不编造曲库命中** → `music_search_terms.py --term <词>… --note "词=依据"…`（可选 `--preference/--theme/--style-brief/--timeline-ms`）出《BGM-检索词-v0.1》+回显卡：逐词标来源与推导依据、时长下限由成片时长推导、bpmRange 取自简报；卡呈用户可改后重跑，**不设门禁口令**（门禁在挑曲）。
2.7 锚定打分排出短名单后，可加"模型试听笔记"（可选，`references/listen-notes-contract.md`）→ `music_listen_omni.py --reference <用户确认的参照曲> --manifest <推荐或候选json>`：逐首与参照曲 A/B 听，产出情调差距与贴合度笔记卡；先探测听觉能力，**没有能力就明说并且一个字都不写**，调用失败如实进 `partialFailures`。笔记只是参考，不做门禁；只听短名单（`--max-tracks` 封顶）控制计费。
3. 用户手动从 Pixabay/Mixkit 等无 API 站下载了音乐 → `music_register_candidate.py --audio <文件> --license-type ... --license-evidence ... --output-dir <目录>` 登记（本脚本不联网、不复制源文件）。
4. 有需求画像（时长/BPM/能量/响度上限，可选 `styleTags` 标签粗匹配）或风格简报后 → `music_recommend.py --profile <画像.json> --candidates <候选清单...> --reports-dir <分析目录>` 打分排序；候选不足会显式报"补检索/放宽画像/缩短成品"三选一，不自行拼凑。
5. 定了曲子和口播后要做节奏对齐 → `music_align.py --report <分析报告> --voice-brief <配音清单> --timeline-ms <成片时长> --output-dir <目录>`（可选 `--climax-sentence` 高潮句、`--snap-tolerance-ms`、`--fade-ms`、`--tier-quantiles` 档位分位数）。产物是**建议**：轨偏移、高潮锚点、句边界卡点吸附（超出容差如实报 miss）、ducking/淡入淡出区间、**机器乐句表**（音轨能量段×轨偏移映射到成片时间轴并标覆盖句）与**逐句排版档位草稿**（段能量分位数定档，词表 快切/推进/常规/留白），附节点末风格的回显卡；口播时值永远是权威，卡点只做参考，不得为踩点让口播变形；档位草稿是机械建议（§6-④），最终逐行档位由 G3 终审八列回显人工定夺，消费者想改对齐数字只能改参数重跑。

   5.5 **节拍蓝图模式（N9，G2 创作期用）**：口播还没定稿、要先照鼓点写稿/改版时 → `music_align.py --blueprint --report <分析报告> --timeline-ms <目标时长> --output-dir <G2 目录>`（可选 `--climax-position-ms` 能量峰要落在成片哪个位置、`--budget-map` 各档每句秒数预算，默认 快切4-6/推进5-7/常规6-8/留白8-12）。产物 `BGM-节拍蓝图-v0.1.json` + 回显卡：鼓点栅格、乐句窗口（含档位草稿）、每句时长预算建议与建议句边界。蓝图是**创作输入不是合同**：目标时间码只是设计意图，G2 人审批准的排版稿经 TTS 实测后的配音清单时间码才是事实，G3 对齐（第 5 条）负责验证意图是否落地、偏差超限回 G2 改稿。纯旁白型项目可跳过本条。
   5.6 **混音合同（N6，G4 执行前用）**：BGM 进 G4 装配前 → `music_mix_plan.py --plan <approved_for_g4 的 G3 计划> --alignment <对齐建议-v0.2.json> --bgm-audio <BGM 文件> --output-dir <G4 目录>`（可选 `--bed-gain-db` 默认 −12、`--duck-reduction-db` 默认 6，即 §6-② 拍板参数）。**可听窗守卫**：用分析报告的轨实测响度算出口播段在位电平预估，落在 [人声目标−18, 目标−6] LUFS 窗外即拒绝出合同——zaku 教训：−18/−12 叠加=−40 LUFS"在混但听不见"，这必须是算术检查不是耳朵检查；G4 装配后还会实测在位电平与本预估对账）。产物 `BGM-混音合同-v0.1.json`+回显卡：把 G3 批准过的轨偏移/淡入淡出/逐句 ducking 翻译成 G4 可逐字执行的合同，并**三重哈希对账**（文件 sha==bgmPlan.audioSha256==分析报告 cacheKey；对齐产物 sha==bgmPlan.alignmentSha256；参数与计划逐字段相等），任何不一致即拒绝出合同。`g4_assemble.py --bgm-mix-contract` 是唯一合法消费路径——**专员决策、节点执行**（用户 2026-09-10 定调：领域能力归专员，节点型专员只排节点）。

## 边界与红线

- 源素材只读：分析不修改输入，产物只写显式输出目录。
- 授权不可含糊：没有许可证据链的音乐不进候选池；默认 `internal_test`，上调需人工复核许可条款。
- 不越界：不执行 G0 素材包登记、不做剪辑决策、不渲染、不做 QA/交付；这些属于对应节点 Skill。

## Pipeline Integration

本 Skill 不读写 `工作台/<projectId>/pipeline-state.json`，不推进任何节点，不登记门禁收据。将来与管线的接缝（G0 `use_library_later` 调检索、G3 引用卡点表、G5 审计许可）另起批次，通过 specialist SKILL 的引用接入，而非把逻辑塞进本 Skill 或节点脚本。

## 标准产物

- `BGM-分析报告-*.json`、`BGM-分析回显-*.md`、`BGM-风格简报-*.json`
- `BGM-候选清单-freesound-*.json`、`BGM-候选登记-*.json`
- `BGM-推荐-*.json`
- `BGM-对齐建议-v0.2.json`、`BGM-对齐回显-v0.2.md`（v0.2 新增 `layout` 段：`phrasesOnTimeline` 机器乐句表、`perSentence` 档位草稿、`rule` 定档参数自曝；被 `video-edit-plan` 的 `validate_g3_plan.py --bgm-alignment` 哈希消费）

## 故障处理

所有脚本以结构化 JSON 到 stdout：退出码 0=成功/复用、2=输入非法或依赖/授权被拦、1=运行时失败。缺 ffmpeg、缺分析运行时、缺 Freesound token 均为 `blocked`，错误信息指明缺哪个受控依赖及其声明变量；不得回退到下载、爬站或无授权来源。

## 资源

- `SKILL.md`：本使用合同。
- `agents/openai.yaml`：平台卡片。
- `references/music-analysis-contract.md`：分析报告与 cacheKey 合同。
- `references/sourcing-contract.md`：三轨找乐与授权证据合同。
- `references/style-brief-contract.md`：参考视频→风格简报合同。
- `references/tag-vocabulary.md`：主题标签受控词表（单一事实源为 `scripts/music_tags.py`）。
- `references/library-probes.md`：曲库与引擎选型实测结论。
- `references/search-terms-contract.md`：检索词生成合同（专员侧 I/O 固化）。
- `references/listen-notes-contract.md`：模型试听笔记合同（能力探测、不编造纪律、成本封顶）。
- `scripts/music_analyze.py`、`scripts/music_search_terms.py`、`scripts/music_search_freesound.py`、`scripts/music_search_netease.py`、`scripts/music_register_candidate.py`、`scripts/music_recommend.py`、`scripts/music_listen_omni.py`、`scripts/music_align.py`、`scripts/music_mix_plan.py`：九个唯一入口（`music_tags.py` 共享词表、`music_echo.py` 固定表格回显卡渲染模块）。
- `tests/`：analyze / sourcing / recommend / align / search-terms / netease / listen-omni / mix-plan 确定性与阻断回归（含"无能力不编造"三例）。
