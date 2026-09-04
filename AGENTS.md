# P0-C Local Video Workflow

This repository contains a six-stage local video production workflow. Before responding to any request involving video, images, documents, transcripts, reference videos, brand assets, music, clips, editing, rendering, subtitles, covers, or delivery packages, read `skill/p0-c-pipeline/SKILL.md` and follow it.

Do not ask the user to name a skill or prepare technical artifacts. Infer the request is a new or continuing P0-C project and route through `p0-c-pipeline`.

## Automatic Routing

1. No validated material pack or project state: run G0 with `material-pack-intake`, writing the new project's formal artifacts under `工作台/<projectId>/`.
2. Existing `工作台/<projectId>/pipeline-state.json`: read it before any other action, report the current node, and invoke only the routed specialist skill. `归档/` is audit-only and must never be used to recover project state.
3. Do not read, repair, or infer state from legacy `run-manifest.json`.
4. Keep all source media read-only. Respect authorization and distribution limits.
5. Stop at every human-review gate. Record explicit approvals through `p0-c-pipeline`; do not treat chat context alone as a completed gate.

The six nodes are G0 material intake, G1 direction, G2 evidence/narration, G3 edit plan, G4 local/ChatCut editing, and G5 QA/delivery.

For project status, next steps, and local environment notes (development/platform-integration work, not video production requests), read `交接文档.md` at the repository root.
