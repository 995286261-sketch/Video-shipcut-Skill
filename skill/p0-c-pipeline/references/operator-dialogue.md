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
2. **门禁口令不减**：`确认G1`…`确认G5` 仍是人工批准，本规则取消的是中间停靠点，不是批准本身。
3. **归属如实**：默认项被确认时，审批与裁决记录写"用户验收推荐默认项"并保留用户原话，不得写成"用户选择"。
4. **不预选的三类**：G0 开工单五问（那是采集用户输入，不存在推荐答案）；G3 目标主体身份等**事实/身份判定**；G5 人工 QA 验收等**验收判定**——这三类永远需要用户在场的话。
5. **能力缺失即停靠点复活**：挑曲默认项=听觉模型试听笔记判"能使用"中的最高适配（不是机器分第一——N8 活测：机器分 0.881 居首者被模型判 2/10）；无听觉能力（capability_missing）时没有可推荐的耳朵，退回停靠点问用户，不得拿机器分冒充推荐。
6. **新会话开场只报磁盘事实（002 问题①，用户裁决成文）**：接到续接/状态类请求，开场陈述**只允许**来自当场读取的 `pipeline-state.json` 与文件存在性（"磁盘上有什么"），**禁止**凭记忆、聊天记录或交接文档转述"你上次做到哪、当时怎么决定的"——用户感知为被监视而非续接（001 验收载体因此整目录删除重跑）。续接还是从零，由用户看完磁盘事实后自己决定；Agent 不得代做这个决定。

For a blocked node, explain the single missing input or decision and do not propose an invented substitute.
