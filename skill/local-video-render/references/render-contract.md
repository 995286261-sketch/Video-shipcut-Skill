# G4 Render and ChatCut Handoff Contract

Input: an `approved_for_g4` edit plan; registered local source, narration and music assets; export profile; target ChatCut project; and caller-owned workspace.

Output: G4 local rough-cut/final candidate, a manifest of independently editable video segments, narration and BGM source files, editable subtitle reference, cover candidates, render log, source-hash verification result, and (only when selected) the matching editable ChatCut timeline.

The default G4 output is local rendering. A ChatCut timeline is an optional branch for user-requested micro-adjustments; it is not required to route a validated local candidate to G5.

Write new-project local artifacts only to `G4_ROOT` defined in [Project Layout Contract](../../video-shipcut-pipeline/references/project-layout-contract.md); `work/` may hold disposable clips, concat lists and caches. Historical `工作区/剪辑方案/<projectId>/` is read-only compatibility input. Keep original media unchanged. A flattened MP4 is preview/QA only and must never be placed on the ChatCut target timeline.

Reject changed source hashes and unregistered music, fonts, reference-video assets or source audio that the plan excludes.
