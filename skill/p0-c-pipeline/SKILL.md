---
name: p0-c-pipeline
description: "Coordinate P0-C's six-stage local video workflow: G0 material intake, G1 direction, G2 evidence and narration, G3 edit planning, G4 local/ChatCut editing, and G5 QA delivery. Use whenever a user provides or mentions video, image, document, transcript, reference video, brand asset, or music and wants clips, an edited video, a social-media video, an edit plan, a render, a delivery package, or project continuation."
metadata:
  pipelineNode: orchestrator
---

# P0-C Pipeline

Use this orchestrator as the conversational entry point. Project state and formal node artifacts belong only under `工作台/<projectId>/`; `归档/` is audit-only and never a workflow input. It routes work to the six specialist skills; it does not replace their content decisions or render logic.

Read `references/runtime-dependencies.md`, `references/toolchain-manifest.json`, and `references/toolchain-setup.md` when setting up a new machine or handing the Skill to another user. A missing local runtime or model is a structured block, not a reason to invent a voice, transcript, or successful render.

## G0 to G5

The six nodes are `G0 Material Intake`, `G1 Direction`, `G2 Evidence and Narration`, `G3 Edit Plan`, `G4 Editing and ChatCut`, and `G5 QA and Delivery`. G0 is mandatory: never ask the user to prepare timecodes, hashes, subtitles, or JSON.

## State first

Read `工作台/<projectId>/pipeline-state.json` before every action. This UTF-8 JSON file is the only orchestration truth. Never infer state from file names, modification times, chat history, archived materials, or legacy `run-manifest.json`.

For every user-facing status, continuation, handoff, or approval response, follow [路径展示合同](references/path-display-contract.md) and [项目布局合同](references/project-layout-contract.md): keep machine references as plain strings in JSON, but render existing artifact and input paths as clickable Markdown links with project-relative forward-slash paths.

For a new project, start G0 with `$material-pack-intake`. Before accepting files, present the fixed G0 intake form in `$material-pack-intake` and explicitly record the user's BGM choice (`provided`, `use library later`, or `no BGM`), keeping any verbatim music preference in `BGM preference:`. The declaration is machine-carried from here: `init` lifts the pack's `bgm` slot (decision, preference, `libraryPending`) into pipeline state, `status` surfaces a pending reminder, and G2/G3 approvals are blocked until the slot is cleared — the user picks a track, registers the official-channel file, then `pipeline_state.py bgm-choice --state … --decision provided --evidence <registration record>` (or an explicit `no_bgm`). After the pack validates, create state with:

```powershell
python skill/p0-c-pipeline/scripts/pipeline_state.py init --project-id <projectId> --source-pack <material-pack.json> --state <pipeline-state.json> --authorization <value> --distribution <value>
```

Approval mode is chosen at the input side (v1.22.0): add `--approval-mode human|auto` (default `human` — an undeclared project is always human-gated). `auto` additionally requires `--auto-policy <策略 JSON>`: a pre-authorization policy (`kind: auto-approval-policy`, seven-category controlled vocabulary) that the gate consumes at approve time. In auto mode each gate's human token is replaced by a policy approval event (`approve --auto`, recorded as `approvalSource: "auto-policy"` with the policy clause as verbatim — never a fabricated human reply); trust-class items not covered by pre-authorizations fail-stop with a structured `autoApprovalBlocked` record and wait for a human, who may close that single gate with the exact token (recorded `host-session` + `autoModeOverride`). Review cards are still rendered at every node boundary. Full semantics: [pipeline-state-contract](references/pipeline-state-contract.md)《Auto-approval semantics》.

Use `status` when the user says "project status", "continue", or "next step". It returns the current node, valid inputs, warnings, human-review items, and the next conversational action.

## Routing

| Current node | Invoke | Stop condition |
| --- | --- | --- |
| G0 | `$material-pack-intake` | Material pack validates with hashes and authorization status. |
| G1 | `$video-edit-plan` in G1 mode | User approves direction, audience, and expression boundary. |
| G2 | `$media-evidence-prep` | Approved narration and fact decision are explicitly registered. |
| G3 | `$video-edit-plan` in G3 mode | User approves timecoded shots, subtitle treatment, BGM, cover, and duration. |
| G4 | `$local-video-render` | Local render is validated and user reviews the candidate; ChatCut is used only if micro-adjustment is requested. |
| G5 | `$media-qa-delivery` | Machine QA and user playback review are both registered. |

