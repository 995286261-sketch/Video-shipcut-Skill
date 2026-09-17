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

### 图形文字字体红线（N8 ㉛）

`fontFile` 直接喂 `drawtext` 的路线（章节卡、顶部标题栏、封面标题）有一个静默陷阱：**TTC 字体集合里 drawtext 只渲染第一个 face**。活测：`/System/Library/Fonts/PingFang.ttc` 首 face 不含简体「战/场/对/手/队」等字形，渲成豆腐块且 ffmpeg 退出码照常是 0；同字体同文字走 libass（`subtitles` 滤镜）完全正常。因此 `g4_assemble` 在三条 drawtext 路线进入 ffmpeg 之前做字形覆盖预检（纯 stdlib 解析 cmap，逐 face 计算码位覆盖）：任何字符在所有 face 里都没有 → blocked；只有后面的 face 有 → 同样 blocked 并提示 TTC 首-face 陷阱。合同口径：优先为图形文字选**单 face 的 .ttf/.otf**；确实只有 ttc 可用时，改走 libass 烧录路线（字幕布局合同同款）。预检失败属于 blocked，不是 warning，不得 `--force` 绕过。
