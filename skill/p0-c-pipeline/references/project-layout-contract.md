# P0-C Project Layout Contract

This is the single authority for active-project paths. Other Skills must link here rather than restating output roots.

| Variable | Value | Purpose |
| --- | --- | --- |
| `PROJECT_ROOT` | `工作台/<projectId>/` | Sole writable root for an active project. |
| `G4_ROOT` | `${PROJECT_ROOT}G4-剪辑与渲染/` | Editable project, local candidate, render records, and optional ChatCut export. |
| `CHATCUT_EXPORT_ROOT` | `${G4_ROOT}ChatCut-导出/<batch>/` | Actual files exported by ChatCut; never use Downloads as a project record. |
| `G5_BUNDLE_ROOT` | `${PROJECT_ROOT}G5-交付包/交付包-v<version>/` | Canonical complete delivery bundle and G5 audit closure. |
| `ARCHIVE_ROOT` | `归档/<date>-<projectId>/` | Immutable post-completion closure, created only after explicit archival approval. |

`成品/` and historical `工作区/` are legacy read-only locations. New projects and new versions must never write there. `归档/` is audit-only and is never a runtime input.

Every state approval reference must resolve to an existing file under `PROJECT_ROOT`. G4 local-direct approval additionally requires a validated local render and G4 validation report. G5 approval additionally requires a validated `delivery-manifest.json` and G5 validation report.
