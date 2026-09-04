# G1 创作方向引导

## 开始前

必须先取得素材包根路径并运行 `g1_direction.py check-pack --pack <路径>`。只有 `status: complete` 才能继续。任何其他结果都只报告 `blockers`，不提问、不生成候选、不写文件。

`projectId` 优先使用调用方提供的受控 ID；缺失时单独询问。只允许 `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`。默认禁止覆盖现有 `创作方向/<projectId>/`；需要新版本时，经用户确认使用 `write --on-conflict version`。

## 对话顺序

G1 继承 G0 已收集的信息（受众、平台、风格、BGM），只补充 G0 没问的。先按 `g1-choice-cards.md` 提供标题候选、叙事角度选择卡，然后收集事实主张和表达边界。

一次推进一个决策主题；同一主题内允许结构化子项。

1. **参考视频分析**（如果有）：

   **(a) 缓存检查**：先检查项目工作台 `工作台/<projectId>/G1-创作方向/G1-参考视频分析/` 下的唯一 `reference-analysis-manifest*.json`。先比较源文件 SHA-256、分析范围、采样配置、provider、model、promptVersion；命中则读取清单及其 canonical 派生产物，禁止重复全片分析。无缓存命中时才使用已配置且获准的多模态视觉分析适配器。不得向原始参考视频目录写回生成物。

   **(b) 场景检测（零 Token）**：用 ffmpeg 的 scene filter 检测场景切换点：
   ```bash
   ffmpeg -i <参考视频> -vf "select='gt(scene,0.3)',showinfo" -f null -
   ```
   解析输出得到每个场景的起始时间戳。

   **(c) 逐场景内容分析（多模态适配器）**：对每个场景取起点帧，用结构化 prompt 让已配置且获准的多模态视觉分析适配器输出 JSON：
   ```json
   {
     "scene": "画面内容一句话描述",
     "text_elements": [
       {"content": "...", "position": "top-center", "style": "白色粗体大号", "animation": "static/fade-in/typewriter"}
     ],
     "camera_motion": "static/zoom-in/pan-left/shake/...",
     "info_layers": "标题栏 + 字幕 + 徽章 共N层"
   }
   ```

   **(d) 转场分析（多模态适配器）**：将场景 N 的终点帧和场景 N+1 的起点帧拼成一张图，由已配置且获准的多模态视觉分析适配器判断转场类型（硬切/溶解/擦除/其他）。

   **(e) 产物保存**：
   - 只在项目工作台保存唯一 `reference-analysis-manifest-v<version>.json`，并由它引用结构化报告、场景时间码、关键帧和转场拼接图。
   - 技术报告、关键帧和拼接图均为 manifest 的派生产物，全部留在 `工作台/<projectId>/G1-创作方向/G1-参考视频分析/`。不得向源片目录、全局目录或归档目录双写缓存。

   回显时展示报告路径、场景数量、转场类型分布和关键文字样式摘要。
2. **标题**：基于素材包和 G0 摘要给 2-3 个候选。每个候选标注 `editorial_expression`、`factual_claim` 或 `mixed`。
3. **叙事角度**：根据项目类型生成 3 个推荐角度 + 1 个自定义。用户选一个。
4. **事实主张**：列出视频中要陈述的关键事实，标注 `supported`（有证据）或 `pending`（待补）。
5. **表达边界**：禁用表达、剧透范围、必须出现的信息。
6. **回显摘要**：只展示 G1 新增的信息，继承自 G0 的信息简要列出。等待用户明确确认。

## 继承自 G0 的信息

以下字段直接从 `01_需求说明.md` 读取，不再重复询问：
- `audience`：给谁看
- `outputPreferences.aspectRatio`：画幅（从平台推导）
- `outputPreferences.targetDurationSec`：时长（从平台推导）
- `outputPreferences.usagePurpose`：用途（从平台推导）
- `styleRules`：风格关键词
- `bgmDecision`：BGM 选择
- BGM 文件路径和使用范围

## 机器输入

最小 JSON：

```json
{
  "projectId": "demo-001",
  "coreQuestion": "这条片要回答的问题",
  "audience": "目标观众（继承自 G0）",
  "title": "标题",
  "titleExpressionType": "editorial_expression",
  "coreViewpoint": "核心观点",
  "outputPreferences": {"aspectRatio": "16:9", "targetDurationSec": [90, 120], "usagePurpose": "brand_homepage"},
  "bgmDecision": "use_library_later",
  "directionChoice": {"id": "recommended-1", "label": "专业可信的品牌第一印象", "source": "agent_recommendation"},
  "styleRules": ["只借鉴抽象节奏"],
  "expressionBoundaries": ["不使用未经证实的排名"],
  "claims": [
    {
      "claimId": "claim-001",
      "text": "需要在口播中陈述的事实",
      "status": "supported",
      "evidenceRefs": [{"path": "03_事实依据/source.pdf", "locator": "p.3"}]
    }
  ]
}
```

`supported` 必须至少有一条存在于素材包 `03_事实依据/` 下的证据路径和定位信息。`pending` 可没有证据，但在简报中必须明确为"待补事实"，不可被视为已确认事实。用户确认标题不等于事实核验。

`coreQuestion`、`audience`、`coreViewpoint`、`outputPreferences`、`styleRules` 和 `expressionBoundaries` 为必填。`outputPreferences` 必须是对象，且包含非空 `aspectRatio` 与正秒数（或两个递增正秒数）`targetDurationSec`；新项目还必须带非空 `usagePurpose`。`bgmDecision` 必须为 `provided`、`use_library_later` 或 `no_bgm`。`directionChoice` 必须记录选中的方向卡；自定义方向使用 `source: custom`。`styleRules`、`expressionBoundaries` 和 `claims` 必须为数组；没有额外规则时必须显式传入 `[]`，不能省略字段。任何通过 `validate` 的输入都必须可安全写入简报。

## 写入条件与产物

先运行 `validate`，再向用户回显摘要。只有获得明确确认后才运行 `write --confirmed`。产物为：

- `创作方向/<projectId>/G1-方向简报.md`
- `创作方向/<projectId>/G1-方向简报.json`

简报必须含有"事实主张与证据引用"表，逐条记录 `claimId`、文本、状态、素材包相对路径和页码/时间码等定位信息。
