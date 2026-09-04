---
name: video-shipcut-pipeline
description: "Coordinate Video-shipcut's six-stage local video workflow: G0 material intake, G1 direction, G2 evidence and narration, G3 edit planning, G4 local/ChatCut editing, and G5 QA delivery. Use whenever a user provides or mentions video, image, document, transcript, reference video, brand asset, or music and wants clips, an edited video, a social-media video, an edit plan, a render, a delivery package, or project continuation."
metadata:
  pipelineNode: orchestrator
---

# Video-shipcut Pipeline

Use this orchestrator as the conversational entry point. Project state and formal node artifacts belong only under `工作台/<projectId>/`; `归档/` is audit-only and never a workflow input. It routes work to the six specialist skills; it does not replace their content decisions or render logic.

Read `references/runtime-dependencies.md`, `references/toolchain-manifest.json`, and `references/toolchain-setup.md` when setting up a new machine or handing the Skill to another user. A missing local runtime or model is a structured block, not a reason to invent a voice, transcript, or successful render.

## G0 to G5

The six nodes are `G0 Material Intake`, `G1 Direction`, `G2 Evidence and Narration`, `G3 Edit Plan`, `G4 Editing and ChatCut`, and `G5 QA and Delivery`. G0 is mandatory: never ask the user to prepare timecodes, hashes, subtitles, or JSON.

## State first

Read `工作台/<projectId>/pipeline-state.json` before every action. This UTF-8 JSON file is the only orchestration truth. Never infer state from file names, modification times, chat history, archived materials, or legacy `run-manifest.json`.

For every user-facing status, continuation, handoff, or approval response, follow [路径展示合同](references/path-display-contract.md) and [项目布局合同](references/project-layout-contract.md): keep machine references as plain strings in JSON, but render existing artifact and input paths as clickable Markdown links with project-relative forward-slash paths.

For a new project, start G0 with `$material-pack-intake`. Before accepting files, present the fixed G0 intake form in `$material-pack-intake` and explicitly record the user's BGM choice (`provided`, `use library later`, or `no BGM`). After the pack validates, create state with:

```powershell
python skill/video-shipcut-pipeline/scripts/pipeline_state.py init --project-id <projectId> --source-pack <material-pack.json> --state <pipeline-state.json> --authorization <value> --distribution <value>
```

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

Record a node's artifact references and review items before asking for approval. Use `approve` only after the listed human decision is explicitly received. Read `references/operator-dialogue.md` for the exact conversational handoffs and `references/pipeline-state-contract.md` for required fields.

## Hard gates

- G2 approval requires `approvedNarrationRef` and `factDecisionRef`.
- G3 approval requires an explicit approval record and cannot use a superseded narration draft.
- G4 local-direct branch can advance with a validated local candidate and explicit user review. When ChatCut is selected, G4 cannot advance without a real ChatCut export reference; a flattened preview is not an editable handoff.
- G5 cannot complete until human QA is recorded. Accepted warnings remain visible.
- `not_for_distribution`, unknown authorization, or `user_manually_verified` claims cannot be silently upgraded or bypassed.

## Delivery boundary

Use the canonical roots in [项目布局合同](references/project-layout-contract.md). Do not put raw source media, credentials, caches, or unlicensed music in the delivery package.
