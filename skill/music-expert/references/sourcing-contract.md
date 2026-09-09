# BGM 找乐与登记合同（双轨来源模型）

本 Skill 覆盖总账 ⑫（无 BGM 内容/节奏分析）与"AI 自动找 BGM"的**确定性前置**。核心红线：**没有授权证据链的音乐，绝不进候选池，更不进成片**。默认分发边界一律 `internal_test`，只有人工复核许可条款后才能上调。

## 为什么是"双轨"而不是"一个自动搜索"

2026-09-08 网络调研结论（详见 `library-probes.md`）：没有任何一个公开音乐库同时满足"官方 API + 许可条款机器可读 + 可商用"。因此拆成两条互补轨道：

### 轨道一：Freesound 自动检索（唯一自动联网适配器）

`scripts/music_search_freesound.py`。有官方 API、每条声音带明确 license、可下载预览件。约束：

- 鉴权 token 从 `P0C_FREESOUND_TOKEN` 读取；缺失即 `blocked`，**不静默换源、不降级到无授权来源**。
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

## 登记产物

两条轨道产出的候选记录共享字段（`provenance` 区分 `freesound_api` / `manual_registration`），都带 `decodeProbe`、`sha256`、`retrievedAt`、`license`、`distributionBoundary`。候选不是源素材，可被下游 `music_analyze.py` 进一步分析后交 `music_recommend.py` 打分。

## 与管线的未来接缝（本版不接线）

- G0 的 `use_library_later` 槽位将来可直接调本 Skill 检索并把候选登记进 `07_授权音频`，沿用同一许可证据链。
- G3 的乐句/卡点登记引用本 Skill 的《BGM 分析报告》`hitPoints`。
- G5 授权审计消费候选的 `license`/`licenseEvidence`/`distributionBoundary`。
- 本 v0.1 **不修改六节点管线任何一行**，只把对外合同（候选 schema）定义到可直接对接的程度。
