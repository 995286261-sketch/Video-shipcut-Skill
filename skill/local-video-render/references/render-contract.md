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

### 转场执行（transition-expert 指令消费，批②）

批准计划含转场（段带 `transitionInstruction`≠硬切）时，G4 **必须**携带 `skill/transition-expert/scripts/transition_directive.py` 产出的《G4-转场执行指令》跑 `g4_prepare --transition-directive`，否则 prepare 拒办——绝不静默丢弃批准的转场（挂空合同教训）。三脚本分工：prepare 绑定指令三哈希并把每段 `headExtraMs/tailExtraMs` 透传进段清单（timeline 游标不动，网格权威）；render 按 extra 扩切段文件（-ss 前移 head、-t 覆盖网格+两侧手柄，起点为负即拒办）；assemble 加载即对账（指令哈希新鲜、网格相等、段文件确已扩切），有边界时逐段 `-i` + 链式 `xfade`/`concat`，成片总长==批准网格（重叠吃掉的就是手柄），无转场项目走 concat demuxer 旧路径产物逐字节不变。装配记录登记 `transitionDirective` 块与含 xfade 的 `filterGraph`，供专员 `transition_report.py` 复检出 `transition-audit.json`（G5 REQUIRED）。窗口/手柄/词表规则全在 `skill/transition-expert/references/transition-contract.md`，G4 只执行不决策。

### 封面合同（⑫ 登记件机抽帧）

`--cover` 合同 JSON 的字段：`materialPack`（`material-pack.json` 路径）、`sourceAssetId`、`sourceMs`（**源资产内毫秒**，三者必填）、`fontFile`、`title`、`output`（可选 `fontsize/marginY/fontcolor/sourceTimelineMs/note`）。装配器按登记件解析**精确路径**→ 对在册 `sha256` 逐字验明正身 → `ffmpeg -ss` 机抽帧 → 叠标题；`sourceMs` 超出该登记资产时长（ffprobe 实测）当场拒。装配记录落 `coverProvenance`（assetId、资产路径与在册哈希、sourceMs、帧文件路径、帧 sha256；`sourceTimelineMs` 给出成片时间线对应时点作披露）。

**红线（zaku-003 台账⑫）**：`imagePath` 通道已退役——合同里出现即罢工。事故根因是编排方自行选帧文件：shell 通配 fallback 误抓 `05_风格参考/` 的参考片 mp4 抽帧，参考片画面险成封面（参考视频画面不得入成片），全靠目检拦下。现在时点与身份都来自批准计划/G3 封面指令（`assetId`+源内毫秒），路径由装配器从登记件反查，登记件之外的画面（含参考片）结构上进不来；`relativePath` 猜路径、`find | head -1` 之类通配选源自此非法。若日后需要成片之外的画面做封面，只能走另一条**已登记**素材通道并同批对账，不在本合同开口子。

### 图形文字字体红线（N8 ㉛）

`fontFile` 直接喂 `drawtext` 的路线（章节卡、顶部标题栏、封面标题）有一个静默陷阱：**TTC 字体集合里 drawtext 只渲染第一个 face**。活测：`/System/Library/Fonts/PingFang.ttc` 首 face 不含简体「战/场/对/手/队」等字形，渲成豆腐块且 ffmpeg 退出码照常是 0；同字体同文字走 libass（`subtitles` 滤镜）完全正常。因此 `g4_assemble` 在三条 drawtext 路线进入 ffmpeg 之前做字形覆盖预检（纯 stdlib 解析 cmap，逐 face 计算码位覆盖）：任何字符在所有 face 里都没有 → blocked；只有后面的 face 有 → 同样 blocked 并提示 TTC 首-face 陷阱。合同口径：优先为图形文字选**单 face 的 .ttf/.otf**；确实只有 ttc 可用时，改走 libass 烧录路线（字幕布局合同同款）。预检失败属于 blocked，不是 warning，不得 `--force` 绕过。
