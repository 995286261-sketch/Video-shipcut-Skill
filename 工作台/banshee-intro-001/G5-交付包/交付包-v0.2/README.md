# banshee-intro-001 交付包 v0.2

报丧女妖（RX-0(N) 命运女神）介绍片 ｜ B站横版制式 1280x720 · 24fps · 124.000s ｜ 去向=**internal_test（内部留存，禁止分发）** ｜ 2026-10-10

本版为混音回炉重做版（v0.1 首验响度 failed，床/duck 参数修正后重走 G4/G5；画面层与批准计划零改动，见问题清单 ⑥）。

## 内容

| 文件 | 说明 |
|---|---|
| final-video.mp4 | 成片（=批准候选 G4-候选成片-v0.2.mp4，sha AA3FE45A…99B1EBD） |
| cover.jpg | 封面（登记件 1170373ms 机抽+标题） |
| subtitles.srt | 英文字幕文件（与烧录同源） |
| clips/ch-01…ch-05.mp4 | 五章节切片（0:00/0:25.968/0:48.593/1:22.168/1:48.207–2:04） |
| source-timecode-list.json | 成片↔源片时间码对照（源=用户提供的 B站混剪素材，只读） |
| edit-plan.json / edit-timeline.md | 批准的 G3 剪辑计划与逐行时间线 |
| export-config.json | 导出制式与响度目标 |
| subtitle-srt-check.json | 字幕专员 SRT 复检（passed） |
| transition-audit.json | 转场审计（passed，网格不变量成立） |
| loudness-audit.json | 响度验收（**passed**：主轨 −14.9 LUFS 偏差 −0.9 ∈ ±1.0；真峰 −1.7 ≤ 上限 −1.5） |
| bgm-chain-audit.json | BGM 全链审计 14/14 passed（哈希链+执行保真+在位实测对账+许可链） |
| metadata-validation-report.json | 机器质检报告（完整解码/黑帧/静音/重复/制式对账） |
| delivery-manifest.json | 交付清单（逐文件指纹） |
| human-review-decision.json | 人工验收决定（本项目=自动确认模式，见下） |
| failure-samples/ | 无失败样片；过程性失败如实指路 |

## 固定披露段（自动确认模式）

- **人工听感/观看验收未执行**，由 auto-policy 策略批准替代（approvalSource=auto-policy；机器校验全过+每节点回显卡照出；绝不伪造人类原话）。用户可随时打断回炉。
- 警告逐条：
  1. **BGM《LOW-PHONK》未清权**：委托选定+4/10 贴合度披露在前；仅限内部留存，**对外发布必须先换曲并重走 G4/G5**，否则违反权益。
  2. **源素材为他人 B站混剪**（个人学习/内部留存边界）：画面内水印/台标/烧录字幕残留按边界保留（底部字幕带 84–100% 遮罩仅覆盖烧录字幕区）。
  3. **配音=预览级系统声（macOS Samantha）**沿用成品（preview_voice_production 预授权，逐字批准含"预览级"披露）。
- 响度：目标 −14.0 LUFS / −1.5 dBTP（B站横版），实测 −14.9 / −1.7，验收 passed；首过 failed 回炉记录在案不掩。
