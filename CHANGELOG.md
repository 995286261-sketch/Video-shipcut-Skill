# 变更记录

## v1.3.0 — 2026-09-18 — **BGM完善版本**

发布范围＝以下四批（单卡交互合同、主线接线①G0/②G1、music-expert N10+锚定打分）＋发布期内追加：

- **N8 测后裁决 26 条四批修复**（52c072c/27c6815/c6d5f09/19d2b9d）：validate_g3_plan 批量报错、评审/审批模式对称、g4_prepare 工作台守卫、drawtext 字形覆盖预检（TTC 首-face 陷阱红线）、《交付包组件 Schema》唯一事实源、口令归一化下沉等；回归 7 套全绿。
- **找乐通道路由定案**（d5ae193）：对外=Freesound 默认轨、个人/内测=网易云可留，通道在 G1 末回显卡可切换；**Freesound 首次活体接通**（5709f21）：CC URL 许可分类器修复 + preview 键名/短链派生漂移修复 + 3 组回归。
- **G0 卡 BGM 通道预告**（19c862c）：问题 5 选项 B 写明检索通道与切换点。
- **正式验收录制闭环**（方案 A）：psycho-zaku-intro-002 G0–G5 六门禁全过（09-18 `确认G5`），交付包 v0.1 封存 valid/completed，`确认交付≠逐条接受`语义走完；`验收002-问题清单.md` 14 条落档（高危=⑧ CJK 断行布局校验器与 libass 渲染能力不一致——绿灯≠渲染正确）。
- 已知限制：002 项目 107MiB 源素材超 GitHub 单文件上限不入库（与 tiger 同法 `.gitignore`，SHA 已录 G0 manifest/素材包，凭证据可重取）。

### v1.3.0 批次 · 单卡交互合同（用户 2026-09-11 定案，N8 活测产物）

- **每节点仅一次最终回显**：中途偏好类决策点（标题/角度/检索词/挑曲/风格参数）不再独立停靠提问，Agent 预选推荐项、以【默认=推荐｜依据】并入节点最终回显卡；用户否决哪条只重跑哪条。门禁口令（确认G1…确认G5）一个不减。
- **归属如实**：默认项被确认记"用户验收推荐默认项"，不得写成"用户选择"；G0 开工单五问、G3 目标主体身份判定、G5 人工验收**永不预选**。
- **默认选曲规则**：默认项=听觉模型 A/B 判"能使用"中的最高适配（N8 证据：机器分 0.881 居首者模型判 2/10——纯机器分不得当推荐）；capability_missing 时挑曲停靠点复活问用户。A/B 试听笔记从"可选"升格为"做默认选曲的必备输入"。
- **体裁标签红线**（问题⑫教训）：给未被任何耳朵听过的曲子写风格词必须标"未试听推测"；参考曲在场先跑绝对笔记、词以笔记原话为准。
- **最终回显样式指南 v1.0**（问题⑰，同日追加定案）：`p0-c-pipeline/references/final-echo-style-guide.md`——六节点门禁卡统一五段骨架（一句话结论→决策点≤两行/条→待办与事实状态→证据与产物[机器字段唯一容身处+项目绝对根路径]→操作区）+ 禁词表（机器枚举值/内部黑话/SHA 等不得上正文①–③段）；专员卡与 G3 八列硬校验不改格式、按内联原则进④区；冲突以门禁合同为准。接缝：operator-dialogue 第 1 条、p0-c-pipeline SKILL、g1-choice-cards 呈报指向。**v1.1（同日用户复审）**：决策点呈报改"问题→选项列全→【默认已选：X｜依据】"三小节，题面与选项先行、默认盖章在后。
- 落点：`p0-c-pipeline/references/operator-dialogue.md`（单卡合同节）+ 两个 SKILL；`video-edit-plan`（g1-choice-cards、g1-direction-guide、SKILL 找乐编排 2/3/4 步）；`music-expert`（SKILL 2.6/2.7、search-terms-contract）。纯合同/文档改动，脚本零改动，回归 27/27 不变。

### v1.3.0 批次 · 主线接线批次②：G1 末找乐编排 + 槽一致性后门封堵

