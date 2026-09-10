# music-expert → 剪辑管线 接线方案 v0.1（纯方案，未实施）

> 状态：设计稿。用户明示"先不动剪辑 skill 的节点，单纯先出方案"。**本方案获批前，六节点脚本与 SKILL.md 一行不改**；获批后按 §5 拆成逐项工单实施。

## 0. 边界

- 方向唯一：剪辑节点是消费方，music-expert 是被引用方；接线逻辑写在节点侧，不塞进 music-expert（保持其可独立迁移）。
- 每条引用都记 `sha256`（与 G3 报告/对齐 JSON 文件绑定），换曲即 hash 变化，下游校验失败即重走门禁。
- 三条纪律不松动：antiFill（口播时值权威，卡点只是建议）；授权红线（`licenseType=unknown` 的候选不得进成片 BGM，打分权重压不住红线）；人工门禁（选曲、对齐、排版分层都在 G3 卡上确认）。

## 1. 数据流总览

```
口播稿(G2) → 实测句时值 → 画面时间骨架 ──┐
                                          ├─ music_align.py → BGM-对齐建议.json → G3/G4
候选池+分析(G0/music-expert) → 能量段+卡点表 ─┘
```

产物消费矩阵：

| music-expert 产物 | 消费节点 | 用途 |
|---|---|---|
| `BGM-候选清单/登记` | G0 | `07_授权音频` 候选登记（同一许可证据链） |
| `BGM-分析报告` | G3 | 乐句表机器化、`hitPoints` 卡点 |
| `BGM-分析回显` | G3/G4 卡 | 分段表进回显（用户已确认卡样） |
| `BGM-推荐` | G3 | 选曲依据+分数+授权状态 |
| `BGM-对齐建议` | G3/G4 | 轨偏移、高潮锚点、吸附表、ducking/fade、**句级排版节奏分层输入** |
| 候选 `license*` 字段 | G5 | 交付审计 |

## 2. 逐节点方案

### G0（material-pack-intake）
- `use_library_later` 分支加一步：调 `music_search_freesound.py` / 收人工文件走 `music_register_candidate.py`（可带 `--tags`），产物目录即 `07_授权音频` 槽位；G0 门禁素材清单里 BGM 候选条目直接引用候选 JSON 路径+hash。
- 失败面：无 token/网络失败沿用结构化 `blocked`，G0 卡片如实呈现"自动轨不可用，转人工轨或降级无 BGM"。

### G2（media-evidence-prep，可选项、默认关）
- 写稿期反哺：若项目已定候选 BGM，把《分析回显》的分段表（各段时长、高潮位置）作为**创作参考**放进配音文稿卡头部（"高潮段 64s ≈ 可容 5–6 短句"）。仅建议，不生成、不删改句子。
- 是否启用留给用户逐项拍板（§6）。

### G3（video-edit-plan）——接线主战场
- **乐句表机器化**：现手工《BGM乐句表》改为脚本从《分析报告》`energySegments` 直出（引用 hash）。
- **转场点位**：剪辑边界对 `hitPoints` 的吸附表进 G3 回显，n/m 命中如实呈现；miss 的边界照常排。
- **句级排版节奏分层（用户 2026-09-09 拍板的新增依据）**：每句查其所在能量档（对齐建议里句↔段映射 + 报告档位规则），得到每句 `layoutTier ∈ {high, mid, steady, low/outro}`；G3 的逐句编排决定（信息密度、转场类型、字幕版式松紧）必须引用该档位。validator 增检：`bgmRef`（报告/对齐 JSON 路径+sha256）、`layoutTier` 合法且与对齐数据一致。
- 回显：G3 审核卡片表头新增"BGM 结构 / 排版档位"两列（沿用 render_g3_review_card 固定表模式）。

### G4（local-video-render）
- `g4_assemble.py` 新增 `--bgm-alignment <BGM-对齐建议.json>`：`offsetMs→atrim=start`、`fades→afade`、逐句 `ducking[]→侧链压低区间`；装配记录写 alignment 文件 hash。吸附表只进人工迭代参考（哪句边界挪几 ms），不改任何句长。
- 无对齐文件时行为与现状完全一致（向后兼容，老项目不坏）。

### G5（media-qa-delivery）
- 交付包 `metadata-validation-report` 增 BGM 节：曲目、来源 URL、licenseType、licenseEvidence、`distributionBoundary`、对齐/报告 hash；`unknown` 许可 → `g5_validate_delivery.py` 直接 fail。
- 章节卡/封面与音乐段落的对齐关系（可选）见 §6。

## 3. 合同变更清单（获批后）

1. edit-plan JSON：新增可选 `bgm` 块（report/alignment 路径+sha256、offsetMs、逐句 layoutTier）——validator 同步。
2. 装配记录：新增可选 `bgmAlignment` 块。
3. 交付 manifest：BGM 审计字段转必填（当工程声明了 BGM 时）。
4. 各节点 SKILL.md：路由表加"引用 music-expert 产物"一行；music-expert 的 Pipeline Integration 章节从"本版不接线"改为指向本方案。

## 4. 测试与验收（实施批次自带）

- 用 002 现成数据做端到端干跑：Interlinked 报告+对齐建议 → G3 validator 通过 → g4_assemble 带 `--bgm-alignment` 重渲 → 与 002 人工版对比响度/卡点，作为接线验收样。
- 全量回归（现 21 套件）保持绿；每个节点 patch 附新单测。

## 5. 实施拆分（下一张工单用，建议顺序）

1. **G4 patch**（收益最直接、改动最小、零门禁语义）
2. G3 contract + validator + 回显列（排版分层落地处）
3. G5 审计字段
4. G0 候选接线
5. G2 反哺（若用户拍板启用）

## 6. 待用户拍板项

| # | 决策 | 选项 |
|---|---|---|
| ① | G2 写稿反哺开不开 | 开（卡片展示结构参考）/ 关（默认） |
| ② | ducking 深度策略 | 固定衰减 dB / 按 BGM 与口播响度差自适应（后者更省事但要测） |
| ③ | 章节卡时间是否对齐音乐段落边界 | 对齐（观感顺）/ 只对齐叙事（现行为）——**仍待拍板** |
| ④ | layoutTier 档位规则 | **已拍板（N5）**：用 music_echo 四档规则（能量分位数，`--tier-quantiles` 可调），G3 终审逐行人工定夺 |

**裁定记录（2026-09-10）**：①已开——N9 节拍蓝图模式（G2 3.5 节循环）；②取"固定衰减 dB"——落地为混音合同参数 `--duck-reduction-db`+`--bed-gain-db`（**默认值经 zaku 实跑修正：初版 −18/12 在密集口播下压到 −40 LUFS 听不见，现默认 −12/6 + 可听窗守卫出窗即拒**），深度想换重跑 `music_mix_plan.py` 即可，自适应方案不再需要（ducking 窗口本身已由对齐产物逐句给定）；执行链见总账㉜。③保留待 zaku G5 或 003 实测观感后再议。
