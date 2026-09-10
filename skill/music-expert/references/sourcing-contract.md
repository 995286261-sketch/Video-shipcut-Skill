# BGM 找乐与登记合同（三轨来源模型）

本 Skill 覆盖总账 ⑫（无 BGM 内容/节奏分析）与"AI 自动找 BGM"的**确定性前置**。核心红线：**未经真实许可登记的音乐，绝不进剪辑计划与成片**。默认分发边界一律 `internal_test`，只有人工复核许可条款后才能上调。

## 为什么是"三轨"而不是"一个自动搜索"

2026-09-08 网络调研结论（详见 `library-probes.md`）：没有任何一个公开音乐库同时满足"官方 API + 许可条款机器可读 + 可商用"。因此拆成互补轨道；2026-09-10 按用户决策（内地内测优先全曲库、审核者要听过歌）增补网易云**试听选型**轨道：

### 轨道一：Freesound 自动检索（自动轨道中唯一可带真实许可的来源）

`scripts/music_search_freesound.py`。有官方 API、每条声音带明确 license、可下载预览件。约束：

- 鉴权 token 从 `MUSIC_EXPERT_FREESOUND_TOKEN` 读取（历史别名 `P0C_FREESOUND_TOKEN`）；缺失即 `blocked`，**不静默换源、不降级到无授权来源**。
- 许可过滤：仅接受 `Creative Commons 0` 与 `Attribution`；凡名字含 `NC / NonCommercial / ND / NoDerivatives / Sampling` 一律排除并记入 `excluded`（附原因）。
- 每条候选保留完整证据链：`sourceUrl`、`license`、`licenseType`、`attributionRequired`、`attributionText`、`author`、`retrievedAt`、下载预览件 `sha256`/`byteSize`、`decodeProbe`。
- 下载预览件后立即 `ffmpeg` 解码探针；未通过即丢弃（假文件/加密文件不进池）。
- 默认下载只取预览 mp3；`--no-download` 只做检索过滤不落地。
- 候选不足（`sufficiency.count < minimumExpected`）在清单里显式标注，不硬凑。

### 轨道二：人工候选登记

`scripts/music_register_candidate.py`。覆盖 **Pixabay / Mixkit 音乐**等"无可用 API、许可页动态渲染、无法机器审计"的曲库：由**人**在浏览器里合法下载音频并抄录许可证据，再交给脚本登记。

- 必填 `--license-type`（`cc0|cc-by|cc-by-sa|public-domain|owned|cleared-for-project|unknown`）与 `--license-evidence`（许可页 URL 或项目内截图/文本文件路径）；非 `unknown` 却没给证据即 `invalid`。
- 脚本**不联网、不下载、不复制**源文件；只做 SHA-256、字节数、解码探针、生成登记清单。
- 默认 `distributionBoundary: internal_test`。

### 轨道三：网易云搜索（试听选型发现器，**不是授权来源**）

`scripts/music_search_netease.py`。解决"公开免版权库里挑不出审核者听过的歌"：中文全曲库检索，返回歌名/歌手/专辑/时长/来源 URL，可下载试听件（同样 SHA-256 + 解码探针）。取证与限制详见 `library-probes.md` 2026-09-10 节。

- **每条候选写死** `license: uncleared-platform-catalog`、`distributionBoundary: internal_test` 与 `licenseNote`：平台曲库授权仅覆盖端内播放，不存在"用了 API 就等于有版权"。
- **候选只能用于试听选型**：选中的歌要进剪辑计划，必须由人经官方渠道取得整轨文件，走轨道二登记真实许可证据（内测项目按 zaku 先例登记 `cleared-for-project` + 用户明示内部使用）。**试听件直接进成片 = 红线违规**，G0 三哈希链与 G5 审计会拒收。
- 风控响应（-462/verifyType）与网络失败一律结构化 `blocked`，不静默换源、不重试轰炸。
- 商用迁移路径：换带商用许可的来源适配器（Epidemic/Artlist/曲多多等）或 AI 生成音乐；候选 schema 与下游链路不变，换源只换这一个脚本。

## 登记产物

各轨道产出的候选记录共享字段（`provenance` 区分 `freesound_api` / `manual_registration` / `netease_search`），都带 `decodeProbe`、`retrievedAt`、`license`、`distributionBoundary`。候选不是源素材，可被下游 `music_analyze.py` 进一步分析后交 `music_recommend.py` 打分；`netease_search` 候选参与打分时许可维度按未清权压低分并常驻 internal_test 标注。

候选另带语义层 `styleTags`：人工登记用 `--tags` 且必须命中 `tag-vocabulary.md` 受控词表，外部来源的原始 tags 走别名 best-effort 归一。标签不进分析报告——声学层与语义层严格分离。

## 与管线的接缝（2026-09-10 现状）

- **G0**：`07_授权音频` 每段音频强制登记记录 + 三哈希链（音频←登记←分析报告），validate 检出登记后篡改（N1，已接线）。候选池（含 `netease_search` 试听件）本身不是源素材，进 `02_原始素材`/`07_授权音频` 必须走轨道二真实登记。
- **G1**：参考视频音轨分析产出风格简报（N3，已接线）。**G2**：节拍蓝图创作循环（N9）。**G3**：`music_align` 对齐产物入计划 bgmPlan 哈希链（N5）。**G4**：`music_mix_plan` 合同 + `g4_assemble` 逐字执行（N6）。**G5**：`g5_audit_bgm_chain` 消费装配记录 bgmMix 全链对账（N7）。
- 尚未接线的一段：**G0 `use_library_later` 自动调检索器**（素材包无音频时主动进候选池），属 N10 收尾批次。