- 堵静默改主意后门：`g1_direction.py validate` 新增 G0 `bgm` 槽一致性检查——方向简报的 `bgmDecision` 与槽冲突即拒（改主意必须先走 `pipeline_state.py bgm-choice` 留痕）；G1 只能继承槽，不能覆盖槽。
- video-edit-plan SKILL 新增"G1 末：找乐编排"节（严守节点专员=编排+卡片、音乐能力全归 music-expert 的分工）：查库先行零成本 → 检索词卡（偏好原话第一优先、不设口令）→ netease 找候选 → 锚定排序 → omni 试听笔记（可选，能力缺失如实提示）→ 候选歌卡（侵权横幅必显）→ 用户挑曲一句即决定（原话入 verdicts）→ 官方渠道整轨登记 → bgm-choice 翻槽 → **初次分析统一 G1** 补三哈希链+档案写回。停止条件与 G2/G3 硬门禁闭环。
- 测试：g1_direction +1（不一致拒、一致继承放行）。

### v1.3.0 批次 · 主线接线批次①：G0 待找乐槽（接上 music-expert 的第一步）

- 兑现 g0-policy 的"下游提醒"空头支票：G0 的 BGM 声明成为机器事实全程携带——模板新增可选 `BGM preference:`（用户口头偏好**原话**，检索词推导第一优先输入）；`material_pack.py register` 把 `bgm` 段（decision/preference/libraryPending/clearCondition）写进 material-pack.json；`pipeline_state.py init` 抬进 state.bgm；`status` 在槽未清时输出 reminder。
- 新命令 `pipeline_state.py bgm-choice`：翻槽唯一入口——翻到 `provided` 必须带登记证据（无证据拒绝），`no_bgm` 免证据；每次翻槽 append `history`，槽不得靠聊天清空。
- 硬门禁（N9 顺序）：`libraryPending` 期间 **G2/G3 approve 直接拒绝**；`validate` 检出"use_library_later 但 07 出现文件"的矛盾。
- 文档同步：pipeline-state-contract 增 BGM slot 节、p0-c-pipeline SKILL 增机器携带说明+硬门禁、g0-start-form/g0-policy 措辞兑现；测试 pipeline +2、material-pack +2（含模板提示行不算用户输入）。

### v1.3.0 批次 · music-expert 找乐（N10）+ 锚定打分

- 检索词生成合同落地（`music_search_terms.py`，专员侧 I/O 固化：时长下限由时间线毫秒向上取整，风格简报 BPM 过滤；口头偏好＞主题翻译＞简报锚定）。
- 网易云搜索适配 `music_search_netease.py`（试听选型轨道三：候选写死 `uncleared-platform-catalog`/`internal_test`，风控结构化 blocked，绝不谎称许可；下载封顶=入选数）。
- 打分许可语义定案：`uncleared-platform-catalog` 在 internal_test 画像不压分（登记由链子把关），更严边界 ×0.3 重罚（专员自测抓出的结构性零通过）。
- 回显侵权可见性：逐条 `infringementRisk` + 顶部 ⚠ 横幅 + 人读推荐回显卡 `BGM-推荐回显-v0.1.md`。
- **锚定打分**（用户试听反馈"有不适配"）：画像带 `styleBrief` 时 BPM 改亲缘度（半速/倍速折叠容差）、新增能量曲线相似度（16 桶重采样+min-max 归一），段落数让权；无简报旧行为不变。zaku 复测：10 首由全部并列 1.000 拉开为 0.896–0.738 梯度，不贴合曲目（十面埋伏/生龙）降位。
- **模型试听笔记层**（`music_listen_omni.py` + `listen-notes-contract.md`，用户定案："没有听觉分析能力不能瞎编，必须明确提示用户"）：先探测音频模型能力（CLI 存在+API key），缺失 → 结构化 `capability_missing`+回显卡明写"此处不编造"；在场 → 逐首与参照曲 A/B 听，情调差距/贴合度笔记进卡；调用失败如实进 `partialFailures`；只听短名单（`--max-tracks` 封顶）控制计费；后端可换（百炼 omni/Gemini/本地开源权重）。首跑即真实拦下一例 PATH 缺失，未编造一字。
- **音乐经验库落地**（`experience/music/` + 唯一写入口 `music_library.py`，用户定址定案）：一首歌一档案，身份=音频 SHA-256；四层次序（track.json 身份卡含 license 红绿灯/acoustic.json 高潮低谷时间戳/listen.md 模型绝对笔记带模型+提示词版本戳/verdicts.jsonl 人类裁决 append-only）；风格锚并入为 `roles: anchor`，不再单设锚库。三条红线入 README：音频本体永不进库（凭证据重取+SHA 验身）、license 只升不降（grant 是唯一翻灯通道）、相对评价不做库事实。试听笔记层新增 `--absolute --library`：同模型同提示词命中零成本复用、只有没听过的才调用、听完自动写回。首批入库 4 条（LOW=锚+绿灯；Devil Game/Gone Bad/弥渡山歌=未清权红灯），活体绝对属性听写 4/4 成功——并纠正了文本检索的假阳性：Devil Game 实为 Hardstyle 非 phonk（标题党，曲名命中≠风格命中）。
- 回归 27/27（sourcing 锚定 3 例；listen"无能力不编造"3 例+复用零成本 1 例；library 身份/红绿灯/过期不冒充 6 例）。节点侧定案记录：BGM 初次分析统一放 G1、G0 只登记（待节点批次，见交接文档 §0）。

