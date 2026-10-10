# Operator Dialogue

Use short conversational commands. Always read state before replying. For every status, continuation, node handoff, and approval response, follow [路径展示合同](path-display-contract.md): show existing local artifact and input paths as clickable Markdown links, while leaving machine-state path fields as plain strings.

| User phrase | Pipeline action |
| --- | --- |
| New project / user provides media | Start G0: first present the fixed intake form (including an explicit BGM choice), then collect materials, validate the material pack, initialize state, and start G1. |
| Continue project / Next step | Report current node, valid inputs, risk, and exact next action. |
| Confirm G1 | After G1 is `review_required` and its fixed review-gate receipt is registered, record the exact response `确认 G1`, then register direction approval and route G2. |
| Confirm G2 | After G2's fixed review-gate receipt is registered, record the exact response `确认 G2`, then register narration, fact-decision, and confirmed voice-decision paths and route G3. |
| Reopen G2 from G3 | Only when G3 finds missing or corrected evidence, facts, or approved narration: create a reviewable amendment file, run the supported `reopen` transition, amend G2, and obtain renewed G2 approval before returning to G3. |
| Confirm G3 | After the G3 review-gate receipt is registered, record the exact response `确认 G3`, then register plan approval and route G4. |
| Confirm local G4 candidate | This is review feedback only. After the G4 review-gate receipt is registered, require the exact response `确认 G4` before routing G5. |
| ChatCut export is ready | Register the actual export path, create the G4 review gate, then require `确认 G4` before routing G5. |
| Confirm G5 | After the G5 review-gate receipt is registered, require the exact response `确认 G5`, then register human QA, accepted warnings, and close delivery. |
| Project status | Report state without changing it. |

Do not ask a user to produce hashes, SRT, timecodes, or JSON. Present reviewable candidates and record the user's decision.

## 单卡交互：每节点一次最终回显，决策点预选默认（用户 2026-09-11 定案，N8 活测产物）

1. **每节点对用户只有一个停靠点**：该节点的最终审核回显（门禁卡）。节点中途出现的**偏好类决策点**（标题、叙事角度、检索词、挑曲、风格与参数选择等）不再单独停下提问：Agent 按推荐纪律预选默认项，全部决策点连同【默认=推荐：X｜依据：…】标注并入最终回显卡；用户一句确认即过，否决哪条只重跑哪条环节后重新出卡。最终回显卡一律按[最终回显样式指南](final-echo-style-guide.md)的五段骨架渲染（用户 2026-09-11 定案，问题⑰）。
2. **门禁口令不减**：`确认G1`…`确认G5` 仍是人工批准，本规则取消的是中间停靠点，不是批准本身。**自动确认模式（v1.22.0，approvalMode=auto）是唯一例外通道**：口令被策略批准事件替代、留痕如实记 `auto-policy`（绝不伪造人类原话），卡片照出一张不减；口令也从未被"取消"——fail-stop 后人工仍用精确口令关闭该闸（该闸记 host-session + autoModeOverride）。细则见 [pipeline-state-contract](pipeline-state-contract.md)《Auto-approval semantics》。
3. **归属如实**：默认项被确认时，审批与裁决记录写"用户验收推荐默认项"并保留用户原话，不得写成"用户选择"。
4. **无授权不得默认放行的三类**：G0 开工单九问（那是采集用户输入，不存在推荐答案；2026-10-09 起固定追问项并入同卡，一卡问完）；G3 目标主体身份等**事实/身份判定**；G5 人工 QA 验收等**验收判定**。v1.2 样式指南后这三类卡也带【默认=推荐】（用户 09-22 裁决），但语义是"无授权不得默认放行"：人工模式必须用户在场确认；自动模式必须有对应预授权在场（如 subject_policy），G5 验收改走机检替代+如实披露（performed:false），不得冒充人审过。
5. **能力缺失即停靠点复活**：挑曲默认项=听觉模型试听笔记判"能使用"中的最高适配（不是机器分第一——N8 活测：机器分 0.881 居首者被模型判 2/10）；无听觉能力（capability_missing）时没有可推荐的耳朵，退回停靠点问用户，不得拿机器分冒充推荐。
6. **新会话开场只报磁盘事实（002 问题①，用户裁决成文）**：接到续接/状态类请求，开场陈述**只允许**来自当场读取的 `pipeline-state.json` 与文件存在性（"磁盘上有什么"），**禁止**凭记忆、聊天记录或交接文档转述"你上次做到哪、当时怎么决定的"——用户感知为被监视而非续接（001 验收载体因此整目录删除重跑）。续接还是从零，由用户看完磁盘事实后自己决定；Agent 不得代做这个决定。
7. **改过必重出卡（R2，Leader 反馈 2026-09-24）**：审核卡登记之后，被审文件（计划、旁白、字幕、成片、验证报告、审核卡本身、清单证据）任何改动都使旧卡失效——机器以 `basisHashes` 指纹对账强制拦截。正确通道=重渲染卡 → 重新 `record-review` → 重新取得 `确认Gn`，禁止拿旧卡催用户"确认"。Agent 可**代录**用户真实确认（逐字纪律不变），不可凭"自己觉得合格"**制造**确认；信任边界声明见 [pipeline-state-contract](pipeline-state-contract.md)。
8. **领域缩写首现必带人话释义（zaku-003 台账④，用户原话"这个东西我见都没见过"）**：说人话纪律不只管卡片模板——**一切用户可见文本（聊天过程通报、进度锚点、错误解释）同样受管**。领域缩写或内部术语第一次出现，必须当场跟一句人话释义（例："DSP 分析＝程序量波形：读 BPM/能量/卡点"），能直接说白话词的就用白话词。用户被术语挡在门外，是 Agent 的违规，不是用户的功课。
9. **自动确认模式的对话纪律（v1.22.0）**：approvalMode=auto 的项目，每节点回显卡仍在节点边界**当场弹出**（流式进度可见，不是最后一次性甩全量），卡尾操作区只有两种形态——通过：「系统已自动确认 · 依据：<策略条款+机检摘要>」；受阻：「自动确认受阻 · 需你拍板：<类别+选项（含默认推荐）>」，并把 `autoApprovalBlocked` 结构化记录翻成人话呈上。进度通报里点明当前模式（"本项目为自动确认模式"）。人工裁决通道永远敞开：用户随时可用精确口令关闭某一闸（该闸如实记 host-session），或 `set-approval-mode` 整体转人工（带理由留痕）。
10. **台账时序：闸没关，别动台账（⑨，banshee-001 台账，2026-10-10 用户拍板甲案）**：问题清单这类活账本也在每闸登记的拍照冻结面里（basisRefs 全部入 basisHashes，无一豁免——banshee 台账曾误记"哈希未冻"，已按本条纪律带日期改笔，是这条规矩的第一次现场示范）。合法窗口=**该闸关单（approve 通过）之后**再追加问题、再下改笔（改笔必须带日期与说明，只追加不涂史）；关单前确有紧急观察，走诚实通道（重新 record-review→重新确认），**绝不**在等批准途中静默动笔——那会让关单对账当场罢工、白白重问用户一次。机器兜底已存在（R2 关单重算），本条管的是编排的手。细则口径见 [pipeline-state-contract](pipeline-state-contract.md)《台账类文件的时序窗口》。

For a blocked node, explain the single missing input or decision and do not propose an invented substitute.
