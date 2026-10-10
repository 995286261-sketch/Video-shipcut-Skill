# Pipeline State Contract

Store every active project's UTF-8 JSON state at `工作台/<projectId>/pipeline-state.json`. Archived directories are never compatibility state or runtime inputs.

```json
{
  "schemaVersion": "0.1",
  "projectId": "<projectId>",
  "sourcePackRef": "<absolute material-pack.json path>",
  "authorization": "<authorization state>",
  "distribution": "<distribution state>",
  "approvalMode": "human",
  "autoPolicyRef": "<auto 模式必带：预授权策略 JSON 路径；human 模式无此字段>",
  "bgm": { "decision": "use_library_later", "preference": "<用户口头偏好原话|null>", "libraryPending": true,
           "clearCondition": "<清槽路径说明>", "evidence": null, "history": [] },
  "currentNode": "G1",
  "status": "in_progress",
  "nodes": {
    "G0": { "status": "completed", "artifactRefs": ["<material-pack.json>"] },
    "G1": { "status": "in_progress", "inputRefs": [], "artifactRefs": [], "humanReviewPoints": [], "approval": null },
    "G2": { "status": "pending", "inputRefs": [], "artifactRefs": [], "humanReviewPoints": [], "approval": null },
    "G3": { "status": "pending", "inputRefs": [], "artifactRefs": [], "humanReviewPoints": [], "approval": null },
    "G4": { "status": "pending", "inputRefs": [], "artifactRefs": [], "humanReviewPoints": [], "approval": null },
    "G5": { "status": "pending", "inputRefs": [], "artifactRefs": [], "humanReviewPoints": [], "approval": null }
  },
  "acceptedWarnings": [],
  "nextAction": "Run G1 direction confirmation.",
  "createdAt": "ISO-8601 UTC",
  "updatedAt": "ISO-8601 UTC"
}
```

Allowed node states are `pending`, `in_progress`, `review_required`, `blocked`, `completed`, `completed_with_accepted_warnings`, and — since v1.22.0 (auto-approval mode) — `completed_auto_reviewed` / `completed_auto_reviewed_with_accepted_warnings` (G5 closed by policy instead of human playback review; the `completed` prefix keeps existing manifest checks compatible). The runtime creates state only after G0 validates; it records G0 as completed and starts G1. Subsequent `currentNode` values normally advance in this order: `G1`, `G2`, `G3`, `G4`, `G5`, `completed`. Supported rework transitions are `G3` to `G2`, using `pipeline_state.py reopen --reason <reason> --rework-ref <existing-amendment-file>` when G3 discovers missing or corrected evidence, facts, or approved narration; and `G4` to `G3`, using `pipeline_state.py reopen-g3 --reason <reason> --rework-ref <existing-amendment-file>` when a G4 execution diagnostic exposes a G3 shot-plan defect. Both commands append `amendmentHistory`, preserve earlier artifacts, clear the superseded active approval, and require renewed approval at the reopened node. Never hand-edit state to simulate a rework transition. **回炉文案随 reason 生成（⑫，banshee-001 台账，2026-10-10 用户拍板甲案）**：两条 reopen 命令注入的 `nextAction` 与节点 `humanReviewPoints` 逐字携带本次 `--reason`（形如"按本次回炉原因完成返工后，重新申请 G3 批准——原因：<reason 原文>"），**不再写死任何宣称返工内容的句子**——banshee 那次纯混音参数回炉曾被旧硬编码说成"重建语义对齐"，账面失真靠编排方事后覆盖才救回；工具手里拿着必传的真相，就必须如实回显。审计以注入即真实的账面为准，无需再对照 `amendmentHistory` 反推。