## v1.2.0 — 2026-09-10 — music-expert 落地与 BGM 全链接线

首个走完 G0–G5 全流程闭环的真项目（zaku-intro-001）在本版诞生；BGM 专员完成从"做好"到"接上"的三段接线（N5/N6/N7），确立"领域能力归专员、节点型专员只管编排"的架构方向（总账㉜、接线方案 §6）。

### music-expert support skill（2026-09-08 建，本版发布）

- 新增独立 support skill `skill/music-expert/`（`$music-expert`）：覆盖基线总账 ⑯（已验证）与 ⑫（部分推进，找乐自动轨道待 `P0C_FREESOUND_TOKEN` 真实取证）。
- 确定性分析引擎 `music_analyze.py`：librosa 节拍/起音 + 能量分段 + ebur128 响度，产出《BGM 分析报告》（含卡点表）与风格简报；受控运行时 `P0C_MUSIC_RUNTIME_HOME`、`cacheKey` 复用、缺依赖结构化 blocked。
- 双轨找乐：`music_search_freesound.py`（仅 CC0/CC-BY、授权证据链、解码探针，缺 token 不静默换源）、`music_register_candidate.py`（人工许可登记）；`music_recommend.py` 画像打分、候选不足显式上报不硬凑；标签粗匹配（`music_tags.py`，3 维 18 标签受控词表）。选型与可达性实测固化在 `references/library-probes.md`。

### BGM 三段接线（N5/N6/N7）与 G2 蓝图（N9）

- **N5/N9**：`music_align.py` 对齐/蓝图双模式（轨偏移/高潮锚点/卡点吸附/逐句 ducking 区间）；G2 门禁 3.5 节蓝图循环（BGM 先行节拍蓝图，时间码三层身份：蓝图窗口=参考、目标码=意图、实测码=事实）；`music_echo.py` 分析回显卡固化。
- **N6（G4 混音合同链）**：`music_mix_plan.py` 出《BGM-混音合同》——三重哈希对账（BGM 文件↔计划 bgmPlan↔分析报告缓存键↔对齐产物）+ **可听窗守卫**（在位预估电平出 [人声目标−18, 目标−6] LUFS 拒绝出合同）；`g4_assemble.py` 无合同拒混 BGM、逐字执行合同、装配后**实测在位电平**与预估对账（>3 LU 或 <−33 拒绝交付）。§6-② 拍板固定衰减 dB，zaku 终值垫底 −8/压低 4。
- **N7（G5 链审计）**：`g5_audit_bgm_chain.py` 从装配记录 `bgmMix` 反向重放 G0 登记→素材包→G3 计划→对齐/报告→混音合同→装配记录，14 项检查（逐文件重算 SHA-256、参数逐字比对、可听窗算术复核、实测漂移、许可与分发边界一致性）。

