# G4 Render and ChatCut Handoff Contract

Input: an `approved_for_g4` edit plan; registered local source, narration and music assets; export profile; target ChatCut project; and caller-owned workspace.

Output: G4 local rough-cut/final candidate, a manifest of independently editable video segments, narration and BGM source files, editable subtitle reference, cover candidates, render log, source-hash verification result, and (only when selected) the matching editable ChatCut timeline.

The default G4 output is local rendering. A ChatCut timeline is an optional branch for user-requested micro-adjustments; it is not required to route a validated local candidate to G5.

Write new-project local artifacts only to `G4_ROOT` defined in [Project Layout Contract](../../p0-c-pipeline/references/project-layout-contract.md); `work/` may hold disposable clips, concat lists and caches. Historical `工作区/剪辑方案/<projectId>/` is read-only compatibility input. Keep original media unchanged. A flattened MP4 is preview/QA only and must never be placed on the ChatCut target timeline.

Reject changed source hashes and unregistered music, fonts, reference-video assets or source audio that the plan excludes.

## v1.1 演示成片扩展字段

需要封面、旁白、章节卡或固定字幕时，G4 运行清单应增加以下字段：

```json
{
  "aspectRatioPolicy": "preserve_source",
  "explicitCanvas": null,
  "cleanMaster": true,
  "cover": {"enabled": true, "representativeFrameRef": "...", "durationSec": 3.5},
  "narration": {"timingSource": "rendered_sentence_audio", "voiceAssetRef": "..."},
  "captions": {"style": "fixed_bottom_band", "hideDuringChapterCards": true},
  "audio": {"duckBgmDuringNarration": true}
}
```

`explicitCanvas` 仅在 `aspectRatioPolicy: explicit` 时填写。`cleanMaster` 必须为 `true`；已烧录本轮字幕、章节卡或 CTA 的预览文件不得作为最终合成输入。完整质量规则见 [客户演示成片质量补丁](demo-quality-patch.md)。