Record a node's artifact references and review items, set it to `review_required`, then create and register its machine-validated review-gate receipt before asking for approval. Use `approve` only after the user's confirmation is explicitly received and recorded; the CLI canonicalizes the typed forms users actually write (`确认G5`, bare `确认` for the current gate) and keeps the verbatim reply in state, but a card, a selection, or a vague acknowledgement still cannot advance state. Read `references/operator-dialogue.md` for the exact conversational handoffs and `references/pipeline-state-contract.md` for required fields.

Per operator-dialogue's single-echo contract (用户 2026-09-11 定案): a node stops for the user exactly once — its final review echo, rendered on the five-section skeleton in [final echo style guide](references/final-echo-style-guide.md) (conclusion first; machine fields only in the evidence section). Mid-node preference decisions (title, angle, search terms, track pick, style parameters) carry preselected defaults rendered as 【默认=推荐｜依据】 on that card; the user's rejection re-runs only the rejected step. Gate tokens never disappear, G0 intake questions are never pre-answered, and fact/identity/acceptance decisions (G3 目标主体, G5 human QA) are never defaulted.

Workbench location (v1.35.0, 用户令 2026-10-23): 新项目 G0 前先 `workspace-root` 查登记——未选址出一次性小卡、经 `workspace-root --set --user-words '<逐字原话>'` 落账（AI 永不代选）；`init` 硬闸按登记根对账落点，越界罢工点名。合同见 `references/workspace-root-contract.md`（connector `workspaceRootRef` 语义的本地补齐）。

Capability preflight (v1.34.0, 用户令 2026-10-22): G0 按 `references/capability-audit-contract.md` 出盘点并入册；每节点开工读 `status` 的 `capabilityAudit` 决定摊卡——**有事才报**（全绿零噪音，与当前节点相关的缺口进③区一行）。G3 批准的计划若新增能力（转场/BGM/配音），重跑 `capability_audit.py` 增量新版并重新入册（版本自增不覆盖），变化行随 G4 闸呈小卡。G4 装配命令**必带 `--pipeline-state`**（硬闸绑定核验；历史补跑缺省只走如实披露通道并摊卡，新编排禁用）。

## Hard gates

- G2 approval requires `approvedNarrationRef` and `factCitationRef`.
- G3 approval requires an explicit approval record and cannot use a superseded narration draft.
- A `use_library_later` BGM slot cannot stay pending through G2 or G3 approval: clear it with `bgm-choice` plus real registration evidence, or record an explicit `no_bgm`. Never let chat context pretend the slot is cleared.
- **选曲关单时长比对（issue ⑫，sinjuku 实测：177.875s 曲配 180s 目标拖到 G2 才爆）**：`bgm-choice --decision provided` 关单时，编排必须用登记件里的 `trackDurationMs` 机器比对 G0 目标时长下限；轨短于下限时确认卡/回显必须亮 warning 并给出两条出路（缩 timeline 或换更长曲），**禁止静默放行到 G2**。分析报告里时长字段有值而不比对=编排漏步。
- G4 local-direct branch can advance with a validated local candidate and explicit user review. When ChatCut is selected, G4 cannot advance without a real ChatCut export reference; a flattened preview is not an editable handoff.
- G5 cannot complete until human QA is recorded. Accepted warnings remain visible. **Auto mode exception (v1.22.0)**: human playback QA is replaced by machine QA + honest disclosure — `human-review-decision.json` must carry `performed:false` + `replacedBy:"auto-policy:<ref>"`, the project closes as `completed_auto_reviewed*`, and the delivery README discloses the substitution. Claiming `performed:true` in auto mode (or `performed:false` in human mode) is refused both ways.
- `not_for_distribution`, unknown authorization, or `user_manually_verified` claims cannot be silently upgraded or bypassed. In auto mode these are permanent fail-stops with no pre-authorization channel: uncleared-license audio × external distribution, unknown authorization × external distribution, and non-empty `userManuallyVerifiedClaims` block every `approve --auto` outright (`validate_distribution_rights`).

## Delivery boundary

Use the canonical roots in [项目布局合同](references/project-layout-contract.md). Do not put raw source media, credentials, caches, or unlicensed music in the delivery package.