### G4 实跑设防（zaku 教训，总账㉜）

- 源字幕遮蔽合同（`g4_render.py --source-mask`，比例带 + 切片内窗口 enable）；章节卡合同 `yRatio` 通道（默认居中向后兼容，修复硬编码正中违反布局合同）；旁白标准压限归一链（`--normalize-narration-lufs`，渲染后 ebur128 实测入装配记录，发现㊌）；在位电平测量防挂死（输入侧 `-t` 封顶 + 超时）。
- 纪律沉淀：遮蔽类处理表必须带实测像素/时间出处；门禁呈报必须全文内联。

### 管线与回显

- G2 回显格式定稿（四卡+自动回显+排版稿卡，标准样例 `skill/media-evidence-prep/references/examples/G2-完整回显样例-zaku.md`）。
- 批准口令脚本级归一（`确认G5`/`确定 G4` 等变体自动规范化、逐字原话留痕；带前缀整句拒收）。
- G5 交付包合同不变；`human-review-decision.json` 显式区分"确认交付"与"逐条接受警告"两种语义（本版为记录惯例，卡片拆问待后续）。

### 验收

- 全量回归 23/23（新增 test_music_align 24 例、test_music_mix_plan 10 例、test_g5_audit_bgm_chain 6 例等）；zaku-intro-001 全流程闭环（六节点全 approved，`g5_validate_delivery.py --media` valid 0 错误，BGM 链审计 14/14）作为本版活体证据入库。

## v1.1.0 — 2026-09-04

将 leader 审阅后的 P0-C v1.1.0 交付补丁合回主仓，并统一命名。补丁内容源自 TASK-050"上能同创智能剪辑 Demo"的实际渲染与人工评审。

### 命名统一

- 产品名 Video-shipcut → P0-C；编排入口 Skill `video-shipcut-pipeline` → `p0-c-pipeline`（目录与 `$` 调用名同步）。
- 环境变量前缀 `SHIPCUT_*` → `P0C_*`。
- 根文档（AGENTS、PRD、README、目录规范、历史调研）与流程图同步更名；流程图改用 SVG 作为 README 主图，旧 PNG（含旧名称，无法从 SVG 无损再生）移除，可从 git 历史找回。

### 工具链跨平台

- 运行依赖从"仅 Windows + `D:\WorkTool`"改为 macOS/Windows/Linux 通用：优先从 `PATH` 解析 FFmpeg/Python，`P0C_*` 变量为可选覆盖。
- Python 最低版本明确为 3.10（脚本使用 PEP 604 联合类型语法），推荐 3.12。
- 测试在缺少 FFmpeg 时优雅跳过（`test_engine_cli.py`）。

### G4 成片质量补丁（本次核心）

- 新增 `skill/local-video-render/references/demo-quality-patch.md`：画幅策略、clean master 不变量、封面、章节卡节奏、句子级旁白、字幕对齐实际音频、分轨与 ducking、清晰度、授权记录、机器/人工 QA。
- `render-contract.md` 增加 v1.1 扩展字段（`aspectRatioPolicy`、`cover`、`narration`、`captions`、`audio` 等），示例见 `examples/g4-render-profile.example.json`。
- `g4_render.py`：默认 `preserve_source`，用 ffprobe 从首个批准源探测画幅；`explicit` 必须同时给宽高；`--crop-bottom-ratio` 默认从 0.14 改为 0。
- `g4_validate.py`：宽高改为可选，未指定时自动检测分段画幅一致性。
- 新增 `tests/test_g4_render_profile.py`。

### 上下游合同传导

- G3（`video-edit-plan`）：含封面/章节卡/旁白/固定字幕的项目，计划必须预登记画幅策略、封面帧、句子边界、字幕样式、ducking 策略与 clean master 输入，否则保持 `review_required`。
- G5（`media-qa-delivery`）：demo-quality-patch 的机器 QA 与人工 QA 纳入交付门禁，缺任一必需证据不得报告完成。

## v0.1 — 2026-09-04

初始发布：G0–G5 六节点流水线 Skill 与示例项目 `unicorn-gundam-intro-001`。
