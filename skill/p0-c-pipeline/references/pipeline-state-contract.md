# Pipeline State Contract

Store every active project's UTF-8 JSON state at `工作台/<projectId>/pipeline-state.json`. Archived directories are never compatibility state or runtime inputs.

```json
{
  "schemaVersion": "0.1",
  "projectId": "<projectId>",
  "sourcePackRef": "<absolute material-pack.json path>",
  "authorization": "<authorization state>",
  "distribution": "<distribution state>",
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

Allowed node states are `pending`, `in_progress`, `review_required`, `blocked`, `completed`, and `completed_with_accepted_warnings`. The runtime creates state only after G0 validates; it records G0 as completed and starts G1. Subsequent `currentNode` values normally advance in this order: `G1`, `G2`, `G3`, `G4`, `G5`, `completed`. Supported rework transitions are `G3` to `G2`, using `pipeline_state.py reopen --reason <reason> --rework-ref <existing-amendment-file>` when G3 discovers missing or corrected evidence, facts, or approved narration; and `G4` to `G3`, using `pipeline_state.py reopen-g3 --reason <reason> --rework-ref <existing-amendment-file>` when a G4 execution diagnostic exposes a G3 shot-plan defect. Both commands append `amendmentHistory`, preserve earlier artifacts, clear the superseded active approval, and require renewed approval at the reopened node. Never hand-edit state to simulate a rework transition.

Legacy `run-manifest.json` is never an input to this state machine. Create a state file explicitly when a historical project is resumed; do not migrate in bulk.

## Approval payloads

All references below must be existing files beneath the active `工作台/<projectId>/` root. Full path definitions are in [Project Layout Contract](project-layout-contract.md).

- G1: `approvalRef` for direction confirmation.
- G2: `approvalRef`, `approvedNarrationRef`, `factDecisionRef`, and `voiceDecisionRef` (confirmed audition/voice setting).
- G3: `approvalRef` plus the approved G3 plan reference. Before subject-based selection, G3 must register a completed visual-analysis manifest as an input/artifact; the manifest is not interchangeable with G1 reference analysis or a contact sheet.
- G4 local-direct: `approvalRef`, `outputMode: local_direct`, `localRenderRef`, and `g4ValidationRef`. G4 ChatCut: `approvalRef`, `outputMode: chatcut`, plus an actual `chatcutExportRef` under `CHATCUT_EXPORT_ROOT`.
- G5: `approvalRef`, `deliveryManifestRef`, and `g5ValidationRef`; pass accepted warnings as repeated `--accepted-warning` values (preferred) or a JSON array, resulting in `completed_with_accepted_warnings`.
