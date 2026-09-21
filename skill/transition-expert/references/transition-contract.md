# 转场合同（transition-contract）——唯一事实源

出生证：002 挂空合同缺陷（缺陷梳理-v0.1 §一-8）——G3 八列卡"转场指令"列有卡无计划、有计划无执行，用户批准过"叠化/硬切按 G4 微调"含糊句。方案经用户批准（2026-09-21，plan 模式定稿）。

## 模型（三条宪法，用户拍板）

1. **网格不变性**：成片输出网格以口播时间轴为权威。转场**不改变任何**成片坐标——字幕 cue、口播音频、BGM 卡点/ducking、章节卡、封面帧全部零平移。任何让坐标平移的方案不进本管线。
2. **手柄回填**：`叠化` 居中吃切点两侧各 D/2 的**画面**：两侧段文件向源素材多渲染 D/2（复用 G3 已登记的 `handleBeforeMs/handleAfterMs` 余量），在 assemble 内以 xfade 重叠混合，成片总时长不变。窗口定义：叠化 `[S−D/2, S+D/2]`（S=前段 outputEndMs）；`黑场入/出` 为片头片尾时间内渐亮渐暗（fade 滤镜，零手柄需求），窗口 `[start, start+D]` / `[end−D, end]`。
3. **缺料摊牌**：手柄余量（同源相邻段占用后净余）< D/2 时，G3 校验器报出确切缺口与**最大可行 D**，卡片明示，出路（降硬切/挪切点/缩时长）由用户逐切点定夺。**G4 永不静默降级**——指令文件里没有的转场绝不出现，指令里有而做不出的直接 blocked。

## 词表（第一批）

| 指令 | 语义 | 位次 | 时长字段 | 素材需求 |
|---|---|---|---|---|
| `硬切` | 无转场（缺省值） | 任意 | 禁止携带 | 无 |
| `叠化` | 本段退场与下一段入场交叠混合（xfade dissolve） | 不得在末段 | `transitionDurationMs` ∈ [100,1500] | 两侧净手柄各 ≥D/2 |
| `黑场入` | 成片开场自黑渐亮（时间内） | 仅首段 | 同上 | 无（fade 滤镜） |
| `黑场出` | 成片收尾入黑（时间内） | 仅末段 | 同上 | 无（fade 滤镜） |
| `抹开` | **预留档**：wipe 系。解锁需合同修订+宿主能力档实测 | — | — | — |

窗口纪律：转场窗口**只准落在口播停顿里**（与任何段 narrationStart/EndMs 区间零重叠）；与章节卡区间零交叠；`叠化` 期间不得有字幕 cue 起始（G3 出 ASS 后由 `--ass` 复检并入）。复合/含糊指令（"X/Y 按 G4 微调"）在词表层直接拒绝——批准什么就执行什么。

## 校验入口

```powershell
python skill/transition-expert/scripts/transition_probe_host.py --output-dir <G3-剪辑计划/转场/>          # 探宿主（xfade 名单实测解析）
python skill/transition-expert/scripts/transition_validate_plan.py --plan <G3-剪辑计划.json> --evidence <证据JSON> [--host-profile <能力档>]  # 深检，含叠化必传能力档
```

节点侧（validate_g3_plan/callback）只管词表、时长在场、卡-计划逐字一致；窗口/手柄/网格模型深检**只在本合同与本脚本**。

## 执行指令形状（批②落地）

批准收口后 G4 装配头一步产《G4-转场执行指令-v0.1.json》：`{skill, purpose: "transition_directive", planSha256, hostProfileSha256, gridInvariant: true, segments: [{segmentId, headExtraMs, tailExtraMs}], boundaries: [{fromSegmentId, toSegmentId, transition: "dissolve", durationMs, offsetMs}], masterFades: {fadeInMs, fadeOutMs}}`——由 `transition_directive.py` 从已批计划+能力档+证据源时长**确定性推导**（同输入必同产物），g4_render 按 head/tailExtra 扩切、g4_assemble 按 boundaries 链式 xfade；无转场项目走原 concat 路径逐字节不变。

## 接线说明书

| 节点 | 接缝 | 消费/产出 |
|---|---|---|
| G2 | 口播时值权威源 | 专员不碰内容层；口播实测毫秒是停顿窗口的判定基准 |
| G3 | 转场决策+深检 | 出计划前 probe 宿主 → 逐切点人工批准（第 8 列单一指令+时长，缺料摊牌上卡）→ `transition_validate_plan.py` 过检入最终回显与门禁收据；**批准≠继承，每项目重批** |
| G4 | 装配执行 | 装配头一步 `transition_directive.py`（plan+能力档+证据→指令，产物入装配记录）；g4_render/g4_assemble 逐字执行；缺能力/缺料→blocked，不降级 |
| G5 | 转场面 QA | 交付包必备 `transition-audit.json`（`transition_report.py` 从装配记录 filterGraph 反推执行==指令，sha256 新鲜度握手）；必检帧含**每转场窗口中点检查帧**（目视混合正常、非意外黑帧）；机器绿灯不背书观感（⑧纪律） |

改任一接缝先改本合同。经验库：**第一批不建**（无验证历史可沉淀）；跑过真实项目批准件后再议。
