# mickey-intro-001 交付包 v0.1

米老鼠介绍宣传片（从蒸汽船到树屋）｜ B站横版制式 1280x720 · 30fps · 66.000s ｜ 去向=**internal_test（内部留存，禁止分发）** ｜ 2026-11-19

本包为本地验收操作单 v0.2 真机测试首版成片；测试口径=**先收集问题不修复**（问题清单 ⑩–㉗ 全程登记，成片本体无带病出厂）。

## 内容

| 文件 | 说明 |
|---|---|
| final-video.mp4 | 成片（=批准候选 G4-候选成片-v0.1.mp4，sha 3707AE91…C0AC49） |
| cover.jpg | 封面（A 素材 264000ms 帧机抽+标题「从蒸汽船到树屋：米老鼠快讲」） |
| subtitles.srt | 英文字幕 12 cue（与烧录同源） |
| clips/ch-01…ch-04.mp4 | 四章节切片（0:00 / 0:30.500 / 0:48.449 / 0:55.859–1:06） |
| source-timecode-list.json | 成片↔源片时间码对照（g5_build_traceability 机械投影，台账⑪甲案） |
| edit-plan.json / edit-timeline.md | 批准的 G3 剪辑计划 v0.7（含 ⑮ 补登字段）与逐行时间线 |
| export-config.json | 导出制式与响度目标（分辨率文本不符 ㉖ 在此如实标注） |
| subtitle-srt-check.json | 字幕专员 SRT 复检（passed） |
| transition-audit.json | 转场审计（passed；全片硬切+黑场入出 masterFades） |
| loudness-audit.json | 响度验收（**passed**：主轨 −17.8 LUFS 偏差 −0.1 ∈ ±1.0；真峰 −4.0 ≤ 上限 −1.5；目标 −17.7=放置轨物理下限 ㉔） |
| bgm-chain-audit.json | BGM 全链审计 passed（哈希链+执行保真+在位实测+许可链） |
| attribution-credits.md | **CC-BY 署名义务清单（机器派生，缺口① 真机首跑实弹）**——发布文案必须从此抄 |
| metadata-validation-report.json | 机器质检报告（完整解码/黑帧/静音/重复/制式对账） |
| delivery-manifest.json | 交付清单（逐文件指纹） |
| human-review-decision.json | 人工验收决定（本项目=自动确认模式，见下） |
| failure-samples/ | 无失败样片；过程性失败如实指路 |

## 固定披露段（自动确认模式）

- **人工听感/观看验收未执行**，由 auto-policy 策略批准替代（approvalSource=auto-policy；机器校验全过+每节点回显卡照出；绝不伪造人类原话）。用户可随时打断回炉。
- 警告逐条：
  1. **BGM《Catchy-Synthwave》(Freesound 686768) license=cc-by 未走完清权登记**：仅限内部留存；对外发布必须按 `attribution-credits.md` 逐字署名并复核许可边界，否则违反权益。署名义务机器闭环（v1.35.4）已在本包兑现。
  2. **源素材=他人修复/补帧版**（《汽船威利》4K60 超分补帧版 + 《米奇妙妙屋》原版无水印修复版；个人学习/内部留存边界）：增强瑕疵随 G0 警告披露；B 段源烧录中文字幕以底部 86–99% 遮罩 black@0.85 **压淡**处理，淡影仍可辨（问题 ㉗ 如实披露，非全遮）。
  3. **配音=预览级系统声（macOS Samantha）**（preview_voice_production 预授权，逐字批准含「预览级」披露词）。
- 其他如实披露：G3 计划政策文本写 1920x1080、成片实际 1280x720@30（与全部已批段文件内部自洽；无机器对账=问题 ㉖ 已登记）；响度目标经两次 reopen-g3 定格 −17.7（㉔ 装配三口径罢工→物理下限重批，全程留痕）。
