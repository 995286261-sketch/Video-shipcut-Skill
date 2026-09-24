# 交付包 v0.3（第 3 轮修订版 · 转场实跑测试）

- 项目：unicorn-gundam-transition-001（unicorn-gundam-intro-001 克隆，转场链路实跑）
- 状态：**待人工 G5 裁决**（本 README 随批准封包后不改写）
- 成片：final-video.mp4 ｜ 0:38.832 ｜ 30fps（第 3 轮修复：⑧ 曾以 24fps 交付被拦）｜ h264 1920x1080 ｜ sha256 99CBF062…04CE6
- 音频：口播 + BGM bed −12dB/duck −6dB（源英文音轨排除）；响度 −16.1 LUFS（目标 −14，记警告）
- 字幕：subtitles.srt 7 cue（第 2 轮修复 ⑦ 重叠缺陷）+ 成片烧录；源内嵌字幕两段遮蔽、水印保留披露
- 章节：clips/ 4 条（登场与装甲/毁灭模式标志/代价与驾驶员/收束）
- 封面：cover.jpg（源 218.500s 静帧）
- 握手：subtitle-srt-check.json passed ｜ transition-audit.json passed（4 转场逐参数+母带哈希）｜ bgm-chain-audit.json **1 failed/15 passed**（⑩ 修订轮合同 planFileHash 锁失效，见 failure-samples/README.md）
- 分发边界：**internal_test** —— 第三方 IP 二创素材，仅内部预览，不得对外发布
- 追溯：source-timecode-list.json（8 段↔源时间码+3 轮修订记录）；审批链见 pipeline-state + G3/G4/G5 批准记录
- 质检：metadata-validation-report.json（含全部警告）；failure-samples/ 记录本轮真实抓到的缺陷 ⑦⑧⑨⑩
