# sinjuku-intro-001 交付包 v0.1（internal_test）

新安洲介绍（B站画幅 1280×720@30，2 分 50 秒）。本包为 P0-C G5 唯一 canonical 交付与审计闭环。

## 文件关系

- `final-video.mp4` — 成片（= G4 候选 v0.3，sha256 7C123A2D95592814…，170.200s 实测 / 网格 170.167s）
- `cover.jpg` — 封面（源 432.5s 红机+大型光束步枪+金袖章帧+标题）
- `clips/chapter-01..04.mp4` — 章节级预览（再临 / 规格与速度之名 / 带袖的与「夏亚再世」/ 最终决战与答案）
- `subtitles.srt` + `subtitle-srt-check.json` — 交付字幕与 subtitle-expert 握手报告（passed）
- `transition-audit.json` — transition-expert 装配后复检（3 边界 fade，filterGraph==指令，gridInvariant，passed）
- `bgm-chain-audit.json` — BGM 许可与哈希链审计（passed）
- `source-timecode-list.json` — 章节→段→源资产/源时间码映射（源 sha 9BAEC009…，只读）
- `edit-plan.json` / `edit-timeline.md` — 批准计划 v0.6 摘要与逐行时间线
- `export-config.json` / `metadata-validation-report.json` / `delivery-manifest.json` — 机器合同与校验入口

## 复现路径

G3 批准件 `G3-剪辑计划-v0.6.json`（sha 20856864CB97BC2D…）→ `transition_directive.py`（指令 v0.2）→ `g4_prepare` → 既有 clean segments（27 段，未重渲）→ `g4_assemble`（xfade fade×3 + 配音/BGM/字幕/包装链）→ `g4_validate` 27/27。全部工作件在 `工作台/sinjuku-intro-001/G4-剪辑与渲染/`。

## 授权与分发边界

- 画面：用户提供的第三方 AMV《红色彗星的再临》（日升 IP 二创，左上水印 UP 主"shin超次元响子 bilibili"保留）——**仅限内部测试，不得对外分发**。
- BGM：LOW(PHONK)（Freesound 来源，cleared-for-project）；源片英文歌音轨已全程排除。
- 口播：AI 配音（cosyvoice-v3-flash · longtian_v3），用户指定。

## 已知如实记录（非缺陷）

成片综合响度 -15.4 LUFS（目标 -14，偏差 1.4 LU）；时长目标 180s→实际网格 170.167s（G2 缩 timeline 决策，⑫ 在案）。验收003 问题清单 ①–㉘ 见 `../../验收003-问题清单.md`。
