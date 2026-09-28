---
name: loudness-expert
description: 对音视频响度做确定性测量、线性归一化规划与成片验收的领域专员：ebur128 验收口径实测（I/TP/LRA 全实测不出估计数），loudnorm pass1 规划口径对账 linear=true 前提（官方文档核实：条件不满足滤镜会静默退回动态模式——专员先算后放行，回退视同违规），产出逐字执行链与素材响度天花板数（供 G2 配音披露用）。接线按响度接线工单逐批生效（2026-09-28 批一 G2 天花板披露已接入配音试听卡与 G2 门禁；G3/G4/G5 未接线批次生效前不得引用）。不负责选曲、混音决策、渲染装配执行或交付打包——那些归各节点专员与 music-expert。
metadata:
  pipelineNode: support
---

# 响度专家（loudness-expert）

把"响度"从散在各节点的口径（g4 实链常量、g5 BGM 审计、注释里的素材天花板先例）剥成独立领域专员（用户 2026-09-28 拍板，出生证=实片台账 ⑪（09-24 记录）+ loudnorm 静默回退 dynamic 调研发现，见 `docs/响度专项-调研与方案讨论-v0.1.md`）。本 Skill 是**领域专员**（`pipelineNode: support`）：响度测量、目标档口径、可行性算术全在这里出合同；接线后节点只调用与逐字执行（与 music-expert、subtitle-expert、transition-expert 同一"底座+插件"架构）。

**用户定案节奏（09-28）**：先建成单独 skill、独立测试完毕，再考虑接入节点——"后续遇到分贝问题能把这个东西进行复用"。本册即独立建设交付物；同日测毕后用户下"接"令开接线工单（`docs/响度接线工单-v0.1.md`），按批接入、批批实跑彩排、用户点头再下一批。

## 插件纪律（可迁移四标准，照先例）

1. 接口只有 CLI 参数与 JSON 产物文件；节点零 import 本目录代码（含 `loud_core.py`，只许本专员内部 import）。
2. 依赖全靠 PATH（ffmpeg/ffprobe），禁硬编码主机/仓库路径；产物全走 `--output-dir`。
3. 合同自带接线说明书（`references/loudness-contract.md` 末节），整目录拷到新宿主照说明书重接。
4. 缺能力结构化 `capability_missing`（exit 2），**无实测即无报告**——能力可以缺、事实不能编；人不得代填数字。

## 核心口径（合同为唯一事实源）

- **单位说清**：LUFS=平均有多响（目标态）；dBTP=会不会爆（真峰值上限）；LU=动态宽度；**dB 单独出现只许表示相对增益量**（BGM 床/duck 那类），四种量纲不混称"分贝"。
- **双口径互不背书但互相对账**：规划口径=loudnorm pass1（measured_* 同源数，与执行零换算）；验收口径=ebur128（与执行链不同滤镜）。同文件两口径偏差 >0.5 LU 即引擎异常（单测锁死）。
- **防静默回退**（本专员存在的理由）：官方文档 8.97——linear=true 要求目标 LRA≥源 LRA 且线性增益后 TP 不超上限，任一不满足**滤镜悄悄退回 dynamic、不报错**。专员先算后放行：不可行→blocked+可修数值出路（提 TP/降目标/先压缩），回退执行视同违规。
- **不许半默认**（⑧ 口径直接继承）：目标必须 `--profile video|podcast` 或显式三件套全给，缺一即拒；容差 1.0 LU、TP 余量 0.3 dB 是合同工程常数并随报告如实带出，不是隐藏默认。

## 执行入口（唯一，四个 + 共享模块）

- 实测：`scripts/loud_measure.py --input <文件> --output-dir <目录> [--project-id]` → 《响度-实测报告-v0.N.json》。
- 规划：`scripts/loud_plan.py --input <源> --output-dir <目录> (--profile video|podcast | --target-lufs+--true-peak+--lra-target) [--project-id]` → 《响度-归一化计划-v0.N.json》：ready 含逐字 chain；blocked 含 reasons+exits；**ceilingLufs（现 TP 上限下最响可到几）永远给出——G2 配音天花板披露的数据源**。blocked 落盘摊开并 exit 1（卡住≠失败静默）。
- 验收：`scripts/loud_verify.py --plan <计划> --master <成片> --output-dir <目录> [--tolerance-lu]` → 《响度-验收审计-v0.N.json》：独立 ebur128 复测对账目标±容差与 TP 上限；plan 身份不符/非 ready/文件缺失一律拒。
- 回显卡：`scripts/loud_echo.py --artifact <产物>` → 固定表格 Markdown 卡（呈现层零算术，数据逐字取自产物；非本专员产物拒渲染——防手制卡，⑤ 先例）。
- 共享模块（只许 import）：`scripts/loud_core.py`（测量封装、可行性纯函数、版本命名 ㉘ 永不覆盖、产物身份头）。
- 不要用临时脚本或手敲 ffmpeg 替代。

## 边界（不做什么）

1. 不做混音决策：bed/duck 深度、选曲、BGM 对齐全归 music-expert 与 G3 批准合同；本专员只答"响不响、会不会爆、可修数值是什么"。
2. 不执行成片装配：chain 由规划产物给出，执行属节点专员（接线后 G4 逐字使用）；`render_with_chain` 只供专员自测。
3. 不碰内容层：口播文本、字幕、画面选择均不相干。
4. 接线状态（按 `docs/响度接线工单-v0.1.md` 逐批生效）：**批一 G2 已接线（2026-09-28）**——配音天花板披露并入试听卡，G2 决定 schema 0.2 必带 `loudnessPlanRef`；批二 G3／批三 G4／批四 G5 **未接线**，在各自批次兑现前任何节点门禁不得引用本专员产物做批准依据（合同 §8 为唯一蓝本）。

## 测试

`tests/`：core（解析/可行性算术/版本命名 12 例）／measure（端到端实测+物理阶梯 6.02 LU 锁+双引擎互证+缺席摊牌 6 例）／plan（目标显式化拒绝+规划自洽 9 例）／verify（ready→真跑 chain→独立复测 passed 闭环+拒绝面 6 例）／echo（卡出处与零算术 3 例）。**逐文件单跑**（全仓口径），ffmpeg 缺席时端到端层显式 skip（skip 不算绿）。

## 已知限制（如实）

- 目标档只收录查证过的 video（−14/TP−1.5/LRA9，现行 g4 实链验证值）与 podcast（−16/TP−2/LRA7，ffmpeg-normalize 预设调研值）；广播档 −23 与我们无关未收。平台新档随接线工单定。
- lavfi `sine` 源在本机构建默认峰值 ≈−18 dBFS（自证轮发现）——专员绝对值全部来自实测，不受源假设牵连；新宿主迁移后跑物理阶梯锁即可验表。
- 全片主轨验收含 BGM 合成效果（口径注记随报告带出），"纯口播响度"需在配音源文件上单独 measure。
