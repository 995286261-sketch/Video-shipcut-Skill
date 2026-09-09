# 交付包 v0.1 — 刹帝利（NZ-666）机体科普 · kshatriya-intro-002

- 定位：B站风格机体科普短片（103.3s），与 kshatriya-intro-001（155.4s）为同题长/短双版本。
- 边界：authorization=internal_test，distribution=not_for_distribution。**不得对外分发。**
- 文件关系：final-video.mp4（成片，烧录字幕）；clips/ch-01..05（章节切片）；subtitles.srt（字幕参考）；cover.jpg（封面）；edit-timeline.md（G3 批准逐行时间轴）；source-timecode-list.json（段级源追溯）；edit-plan.json（操作摘要+警告）；export-config.json（导出规格）；metadata-validation-report.json（机器 QA）；delivery-manifest.json（唯一合同入口）；human-review-decision.json（人工审核状态）；failure-samples/README.md（真实故障记录）。
- 复现：切片/装配均出自 `skill/local-video-render/scripts`（g4_prepare→g4_render→g4_assemble，装配记录含逐段哈希与滤镜图）；旁白为 CosyVoice longtian_v3 逐句合成后按 G2 实测时码拼接。
- 已知偏差（用户已于 G4 接受）：无章节卡/标题栏；旁白 −15.2 LUFS（目标 −14）；与 001 画面同源 96%。
- 生成时间：2026-09-09T02:05:31Z
