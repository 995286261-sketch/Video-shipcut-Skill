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
| `叠化` | 本段退场与下一段入场交叠混合（xfade `fade`，平滑交叉淡化。注：xfade 自带的 `dissolve` 是噪声抖动式混合、中点呈颗粒感，不是行业语义的叠化——2026-09-22 验收003 ㉔ 实片裁决改用 `fade`） | 不得在末段 | `transitionDurationMs` ∈ [100,1500] 且**必须偶数**（对称 D/2） | 两侧净手柄各 ≥D/2 |
| `黑场入` | 成片开场自黑渐亮（时间内） | 仅首段 | 同上 | 零手柄，**但须成片开头存在 ≥D 的无口播静默**（窗口同样不得压口播——口播从 0 起播的网格上黑场入物理不可行，issue ⑰；G3 出卡前先算，不可行就摊牌，别让用户在卡上才看到） |
| `黑场出` | 成片收尾入黑（时间内） | 仅末段 | 同上 | 零手柄，**但须成片结尾存在 ≥D 的无口播静默**（同上；标准出路=末句后追加片尾静默并重跑 music_align 再提案，作为可选路径写明） |
| `抹开` | **预留档**：wipe 系。解锁需合同修订+宿主能力档实测 | — | — | — |

窗口纪律：转场窗口**只准落在口播停顿里**（与任何段 narrationStart/EndMs 区间零重叠）；与章节卡区间零交叠；`叠化` 期间不得有字幕 cue 起始（G3 出 ASS 后由 `--ass` 复检并入）。复合/含糊指令（"X/Y 按 G4 微调"）在词表层直接拒绝——批准什么就执行什么。每段字段唯一（一个指令位）：**首段若要同时"黑场入+退场叠化"，须拆成两个 segment 各携一个指令**（seg-00a/00b 句内切段先例，网格照常连续）。

## 校验入口

```powershell
python skill/transition-expert/scripts/transition_probe_host.py --output-dir <G3-剪辑计划/转场/>          # 探宿主（xfade 名单实测解析）
python skill/transition-expert/scripts/transition_validate_plan.py --plan <G3-剪辑计划.json> --evidence <证据JSON> [--host-profile <能力档>]  # 深检，含叠化必传能力档
python skill/transition-expert/scripts/transition_preview.py --plan <计划> --evidence <证据JSON> --host-profile <能力档> --material-pack <G0/material-pack.json> --output-dir <G3-剪辑计划/预览小样/> --fps <成片帧率> [--crop-bottom-ratio <计划值>]  # 试装预览（批准前观感层，见下节）
```

节点侧（validate_g3_plan/callback）只管词表、时长在场、卡-计划逐字一致；窗口/手柄/网格模型深检**只在本合同与本脚本**。

## 执行指令形状（批②落地）

批准收口后 G4 装配头一步产《G4-转场执行指令-v<M.N>.json》（文件名版本自动递增、永不覆盖既有产物——reopen 重跑旧指令留盘作审计，issue ㉘）：`{skill, purpose: "transition_directive", planSha256, hostProfileSha256, gridInvariant: true, segments: [{segmentId, headExtraMs, tailExtraMs}], boundaries: [{fromSegmentId, toSegmentId, transition: "fade", durationMs, offsetMs}], masterFades: {fadeInMs, fadeOutMs}}`——由 `transition_directive.py` 从已批计划+能力档+证据源时长**确定性推导**（同输入必同产物），g4_render 按 head/tailExtra 扩切、g4_assemble 按 boundaries 链式 xfade；无转场项目走原 concat 路径逐字节不变。

## 试装预览（G3 批准前观感层，用户 2026-09-23 批准方案）

**防幻觉宪法：预览不新写一套"长得像"的效果。**`transition_preview.py` 从入口起复用 `validate_plan`（不过检=blocked，与指令同门槛）与 `build_directive`（拿完全相同的 extras/boundaries/masterFades）；裁剪/缩放/xfade/settb/黑场滤镜公式与 g4_render、g4_assemble 同式（跨专员零 import=插件四标准，故为故意同式复制，由测试逐片段断言同构锁死）。将来任何一边走路，另一边必然跟着变。

- **窗口**：每非硬切边界一条小样，覆盖成片网格 `[S−D/2−C, S+D/2+C]`，C=min(1200ms, 两侧成片段长−D/2, ≥0)。**永不展示批准裁切之外的画面**——手柄刚好=D/2 时小样即 D 长的混合窗本身。
- **纯画面无声**（用户裁决）：配音/BGM 混音属 G4，清单 disclaimer 与卡上明写；小样不复现源字幕遮蔽等包装层（`--crop-bottom-ratio` 传入时复现底部裁切），只验转场观感。
- **硬门禁+如实豁免**（用户裁决）：计划含非硬切转场 → 终审卡必挂预览清单（逐边界一一对应、planSha256==当前计划、文件 sha 匹配），缺=卡校验拒。唯一豁免=结构化 `blocked_previews`（无 ffmpeg/素材 sha 变更/渲染失败），编排必须把披露句"本机无法生成预览：你批准的是未见过的效果"原样上卡后放行，**不许静默跳卡**（㉔ 的手工小样无记录教训：renderArgs 全量入册、可逐字重建）。
- **产物**：《转场-预览清单-v<M.N>.json》（next_versioned_path 自增永不覆盖，㉘）+ 逐边界 `转场预览-<from>to<to>-v<M.N>.mp4`（边界 id 命名，弃用人肉 A/B/C）；中间件删除、renderArgs 入册。G3 收据 basisRefs 挂清单路径；**不新增 checklist id**（㉙ 教训）。计划改版→清单 planSha256 失配=自动 stale，逼重跑预览。

## 接线说明书

| 节点 | 接缝 | 消费/产出 |
|---|---|---|
| G2 | 口播时值权威源 | 专员不碰内容层；口播实测毫秒是停顿窗口的判定基准 |
| G3 | 转场决策+深检+试装预览 | 出计划前 probe 宿主 → **有非硬切转场必调 `transition_preview.py`，终审卡挂预览小样先看后批（硬门禁，见"试装预览"节）** → 逐切点人工批准（第 8 列单一指令+时长，缺料摊牌上卡）→ `transition_validate_plan.py` 过检入最终回显与门禁收据；**批准≠继承，每项目重批**。**推荐层分工（用户 09-23 拍板转正）**：提案与【默认=推荐｜理由】归编排（编辑判断），专员只摊可行性事实（缺口毫秒/最大可行 D/黑场前提），机器侧评分推荐不存在；决定权在人 |
| G4 | 装配执行 | 装配头一步 `transition_directive.py`（plan+能力档+证据→指令，产物入装配记录）；g4_render/g4_assemble 逐字执行；缺能力/缺料→blocked，不降级 |
| G5 | 转场面 QA | 交付包必备 `transition-audit.json`（`transition_report.py` 从装配记录 filterGraph 反推执行==指令，sha256 新鲜度握手）；必检帧含**每转场窗口中点检查帧**（目视混合正常、非意外黑帧）；机器绿灯不背书观感（⑧纪律） |

改任一接缝先改本合同。经验库：**第一批不建**（无验证历史可沉淀）；跑过真实项目批准件后再议。
