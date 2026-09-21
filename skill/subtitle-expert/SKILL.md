---
name: subtitle-expert
description: 对字幕做确定性排版与校验的领域专员：探测宿主渲染器能力档（libass 版本、autoWrap 证据化判定），产出/机器校验 G3 字幕布局合同与 ASS/SRT 时间轴（CJK 显式语义断行、两行均衡、宽度模型、SRT 同源派生与格式校验），固化烧录排版策略（固定字幕条），并向 G5 提供字幕面 QA 判读纪律。作为字幕专员已接入 G3（布局合同与时间轴校验）、G4（烧录执行 style-contract）、G5（字幕 QA qa-contract）；G2 只供文本权威源、专员不碰内容层。不负责口播写作、剪辑决策、渲染装配、QA 打包或交付。
metadata:
  pipelineNode: support
---

# 字幕专家（subtitle-expert）

把字幕从"各节点各管一段、接缝处出事"剥成独立领域专员（用户 2026-09-21 拍板；出生证=002 问题⑧「校验器绿灯≠渲染正确」+ ㉖㊍⑩㉛ 事故链）。本 Skill 是**领域专员**（`pipelineNode: support`）：排版规则与校验全在这里出合同，节点型专员只调用与逐字执行（与 music-expert 同一"底座+插件"架构，用户 2026-09-21 定案）。

## 插件纪律（可迁移四标准，照 music-expert 定案）

1. 接口只有 CLI 参数与 JSON/ASS/SRT 产物文件，节点零 import 本目录代码；
2. 依赖全靠环境变量与 PATH（ffmpeg/ffprobe），**禁硬编码主机/仓库路径**；输出全走 `--output-dir` 显式参数；
3. 合同自带接线说明书（`references/layout-contract.md` 末节），整个目录拷到新宿主后照说明书重接；
4. 缺能力结构化 blocked/保守降级，**绝不编造渲染器行为**——autoWrap=true 必须有实测证据（能力可以缺、事实不能编）。

## 执行入口（唯一）

- 渲染器能力探测：`scripts/subtitle_probe_renderer.py --output-dir <目录> [--font <字体>] [--auto-wrap true --auto-wrap-evidence <证据>]` → 《字幕-渲染器能力档-v0.1.json》。默认保守档 autoWrap=false；升 true 必须带证据。
- 布局校验：`scripts/subtitle_validate_layout.py --ass <时间轴> --layout <布局合同> [--srt <交付副本>]`。合同形状、能力档语义、生成规则全部见 `references/layout-contract.md`（唯一事实源）。
- 烧录排版策略：`references/style-contract.md`（固定字幕条；G4 逐字执行）。
- 字幕面 QA 判读：`references/qa-contract.md`（G5 消费）。
- 不要用临时脚本或手敲 ffmpeg 替代。

## 边界（不做什么）

- **不碰口播稿内容权威层**：字幕文本= G2 批准的口播原文，专员只管呈现层（断行、排版、格式）——与 BGM 同一纪律。
- 不做语音识别（转写归 G2）、不做花字/动效模板库（无事故证的想象需求）、不做翻译。
- 字体字形覆盖预检（㉛）留在 G4 drawtext 路线；libass 烧录路线的字体问题按 G5 目视+能力档纠偏处理。

## 接线现状

G3：布局合同+ASS/SRT 生成过检（video-edit-plan 调用，收据项 `subtitle_timeline`）；G4：`g4_assemble.py --subtitle-ass` 逐字执行 + style-contract；G5：qa-contract 判读纪律 + 检查帧收据 `check_frames`。G2 为文本上游、不接线（只读权威源）。改接缝先改 `layout-contract.md`。
