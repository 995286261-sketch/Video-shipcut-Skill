# 响度合同（loudness-contract）——唯一事实源

版本 v0.1（2026-09-28 立册）。一切响度口径以本文件为准；脚本与报告与本文件冲突时，以本文件为裁判、脚本改。调研背景与裁决过程：`docs/响度专项-调研与方案讨论-v0.1.md`。

## 1. 量纲纪律

| 量纲 | 含义 | 用途 | 禁止 |
|---|---|---|---|
| LUFS（integrated） | 集成响度＝人耳平均"有多响"（ITU-R BS.1770-4 / EBU R128） | 目标态、验收对账 | 与峰值混称"分贝" |
| dBTP | 真峰值＝会不会爆 | TP 上限闸 | 当响度用 |
| LU | LRA 动态宽度单位 | 参考记录 | 设闸（暂不设） |
| dB（增益量） | 相对变化量（如 bed −12 dB＝压低 12 分贝） | 混音合同参数 | 当绝对响度 |

用户卡片写人话（"整片平均响度""会不会爆音"），数字全放 JSON 数据层与卡的"值"列。

## 2. 目标档（PROFILES）

| 档 | I 目标 | TP 上限 | LRA 目标 | 出处 |
|---|---|---|---|---|
| `video` | −14 LUFS | −1.5 dBTP | 9 LU | 现行 g4 实链验证值（kshatriya/002/unicorn 实跑），与 ffmpeg-normalize `streaming-video` 预设（−14/−2）同档 |
| `podcast` | −16 LUFS | −2.0 dBTP | 7 LU | ffmpeg-normalize `podcast` 预设（AES 通行档） |

规则：目标必须**显式**给——`--profile` 或 `--target-lufs/--true-peak/--lra-target` 三件套全给；半默认、混给、未知档一律拒（⑧ 口径继承：不许冒出来源不明的默认值）。新档须带查证出处入本表，不得临时拍脑袋。

## 3. 验收闸常数（工程惯例值，如实声明，非隐藏默认）

- `toleranceLu` 默认 **1.0 LU**（`|实测I − 目标I|` 上限）；CLI 可覆盖，报告须记 `toleranceSource`（合同默认/CLI 显式覆盖）。
- `tpSlackDb` **0.3 dB**：loudnorm 保证的是估算 TP 而非硬限幅，验收允许实测 TP 超上限 0.3 以内；再超即不过。
- LRA 只记不闸（v0.1 立场，闸否随接线工单议）。

## 4. 双口径与防回退

- 规划口径 = loudnorm pass1 `print_format=json`（input_i/input_tp/input_lra/input_thresh）——这四个数原样喂回第二遍 `measured_*`，规划与执行零换算。
- 验收口径 = ebur128——与执行链不同滤镜，互不背书；同文件双口径读数差 >0.5 LU = 引擎异常（单测 `test_engine_agreement` 锁死）。
- **静默回退防线**（官方文档 ffmpeg filters 8.97）：linear=true 前提＝目标 LRA≥源 LRA 且线性增益后估算 TP≤上限，任一不满足滤镜**退回 dynamic 且不报错**。专员纪律：先算后放行，不满足→`blocked_*`（落盘摊开、exit 1、exits 给可修数值）；接线后执行者若发现实际以 dynamic 跑（如 stats `normalization_type` 非 linear），视同违规拦单。

## 5. 偏差三成因（failed 排查顺序，failNote 指向本节）

1. **源天花板**：素材峰均比过高，线性推到 TP 上限即到顶——`loud_plan.ceilingLufs` 就是该源的物理答案（unicorn 跑 −16.1、kshatriya-002 −15.2 先例）。出路=提 TP 上限/降目标/先压缩/换源，逐数值化在 exits。
2. **混音口径**：全片主轨含 BGM 合成，读数≠纯口播；纯口播响度须对配音源文件单独 `loud_measure`。
3. **回退/链漂移**：执行未用逐字 chain 或源文件已换（sha 对不上规划 source）——重规划，不碰运气重跑。

## 6. 产物形状

所有产物带身份头：`{"skill":"loudness-expert","purpose":"loud_measure|loud_plan|loud_verify","schemaVersion":"0.1","projectId":…,"source":…}`。source 字段落**解析后的绝对路径**（调用方从仓库根传相对路径时专员先行解析——09-28 zaku 实测彩排抓出：相对串在他处对账即失联；重规划与 G2 校验器均按此对账）。文件命名《响度-实测报告|响度-归一化计划|响度-验收审计-v0.N.json》，版本自增永不覆盖（㉘）。回显卡必须由 `loud_echo.py` 从产物渲染（呈现层零算术；卡尾出处行"此卡由通过校验的响度专员产物生成"——⑤ 先例，接线时 record-review 校验该行）。

## 7. 不编造纪律