Amendment rounds must also re-lock downstream hash-pinned contracts (转场实跑问题⑩，2026-09-24 用户裁决): after a reopened node is re-approved and before the G4 re-run, if the project has a BGM mix contract, run `music-expert/scripts/music_mix_contract_rebind.py` to produce a new-version contract that carries every mix parameter verbatim and re-pins only `evidence.planSha256` to the current approved plan (old contract file untouched, version 自增永不覆盖; tampered audio bytes refuse the re-lock outright). G4 assembly and the G5 BGM chain audit then consume the newest version — forging or hand-editing the old contract remains forbidden, and a permanently disclosed red light is not a steady state.

## BGM slot（G0 声明的机器事实，待找乐不靠聊天记忆）

`init` 把 material-pack.json 的 `bgm` 段抬进 state；`status` 在 `libraryPending` 时附 `reminder`（G1 末检索词卡 → 找乐 → 用户挑曲 → 官方渠道取得整轨并登记 → `bgm-choice` 翻槽）。翻槽唯一入口 `pipeline_state.py bgm-choice --decision provided|use_library_later|no_bgm [--evidence …] [--note …]`：翻到 `provided` 必须携带登记证据，每次翻槽 append 进 `history`。**G2/G3 的 approve 在 `libraryPending` 时硬拒绝**（N9 顺序：音乐必须在首个消费节点前在场）。

Legacy `run-manifest.json` is never an input to this state machine. Create a state file explicitly when a historical project is resumed; do not migrate in bulk.

## Approval payloads

All references below must be existing files beneath the active `工作台/<projectId>/` root. Full path definitions are in [Project Layout Contract](project-layout-contract.md).

Every G1–G5 approval first requires a registered `reviewGate`: a project-local `review-gate-receipt` JSON whose fixed `cardType`, required checklist, card reference, evidence references, and basis references pass `record-review`. The node must be `review_required`. Rework clears the affected node and downstream review gates, so a superseded card cannot approve amended inputs.

Receipt document shape (verbatim machine contract enforced by `review_gate.py`; documented 2026-09-11 after N8 issue ⑳ — the `reviewGate` stored in state is a summary, not this document):

```json
{
  "schemaVersion": "0.1",
  "projectId": "<active projectId>",
  "node": "G1",
  "cardType": "g1_direction_review",
  "reviewStatus": "ready_for_approval",
  "renderedAt": "<non-empty string>",
  "reviewCardRef": "<project-local presented card file>",
  "basisRefs": ["<existing project-local files>"],
  "checklist": [
    {"id": "direction_brief", "required": true, "status": "completed", "evidenceRef": "<existing file>"}
  ]
}
```

Path resolution (live-verified 2026-09-11, G2): every reference inside the receipt (`reviewCardRef`, each `basisRefs[]`, each `evidenceRef`) and the CLI `--review-gate-ref` itself are resolved against the **CLI working directory** (`project_layout.require_project_file` → `Path(reference).resolve()`), so they must be written repo-root-relative **including the `工作台/<projectId>/` prefix**; a bare project-root-relative path fails with "must be an existing file under <project root>".

**Reviewed-file fingerprint binding (R2, Leader 反馈, 用户 2026-09-24 裁决):** `record-review` additionally freezes the sha256 (uppercase hex) of every reviewed file the receipt references — `reviewCardRef`, each `basisRefs[]`, each checklist `evidenceRef` — into the state snapshot as `basisHashes: {reference: sha256}`. Before `approve` lets a gate pass it recomputes them all: a same-path replacement or content edit after registration means the version the human actually saw no longer exists, so approval is refused (exit 2, naming the changed files). The fix channel is always 重渲染审核卡 → 重新 `record-review` → 重新取得人工确认. Two carve-outs, stated openly: (1) the `--approval-ref` file is exempt from comparison — approval records are written at close, necessarily after registration; (2) snapshots recorded before this upgrade (no `basisHashes`) are refused with a re-record instruction (hard cut; zero live impact — every 工作台 project was already `completed` on 2026-09-24). Closed gates keep their `basisHashes` as the audit record of exactly which file versions the human approved.

