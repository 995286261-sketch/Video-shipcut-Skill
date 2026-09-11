# tiger-intro-001 交付包 v0.1

《王牌老虎：08小队战场上最不愿遇到的对手》——MS-07B3 老虎改 机体介绍片，B站公开。

## 文件关系

- `final-video.mp4`：最终成片（1920×1080/24fps/120.1s，G4 本地渲染，确认G4 验收）。
- `cover.jpg`：B站封面（seg-001 机库正面裁除水印重制 + libass 标题）。
- `subtitles.srt`：19 cue 中文口播字幕（时间来自实际配音音频）。
- `edit-plan.json` / `edit-timeline.md`：批准的 G3 计划与其逐行交付展开。
- `source-timecode-list.json`：章节→内部段→源时间码追溯（源 sha 17B6A344…）。
- `export-config.json`：平台/规格/授权设置。
- `metadata-validation-report.json`：机器 QA（黑帧/静音/解码/哈希）。
- `delivery-manifest.json`：G5 唯一机器合同入口。
- `human-review-decision.json`：人工验收决定（当前 pending）。
- `BGM链路审计-v0.1.json`：音乐哈希链 12 项全过。
- `clips/`：4 个章节级审看片段。`检查帧-字幕.jpg`：字幕安全区证据帧。

## 复现

`g4_prepare → g4_render(mask合同) → g4_assemble(配音轨+BGM混音合同+ASS)`，全部合同在项目内带哈希。

## 授权与分发边界（重要）

- **BGM《Infinity（鲫虞豆腐汤remix）》为网易云试听件，用户 2026-09-11 声明自担版权风险**；仅限非商用二创分发，若需商用必须换已清授权轨并重走 G4。
- 画面源为 B站二创混剪（UP主「嘟嘟踢被子」），左上水印按 G3 批准保留；成片分发限于同规范二创生态，不得商用。
- 字体 PingFang SC 为系统字体烧录，商用场景需自查许可。
- 配音 cosyvoice-v3.5-plus-flash 用户确认音色（G2）。
