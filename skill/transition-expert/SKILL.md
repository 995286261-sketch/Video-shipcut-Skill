---
name: transition-expert
description: 对视频转场做确定性探测、模型校验与执行指令推导的领域专员：探测宿主 ffmpeg xfade 能力档（转场名单实测解析，无探测不声称），深检 G3 计划的转场决定（受控词表、口播停顿窗口、手柄回填余量、缺料摊牌报最大可行时长、成片网格不变），并向 G4 提供确定性执行指令与装配复检。核心模型=音不动画面服从、手柄回填、G4 永不静默降级。不负责剪辑决策、口播/字幕内容、BGM 对齐或交付打包——那些归各节点专员。
metadata:
  pipelineNode: support
---

# 转场专家（transition-expert）

把"转场"从 G3 卡上的挂空列（有卡无计划、有计划无执行——002 实际批准过"叠化/硬切按 G4 微调"）剥成独立领域专员（用户 2026-09-21 拍板；出生证=缺陷梳理 §一-8，方案经 plan 模式批准）。本 Skill 是**领域专员**（`pipelineNode: support`）：转场模型与校验全在这里出合同，节点专员只调用与逐字执行（与 music-expert、subtitle-expert 同一"底座+插件"架构）。

## 插件纪律（可迁移四标准）

1. 接口只有 CLI 参数与产物文件；节点零代码 import 本专员。
2. 依赖全靠环境变量与 PATH（ffmpeg/ffprobe；库根如需再议走 `TRANSITION_EXPERT_*` 通用名），禁硬编码机器路径；产物一律 `--output-dir`。
3. 合同自带接线说明书（`references/transition-contract.md` 末节），拷到新宿主照说明书重接。
4. 缺能力结构化 blocked / 保守降级，绝不编造：无能力档则叠化一律不声称可用（能力可以缺、事实不能编）。

## 核心模型（三条宪法）

**网格不变性**（口播时间轴为权威，转场零平移）、**手柄回填**（叠化吃切点两侧源余量 D/2，成片总长不变）、**缺料摊牌**（余量不足报确切缺口与最大可行时长，用户逐切点定夺；G4 永不静默降级）。全文以 `references/transition-contract.md` 为唯一事实源。

## 执行入口（唯一）

- 探测：`scripts/transition_probe_host.py --output-dir <目录>` → 《转场-宿主能力档-v<M.N>.json》（xfade 可用性+转场名单实测解析；未知如实 unknown；版本自动递增、永不覆盖旧档，issue ㉘）。
- 计划深检：`scripts/transition_validate_plan.py --plan <G3计划> --evidence <证据JSON> [--host-profile <能力档>]`（词表/位次/窗口压口播/章节卡交叠/手柄余量/偶数时长/网格连续，批量报错）。
- 执行指令（批准后、g4_prepare 前运行）：`scripts/transition_directive.py --plan <已批计划> --evidence <证据JSON> --host-profile <能力档> --output-dir <G4目录>` → 《G4-转场执行指令-v<M.N>.json》（确定性推导：段头尾扩切毫秒、边界 xfade offset、片头片尾黑场；非法计划直接 blocked——**先过深检才有指令**；版本自动递增、永不覆盖——reopen 重跑时旧指令留盘作审计，issue ㉘）。prepare 以 `--transition-directive` 消费；计划含转场而不传指令=G4 拒办。
- 装配复检（G5 握手产物生产者）：`scripts/transition_report.py --manifest <可编辑工程> --assembly-record <装配记录> --directive <指令> --output-dir <目录>` → `transition-audit.json`（filterGraph 逐项对账边界/fade；无转场项目也出报告，transitions=[]）。
- 试装预览（G3 批准前观感层，用户 09-23 批准）：`scripts/transition_preview.py --plan <计划> --evidence <证据JSON> --host-profile <能力档> --material-pack <G0/material-pack.json> --output-dir <G3-剪辑计划/预览小样/> --fps <帧率>` → 《转场-预览清单-v<M.N>.json》+逐边界低清无声小样（复用深检与指令算术，公式与成片路径同式；硬门禁与豁免披露口径见合同"试装预览"节）。

不要用临时脚本或手敲 ffmpeg 替代。

## 边界（不做什么）

不决定哪里该用转场——**分工三层（推荐层转正，用户 09-23 拍板）**：编排（g3-edit-plan 节点侧）必须基于逐切点素材观察主动出转场设计提案并带【默认=推荐｜理由】（㉑+⑮ 新规）；**专员脚本（校验/directive/预览）不做机器侧评分推荐、不代选**；最终决定权在用户逐切点批准。专员的"提示义务"止于可行性事实（缺多少毫秒、最大可行 D、黑场前提是否满足），到"建议用哪种"为止——再往前的编辑判断归编排与人的。不渲染成片、不装配（执行参数归 G4，专员只产指令文件与校验；批准前低清试装小样是例外——观感层证据，不产出任何可执行参数，见合同"试装预览"节）；不碰口播/字幕/音乐内容层；不建经验库（第一批无验证历史可沉淀，冻结律）。

## 接线现状

G3：probe → `transition_validate_plan.py` 深检 → 产物入最终回显与门禁收据；节点侧词表校验在 video-edit-plan（`plan-contract.md` 转场节）。G4/G5：批②③建设中，接线表见 `references/transition-contract.md` 末节。改任一接缝先改合同。
