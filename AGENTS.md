# P0-C Local Video Workflow

> **冻结登记（2026-10-10，用户令）**：本仓库自 **v1.33.0（`3f5f7ea`）** 起进入平台融入冻结期——只收两类改动：① connector 联调暴露的引擎缺陷修复（出新版本+tag，由 connector 升钉引用）；② 两笔平台挂账（sourceAsset 合同、gN- 前缀改名，均随平台命名/合同层一次成批）。**新功能一律不加。** 公司 connector 开发工作区＝`/Users/chuanzhangbigye/工作/MySpace/videocut-connector/`（独立目录，公司内容永不进本公开仓库=红线）；connector 侧以 tag 钉住本仓库版本为引擎。视频制作请求照常走下方路由。
>
> **冻结修正（2026-10-22，用户令）**：原冻结目的＝connector 成版期间"防乱改 skill"；现用户明令**恢复本地 skill 开发**。规矩改为：改动照常出版本+tag，git 本地提交保回退，**push 云仓前必须先问用户**；skill 验证没问题后再升 connector（engine/ 快照升钉）。本条款下的新功能批次＝能力预检申报（方案定稿见 `docs/改进-能力预检申报-v0.1.md`）。同日用户另定原则：**申报类机制一律机器硬闸＋如实披露豁免，不做软提醒**（防模型偏移/幻觉绕过）。

This repository contains a six-stage local video production workflow. Before responding to any request involving video, images, documents, transcripts, reference videos, brand assets, music, clips, editing, transitions, rendering, subtitles, covers, or delivery packages, read `skill/p0-c-pipeline/SKILL.md` and follow it.

Do not ask the user to name a skill or prepare technical artifacts. Infer the request is a new or continuing P0-C project and route through `p0-c-pipeline`.

## Automatic Routing

1. No validated material pack or project state: run G0 with `material-pack-intake`, writing the new project's formal artifacts under `工作台/<projectId>/`.
2. Existing `工作台/<projectId>/pipeline-state.json`: read it before any other action, report the current node, and invoke only the routed specialist skill. `归档/` is audit-only and must never be used to recover project state.
3. Do not read, repair, or infer state from legacy `run-manifest.json`.
4. Keep all source media read-only. Respect authorization and distribution limits.
5. Stop at every human-review gate. Record explicit approvals through `p0-c-pipeline`; do not treat chat context alone as a completed gate.
6. A fresh session must open with disk facts only (state file read now, file existence). Never recount prior progress from memory, chat history, or handoff docs; whether to continue or restart is the user's call. See `operator-dialogue.md` rule 6 (002 issue ①).

The six nodes are G0 material intake, G1 direction, G2 evidence/narration, G3 edit plan, G4 local/ChatCut editing, and G5 QA/delivery.

For project status, next steps, and local environment notes (development/platform-integration work, not video production requests), read `交接文档.md` at the repository root.

All skills stay flat under `skill/<name>/` — never add grouping directories. Node-specialist vs independent-expert classification lives in `metadata.pipelineNode` and the roster in `目录规范.md` ("skill/ 专员花名册"). Register every new specialist there.
