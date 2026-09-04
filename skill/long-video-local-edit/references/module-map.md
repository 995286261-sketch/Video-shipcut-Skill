# Module Map

`long-video-local-edit` is the orchestration and local-edit runtime. It does not own user material intake.

Before dispatching or resuming a project, read `artifact-registry.md` and the project's `pipeline-state.json`. The state file is authoritative for completed artifacts and the next runnable node; folder names alone are not task status.

| Module | Status | Owns | Does not own |
| --- | --- | --- | --- |
| `$material-pack-intake` | Implemented | Seven-entry input pack, hashes, manifest, intake completeness | Evidence analysis, scripts, editing, rendering |
| `$media-evidence-prep` | Implemented | Local transcript and SRT/TXT/manifest evidence artifacts | Raw input pack, edit decisions |
| `$video-edit-plan` | G1 已实现；其余计划能力待实现 | 创作方向、叙事、源时间码候选、机器可读编辑计划 | 渲染、源文件修改 |
| `$local-video-render` | Implemented | Local TTS, subtitles, composition, exports, visual verification hard gate | Factual research, final QA judgment |
| `$media-qa-delivery` | Implemented | Artifact validation, traceability report, README, delivery bundle | Editing decisions |

Invoke only implemented Skills. All listed modules are callable.