**台账类文件的时序窗口（⑨，banshee-001 台账，2026-10-10 用户拍板甲案）.** Living ledgers (e.g. `问题清单-v0.N.md`) are grown while gates run, yet the moment a gate registers its receipt every `basisRefs` entry — the ledger included — IS hash-frozen and re-checked at close. The two facts coexist only through ordering, now written down: **append/correct a ledger only AFTER the gate that references it has closed** (each closed gate's `basisHashes` keeps its own point-in-time snapshot; later growth never invalidates a closed approval — this is what made every banshee append legal, and the banshee ledger's claim "not hash-frozen" was itself corrected in place as the first demonstration of this clause). Writing into the ledger between `record-review` and `approve` will (correctly) trip the close-time mismatch and force 重新 record-review → 重新人工确认 — so if an observation is genuinely urgent mid-gate, take that honest channel, never a silent edit. Ledger discipline is **append-only plus dated 改笔 with explanation** (纠错改笔 allowed, rewriting history without a marker forbidden); never hand-edit to delete or soften recorded facts. No machine change accompanies this clause: the ordering violation is already caught mechanically by the R2 recompute at close.

**G3 card provenance marker (转场实跑问题⑤, 用户 2026-09-24 裁决"统一更新模板"):** for node G3, `record-review` additionally requires the review card to contain the renderer's provenance line「此卡由通过校验的 G3 最终回显数据生成」(constant `G3_CARD_MARKER` in `review_gate.py`, emitted by `render_g3_review_card.py`). A hand-written or body-rewritten G3 card is refused at registration (the fixed 成片包装决定 section may be appended after rendering; the rendered body itself must stay untouched). Fix channel: rerun the renderer, then re-record.

Per node the `cardType` and checklist ids are exact sets (no extras, none missing; every item `required:true`, `status:"completed"`, `evidenceRef` resolving to an existing project file): G1 `g1_direction_review` → direction_brief, claims_and_boundaries, direction_card ｜ G2 `g2_evidence_narration_review` → fact_citation, approved_narration, voice_brief, g2_card ｜ G3 `g3_timeline_review` → approved_edit_plan, final_timeline_review, subtitle_timeline, bgm_decision, packaging_decisions, g3_card ｜ G4 `g4_candidate_review` → candidate_or_export, render_validation, playback_review_card ｜ G5 `g5_delivery_review` → delivery_manifest, qa_validation, playback_review, check_frames, distribution_boundary.

**Token semantics (issue ㉙, reworded after the tiger live test):** `--approval-response` must be the user's reply containing the confirmation token, stored **verbatim in full**. Message independence is NOT a contract requirement and was never machine-checkable — the CLI only sees what the agent hands it, so an "only-a-standalone-message" rule would be a gentleman's agreement that tempts the agent to paraphrase users into compliance (tiger: 确认G3/G4/G5 were all embedded in sentences three times running, and users plainly meant them). What the contract does enforce is provenance: the token text must appear in a real user reply (never agent-fabricated), the whole original reply lands in `approvalResponseVerbatim` and the approval record, and anything vague or wrong-node (`好的`, `确认G`, `确认G2` on G3) is still refused. If no token appears in any user message, the gate is NOT passed — the agent asks for an explicit confirmation instead of normalizing one into existence.

**Human-approval trust boundary (R2③, declared honestly):** the CLI cannot cryptographically prove a token came from a real person — it only sees what the caller passes in. The local-stage root of trust is the host session relaying the user's actual reply: the agent may **record** a real confirmation (the verbatim discipline above) but must never **manufacture** one. Machine enforcement (nodes stop at `review_required`, token normalization, `basisHashes` version binding, R1 QA-report parsing) shrinks what a dishonest caller could fake but does not eliminate the boundary; `approvalSource: "host-session"` records it. When the Proxima host review entry lands, it supplies trusted approval events and only this field changes. 本地记录来源 ≠ 已实现防伪审批; no account system at this stage (Leader 2026-09-24 明示不需要). The v1.22.0 auto-approval mode below is the second legitimate `approvalSource` — same principle: the system may approve **as policy**, and must never pretend a human did.

## Auto-approval semantics（v1.22.0 自动确认模式）

