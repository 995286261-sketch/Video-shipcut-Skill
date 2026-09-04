# Contract Reference

Use `sourceAssets` as the engine's internal multi-video representation. Each item requires `assetId`, `sourceKind: local-file`, `sourceValue`, and `sha256`. The company adapter remains responsible for reconciling its single `sourceAsset` field with this representation.

The plan response contains `sourceProbe`, `segments`, `editPlan`, `artifacts`, `qaReport`, `humanReviewPoints`, `evidenceRefs`, `warnings`, `status`, and `finishedAt`.

- `Segment.startMs/endMs` always reference the original asset.
- `editPlan.timeline.outputStartMs/outputEndMs` always reference the final video.
- `review_required` means a usable plan needs human approval.
- `insufficient_material` means evidence cannot support a relevant plan; do not render a substitute.
- `failed` means a probe, hash, contract, render, or QA failure; include the failure stage.
- `completed` means an operation completed. Human approval is stored in `editPlan.approvalState`, not inferred from `status`.

For a pre-transcription fixture, use explicit `selectionHints` with an evidence-backed `reason`. Production requests must replace these hints with local transcript/model evidence before automatic selection is claimed.
