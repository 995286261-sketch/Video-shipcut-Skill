# 字幕经验库（experience/subtitles）

跨项目的"我们验证过的字幕呈现事实"档案，照音乐经验库同一纪律建设（用户 2026-09-21 提议"像 music 一样"）。**唯一写入口是 `skill/subtitle-expert/scripts/subtitle_experience.py`**——Agent 不手改 JSON；库根用 `--library` 或 `SUBTITLE_EXPERIENCE_HOME` 声明，不硬编码。

## 三类档案

| 目录 | 回答的问题 | 入库门槛 |
|---|---|---|
| `fonts/` | 这个字体文件（身份=文件 SHA-256）在 drawtext / libass 两条路线上能不能用？ | usable/rejected 判定必须带证据（㉛ 预检结论、目视实据）；记录只增不删 |
| `layouts/` | 这个分辨率族下，被门禁批准过的排版参数是什么（字号/行数/安全带/边距/autoWrap 档）？ | 必须附 G3 布局合同 + 门禁批准文件路径——没被批准过的排版不入库 |
| `renderer/` | 这台宿主的渲染器实测能力档（libass 有无、autoWrap 判定与证据）？ | 只存 `subtitle_probe_renderer.py` 探测报告派生的事实；autoWrap=true 无证据拒收 |

## 三条红线

1. **库=建议层，不是批准。** `query` 输出自带免责声明：G3 每次必须重新出布局合同、重新过 `subtitle_validate_layout.py`、重新过用户门禁。库档案只能作为回显卡上的【默认=推荐】项出现，依据栏写"经验库+来源项目"。字体/排版参数跨项目**不自动沿用**（G0 追问项每次重问的同一教训）。
2. **呈现层事实才入库。** cue 的时刻、断句位置、字幕文本=每个项目的语义/内容判断（G2 批准稿+G3 时间轴），**永不入库**——写入口按白名单只抽 `lanes.narration` 的排版参数，字段层面就进不去。"什么时候显示"复用旧成果与"每项目重批"纪律冲突，用户侧已按此口径定案。
3. **未验证的不写。** 没跑过的字体、没过门的合同、没有证据的能力声明，一律拒。宁缺毋滥，库里每个字都要能回指实据。

## 复用（读侧）

- **G3 写布局合同前**：`subtitle_experience.py query --kind layout --resolution <WxH>` 与 `query --kind font`，命中即在回显卡推荐默认里引用；未命中按 style-contract 画幅默认起步。
- **G4 选字体路线前**：`query --kind font` 查该字体的 drawtext 首-face 陷阱（㉛）与 libass 实测史，少走一遍弯路。
- **换宿主**：`query --kind renderer` 为空是正常起点——重跑探测再 `record-renderer`，旧宿主的档案不迁移复用（能力档跟着机器走）。

首批档案=2026-09-21 从六个已交付项目的 G3 产物与 ㉛/⑧ 实测记录回填（脚本实录，非手填）。