**输入端选模式，项目级登记。** `init --approval-mode human|auto`（默认 human；不声明=人工，安全兜底）。auto 必带 `--auto-policy <ref>`：策略 JSON `schemaVersion 0.1` / `kind auto-approval-policy` / `projectId` 与项目相符 / `statement` 非空（自动批准的逐字依据），登记预授权白名单 `preAuthorizations[]`（每条 category+basis+authorizedBy+authorizedAt+可选 parameters，三件套缺一即拒）。模式切换唯一入口 `set-approval-mode --mode X --reason`（append-only `approvalModeHistory`；禁隐式切换；fail-stop 不切模式）。历史 state 无 `approvalMode` 字段=human（R3 不追溯）。

**预授权受控词表（七类，词表不可扩展，未知类别当场拒）：**
`preview_voice_production`（basis 或 parameters.disclosure 必须含披露词"预览级"——绿灯通道披露一字不松）｜`loudness_blocked_exit`（parameters.exit 必须指明走哪条出路，且与现场计划的 exits 对得上；概括放行=拒）｜`transition_preview_waiver`（"你批准的是未见过的效果"豁免）｜`subject_policy`（G3 auto 必备：目标主体政策由输入工单承载）｜`warning_acceptance`（parameters.scopes 关键词必须覆盖每条现场警告）｜`sufficiency_shorten`（充分性缩短兜底）｜`music_delegated_selection`（auto 下 `bgm-choice` 翻槽的唯一入口——系统受托选曲必须有此授权）。

**永久 fail-stop（没有预授权通道，写进策略也被词表拒）：** 未清权音频（license 含 `uncleared`/`unverified`/缺失）× 对外分发；授权不明（unknown/unclear/待确认/pending）× 对外分发——distribution 不在内向词表 {`internal_test`, `local_only`, `not_for_distribution`} 即按对外处理（保守）；`userManuallyVerifiedClaims` 非空（人工背书断言属人工批准的项目）。此闸（`validate_distribution_rights`）补上"未清权×对外此前无端到端机器闸"的缺口；仅 auto 模式生效，human 模式行为不变（人审 distribution_boundary 项照旧覆盖，R3 不追溯已封存项目）。

**approve 分支（`--auto`）。** 机器验收链**全部照跑**（收据对账 002-⑦、basisHashes R2、BGM 槽拦截、节点载荷校验、R1 报告解析）——auto 改的只是口令段：换成信任类预检（`require_auto_approval`），扫描被审面（收据 basisRefs+本次载荷+G5 交付包审计文件）收集标记：`voiceTier=preview_only`、loudness plan `blocked_*`、`transitionPreviewWaiver`、`sufficiencyFallback`、`disclosed-exceedance`、acceptedWarnings。标记在场而预授权未覆盖 → emit blocked + `autoApprovalBlocked` 结构化记录（category/reason/decisionNeeded/note），节点停 review_required 等人。全过 → approval 记录：`approvalSource:"auto-policy"`、`approvalToken:"auto-policy:<node>"`、`approvalTokenVerbatim/approvalResponseVerbatim` = 策略 statement 原文＋适用预授权条款（**绝不伪造人类原话**）、`autoPolicyRef`、`preAuthorizationsUsed[]`。

**auto 项目里的人工单闸裁决。** fail-stop 后人工处理：照常传口令（不带 `--auto`）——该闸如实记 `approvalSource:"host-session"` + `autoModeOverride:true`，后续闸恢复自动。`--auto` 与口令参数同传=拒（一次批准只有一个来源）；human 项目传 `--auto`=拒；auto 项目 approve 两者都不传=拒（提示二选一）。`--approval-token/--approval-response` 自本版起在 parser 层改为可选、由代码按模式强制（human 缺口令的报错语义不变）。