- 无 ffmpeg＝`capability_missing`（exit 2），不得由人/模型代填数字；
- 报告数字与盘上实测可复算（同文件重测必现，单测锁）；
- 模型听感（omni 第二只耳朵，接线后属呈现层意见档案）**永不充当验收数值**——数字闸只认本专员实测。

## 8. 接线说明书（工单 `docs/响度接线工单-v0.1.md` 2026-09-28 经用户"接"令开工；**批一 G2、批二 G3、批三 G4 已接线生效**，批四 G5 为届时蓝本、兑现前不得引用）

用户定案节奏：独立测试完毕（本册 36 例绿）后另开接线工单；接一个、WorkSpace 实跑验一个、用户点头再下一个。挂接点：

1. **G2 配音【已接线·批一 2026-09-28】**：每条候选配音源跑 `loud_measure`+`loud_plan`（目标档显式必给，现行 video）→ 试听卡逐字披露天花板（"整片平均响度最响可到 X LUFS（目标 −14）"，操作细则见 `skill/media-evidence-prep/references/g2-choice-cards.md` §3.5）；够不到时同轮选项卡（出路取自产物 `exits`），不得静默延到 G4。机验落点=`validate_g2_decision.py` **schema 0.2**：决策必带 `loudnessPlanRef`，校验器核对产物身份（skill/purpose 头）与旁白源 sha256——**批准后换配音=放行失效**（R2 同型）；blocked 计划是合法披露（用户在卡上选出路即留痕）。历史 0.1 决策不追溯（R3）。彩排实录：unicorn 真实口播源 TP 已贴上限、线性到不了 −14 → blocked_true-peak 如实摊开，出路"先压缩"正是当年 G4 实走链——披露在 G2 提前兑现；篡改彩排（拷贝上换字节）被 sha256 对账拦下。对应台账 ⑪-③ 裁决。
2. **G3 剪辑计划【已接线·批二 2026-09-28】**：目标档双式记账——计划必带 `packagingDecisions.loudnessTarget` 三元组，逐字等于决定 `loudnessPlanRef` 专员计划的 `targetProfile`（`validate_g3_plan.py` 批量拒缺拒差；用户换档=回 G2 重规划，机器不代换）；包装决定节"响度目标档"行卡样式与纪律见 `skill/video-edit-plan/references/g3-choice-cards.md`。彩排实录（zaku 链）：真决定+真专员计划 v0.5 装配计划过闸 exit 0；卡上改 −16 即拒（"must equal G2 loudness plan"）。
3. **G4 装配【已接线·批三 2026-09-28，丙·分档口径（用户"走你推荐的"拍板）】**：`g4_assemble.py --loudness-plan` 产物握手——专员身份头、规划源 sha 对账（批准后换配音=罢工，R2 同型延伸）、串项目罢工；三口径对账 `G2 targetProfile == manifest.loudnessTarget（g4_prepare 自 G3 包装决定镜像）== 执行链参数`，缺一拒装、换档回 G2/G3 重批（机器不代换）。分档执行：**ready→linear-verbatim**，逐字两遍线性 chain（measured_* 同源数、规划与执行零换算），预渲染按纯口播量纲实测、|偏差|>容差=罢工（静默回退 dynamic 必超差、同闸兜住 §4 红线）；**blocked_*→controlled-dynamic**，显式执行 G2 出路卡批准的标准压缩链（按 targetProfile 三参数展开、单遍动态强制 print_format=json），loudnorm stats 落账，I 超差如实记 `disclosed-exceedance`+reviewNote、必须进 G4 回显第③节摊开确认——永不静默但**不罢工**：彩排实证真 TTS 长天源动态落点 −15.6 对目标 −14（超差 1.60 LU），blocked 档的出路本来就是肉眼选过的让步，硬闸=一切真项目永久卡死=假闸（TP 超上限+余量仍是两档共同硬闸，限幅链路坏不是响度取舍）。旧 `--normalize-narration-lufs` 仅留历史补跑（R3）。彩排实录（WorkSpace/响度接线-G4彩排-v0.1）：blocked 档=zaku 真口播+真专员计划全流程装成（含三口径、stats 落账）；ready 档=unicorn《阿吉叶玛》真成品音源新计划，逐字线性链落点 −14.0（偏差 0.00 LU、normalization_type=linear 实证）；负向彩排顺手抓到**串项目罢工实盘第一案**（批二彩排计划 zaku-g2-rehearsal 对 zaku-intro-001 主 manifest 被拦）；错镜像/换配音/外来头三案全拦在重渲染之前。卡样式与纪律见 `skill/local-video-render/references/g4-choice-cards.md` 响度执行记账。
4. **G5 交付**：《响度-验收审计》产物入交付包 REQUIRED（`loudness-audit.json`，R1 解析指纹、R2 basisHashes 冻结自动覆盖）；`--media` 复测对账。
5. **迁移**：整目录拷贝即用；依赖仅 PATH 的 ffmpeg/ffprobe；端到端测试在新宿主重跑物理阶梯锁验表。
6. **历史封包**：R3 政策——已封存交付包不追溯补件。
