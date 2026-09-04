# Evidence Contract

Input: a validated material-pack root, one registered local source file, and a caller-owned workspace.

Output: source probe, SHA-256 reference, timestamped transcript JSON, SRT, TXT, manifest, and validation result. Generated paths must remain outside the material pack.

For new projects, G2 writes project-level artifacts under `工作台/<projectSlug>/G2-证据与口播/`. Historical `工作区/素材分析/<projectSlug>/` paths are archived and must not be read as workflow inputs:

- `G2-证据准备报告-v0.1.md`
- `G2-证据清单-v0.1.json`
- one or more contact sheets per source video
- `转写/<asset-short-id>-transcript.json`
- `转写/<asset-short-id>/transcript.srt`
- `转写/<asset-short-id>/transcript.txt`
- `转写/<asset-short-id>/manifest.json`

`G2-证据清单-v0.1.json` must include:

- `schemaVersion`
- `projectId`
- `status`
- `evidencePolicy`
- `sourceEvidence[]`
- `factEvidenceRefs[]`
- `handoff`

Each `sourceEvidence[]` item must include:

- `assetId`
- `sha256`
- `sourceProbe.durationMs`
- `sourceProbe.video`
- `sourceProbe.audio`
- `contactSheetRef`
- `transcriptRef` when transcription exists
- `transcriptArtifactsRef` when SRT/TXT validation exists
- `cacheKey` on the transcript JSON: `assetId`, source `sha256`, language, model, device, compute type, and runtime version. Matching keys must reuse the existing transcript and derived SRT/TXT/manifest; do not transcribe the same source again.
- `warnings[]`

Status meanings:

- `completed`: artifact validation passed; transcription remains machine-generated draft evidence.
- `failed`: a source hash, media stream, local model, output boundary, or timestamp validation check failed.

Downstream Skills must retain `assetId`, source SHA-256, and original timecodes when citing this output. G2 registration makes a source available for G3; it does not complete target-subject visual analysis. A contact sheet or transcript cannot substitute for G3's multimodal visual-analysis manifest.

## Reference-media variant

For a style-only reference video, route analysis to G1 and write its manifest and derivatives only to `工作台/<projectId>/G1-创作方向/G1-参考视频分析/`. Include the source path, SHA-256, original timecodes, and `analysisOnly: true` in the G1 record. Do not add it to `G2-证据清单-v0.1.json`, cite it as fact evidence, reuse its transcript as output subtitles, or treat its media/audio/text/logo as an output asset.

Failure rules:

- Fail if a source SHA-256 differs from `material-pack.json`.
- Fail if generated artifacts would be written inside the source material pack.
- Fail if local transcription requires uploading media, cloud APIs, model downloads, or model-cache refreshes. If the controlled runtime or a cached model is missing, return `blocked` without attempting remediation.
- Fail if transcript timestamps are non-monotonic, overlapping, empty, or not tied to the original source asset.
- Warn, but do not fail, for burned-in subtitles, spoiler risk, low-confidence transcript terms, or source audio excluded from the final edit.