**G5 披露形状（双向诚实闸）。** auto 关单要求 `human-review-decision.json` 以 `performed:false` + `replacedBy:"auto-policy:<ref>"` 在场——缺文件或 `performed:true` 均拒（自动不得声称做过人工审）；人工关单拒 `performed:false`（免审声明是自动模式专属）。`g5_validate_delivery.py` 同步校验 performed:false 必带 auto-policy 前缀来源。auto 关单终态 `completed_auto_reviewed`（带已接受警告 `completed_auto_reviewed_with_accepted_warnings`）。

**卡片纪律不变。** auto 模式下每节点回显卡照出（节点边界当场弹出、一张不少一张不跳），只换卡尾操作区措辞（style-guide v1.3：通过=「系统已自动确认·依据」；受阻=「自动确认受阻·需决策」）。改过必重出卡（basisHashes 与模式无关）；审批留痕.md 人话版同步"系统按策略自动确认"。

`approve` validates both `--approval-token` and `--approval-response` against the current node's canonical confirmation string (`确认 G1`…`确认 G5`). Since the A3 fix (2026-09-09) the CLI performs the normalization itself: the canonical form, the no-space typed variants users actually write (`确认G5`/`确认g5`), a bare `确认`, and — since 验收003 issue ㉕ (2026-09-23 修复批次1) — a natural reply whose **only** 确认/确定 clause names this node unconditionally (`确认G5，那么下一步是什么` / `OK，那这个G4我确认了`) are accepted for the node that is currently `review_required`. Conservative by design: any conditional, negative, imperative, adversative or interrogative marker anywhere (`如果…就`、`…的话就`、`帮我确认`、`不确认`、`确认G3吗`、`但`), or a reference to another node (`确认G2` on G3), refuses the whole reply; `好的`/`OK`/`确认G` stay refused. The state file always stores the canonical strings, plus `approvalTokenVerbatim`, `approvalResponseVerbatim`, and `normalizedFromVariant` so the original reply stays auditable. Agents must still paste the user's verbatim reply into the approval-record receipt.

- G1: `approvalRef` for direction confirmation.
- G2: `approvalRef`, `approvedNarrationRef`, `factCitationRef`, and `voiceBriefRef` (confirmed audition/voice setting). All must be existing project-local files and be listed in the review gate's `basisRefs`.
- G3: `approvalRef` plus the approved G3 plan reference and `timelineReviewRef`; both must be existing project-local files and be listed in `basisRefs`. Before subject-based selection, G3 must register a completed visual-analysis manifest as an input/artifact; the manifest is not interchangeable with G1 reference analysis or a contact sheet.
- G4 local-direct: `approvalRef`, `outputMode: local_direct`, `localRenderRef`, and `g4ValidationRef`. G4 ChatCut: `approvalRef`, `outputMode: chatcut`, plus an actual `chatcutExportRef` under `CHATCUT_EXPORT_ROOT`. The active render/validation or export must be listed in `basisRefs`. **Report parsing (Leader 反馈 R1, 方案 A, 2026-09-23):** on the local-direct branch `g4ValidationRef` must be a parseable JSON report produced by `g4_validate.py --candidate <候选成片>`; before approving, `approve` checks `status=="valid"`, `projectId` equals the state's project, and `candidate.sha256` equals the recomputed hash of `localRenderRef`'s current bytes — failed/non-JSON/wrong-project/stale-artifact all block with exit 2 ("不能仅检查文件存在"). The ChatCut branch has no local candidate video and stays outside this binding (scope note in the Leader 反馈 ledger).
- G5: `approvalRef`, `deliveryManifestRef`, and `g5ValidationRef`, both listed in `basisRefs`; pass accepted warnings as repeated `--accepted-warning` values (preferred) or a JSON array, resulting in `completed_with_accepted_warnings`. Per R1 the QA report is parsed the same way: approvable statuses `g5_pending_human_review`/`valid`/`completed*`; matching `projectId`; every registered artifact (single entries and list forms such as `chapterClips`) re-hashed against the bundle bytes next to the report — mismatch = the report does not describe this delivery bundle, blocked. See `media-qa-delivery/references/delivery-bundle-schema.md`.
