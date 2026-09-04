# Project Artifact Locations

Keep source inputs and generated production artifacts separate. Read the project index before writing and record each node's relative artifact references.

| Node | Location | Owner |
| --- | --- | --- |
| G0 material pack | `工作台/<projectId>/G0-素材包/` | `material-pack-intake` |
| G1 direction | `工作台/<projectId>/G1-创作方向/` | `video-edit-plan` |
| G2 evidence and narration | `工作台/<projectId>/G2-证据与口播/` | `media-evidence-prep` |
| G3 edit plan | `工作台/<projectId>/G3-剪辑计划/` | `video-edit-plan` |
| G4 local render and editable handoff | `工作台/<projectId>/G4-剪辑与渲染/` | `local-video-render` |
| G5 QA audit copy | `工作台/<projectId>/G5-交付包/` | `media-qa-delivery` |
| Final delivery bundle | `工作台/<projectId>/G5-交付包/交付包-v<version>/` | `media-qa-delivery` |
| Project indexes | `工作台/<projectId>/pipeline-state.json` | Orchestrator |

## G5 bundle

The default G5 bundle contains `final-video.mp4`, `cover.jpg`, `clips/` with 3–5 chapter clips, `source-timecode-list.json`, `edit-plan.json`, `subtitles.srt`, `export-config.json`, `metadata-validation-report.json`, `README.md`, and `failure-samples/README.md`.

The chapter files are a review-friendly grouping. They must not replace the fine-grained G3/G4 segment traceability; `source-timecode-list.json` must map chapter -> internal segment -> original asset and source `startMs/endMs`.

G5 must record machine results and human review separately. A missing or burned-in subtitle, black-frame anomaly, duration delta, authorization uncertainty, or detector limitation is a warning/review item, never an automatic pass.

The delivery bundle must not contain raw source media, credentials, caches, temporary renders, or unlicensed music. Practice packages must retain `personal_practice_unverified` and `not_for_distribution` boundaries.

## Minimal run manifest shape

```json
{
  "schemaVersion": "0.1",
  "projectId": "<projectId>",
  "currentNode": "G5",
  "status": "pending_human_review",
  "nodes": {
    "G1": { "status": "pending", "artifactRefs": [] },
    "G2": { "status": "pending", "artifactRefs": [] },
    "G3": { "status": "pending", "artifactRefs": [] },
    "G4": { "status": "pending", "artifactRefs": [] },
    "G5": { "status": "pending_human_review", "artifactRefs": ["工作台/<projectId>/G5-交付包/交付包-v<version>/"] }
  }
}
```
