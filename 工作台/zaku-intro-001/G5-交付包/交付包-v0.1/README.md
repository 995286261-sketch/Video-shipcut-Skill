# 交付包 v0.1 — zaku-intro-001（internal_test）

为什么一台量产机，能成为高达系列的灵魂？——113.310s 混剪科普成片。

## 文件关系
- `final-video.mp4`：**交付主件**（G4 批准候选 v0.6 逐字节复制，SHA-256 见 `metadata-validation-report.json`）。
- `cover.jpg`：平台封面图（不入正片）；`subtitles.srt`：15 条口播字幕参考（成片为烧录 ASS）。
- `clips/chapter-01..03.mp4`：章节级审阅条（CRF18 重编码，非交付主件），映射见 `source-timecode-list.json`。
- `edit-timeline.md`：逐行剪辑时间线（合同入口件）；`edit-plan.json`/`export-config.json`：机器摘要。
- `bgm-chain-audit.json`：BGM 授权与哈希链审计（14 项全绿），链：G0 登记→素材包→G3 计划→对齐/分析报告→混音合同→装配记录。
- `metadata-validation-report.json`：机器 QA 明细；`delivery-manifest.json`：G5 合同唯一入口。

## 复现
G0–G4 全部经门禁批准（见 pipeline-state.json）。BGM 混音由 music-expert 合同驱动，
`skill/media-qa-delivery/scripts/g5_audit_bgm_chain.py` 可从装配记录起重放全链对账；任何一环哈希不符即审计失败。

## 授权与分发边界
- **internal_test，不可对外分发。** 画面为第三方混剪（日升 IP 二创），用户 2026-09-09 明示仅内部测试；左上 bilibili 水印保留。
- BGM LOW(PHONK)：cleared-for-project（对外未清权）；源英文歌音轨已全片排除。
- 母带实测 −15.1 LUFS（目标 −14；TTS 高峰值因子上限，复核项）；重复画面无机器检测器（人工播放覆盖）。

## 状态
`g5_pending_human_review` —— 等待用户全片播放并回复 `确认 G5`。
