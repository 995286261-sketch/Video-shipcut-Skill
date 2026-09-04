---
name: long-video-local-edit
description: 仅为已知历史项目提供显式兼容检查。新 P0-C 项目不得使用本 Skill，而由 p0-c-pipeline 路由至当前 G4/G5 Skills。
metadata:
  pipelineNode: support
---

# 本地长视频剪辑总调度

本 Skill 是已弃用的 support 兼容运行时，不是独立流水线节点，也不得作为新项目剪辑或渲染入口。新项目必须使用 `$p0-c-pipeline` 路由的 `local-video-render` 与 `media-qa-delivery`。它仅可在用户明确指定的历史兼容检查中使用；归档目录不得读取，原始媒体只读。

## Pipeline Boundary

`$p0-c-pipeline` owns cross-node routing and project approval state. This skill provides local editing rules and runtime checks only; when pipeline state exists, read it and do not advance a project across nodes.

## 前置条件

1. 媒体操作前先执行 `doctor`。
2. 读取 `references/local-toolchain.md`，确认本地共享工具链，不要重复下载工具。
3. 生产前调用 `$material-pack-intake`，只接收 `material-pack.json` 校验通过的素材包。
4. 先读取 `references/artifact-registry.md` 与 `工作台/<projectId>/pipeline-state.json`。不得读取或写入归档、旧 `run-manifest.json`；本 Skill 不是状态入口。
5. 请求必须含 `schemaVersion: "0.1"`、`operation: "media.edit.plan"`、`requestId`、`projectId`、`editPrompt` 和已登记哈希的本地 `sourceAssets`。
6. 只使用用户授权的源素材；参考视频不能作为输出素材。
7. 生成或适配请求时读取 `references/contract.md`。
8. 涉及“参考口播稿 + 自有资料 → 原创口播稿”时，先完成 `$media-evidence-prep` 的 G2 脚本创作与事实审核门禁；只有 `approved_for_g3` 的稿件可进入镜头与音频计划。
9. G3 开始前必须读取 G2 审核决定中的 `approvedNarrationRef`，并将该路径登记为编辑计划的唯一 `narrationDraft` 输入。禁止根据文件名、最近修改时间或聊天上下文猜测最新口播稿；候选稿、创作稿、旧版稿和 `supersededDraftRefs` 中的稿件必须拦截，不得进入镜头绑定。

## 工作流

### G3 口播来源强制门禁

进入 G3 时执行以下顺序：

1. 读取项目 `pipeline-state.json`。
2. 读取 G2 审核决定 JSON。
3. 解析 `approvedNarrationRef`、`voiceBriefRef`、`factCitationRef` 和 `status`。
4. 只有 `status` 明确允许进入 G3 且 `approvedNarrationRef` 存在时，才可生成编辑计划。
5. 对照 `supersededDraftRefs` 和项目内候选稿列表；若编辑计划引用其中任一文件，必须失败并要求人工确认。
6. 在计划中保存完整的口播来源路径、版本标识和审核决定路径，禁止只保存模糊的“最新稿”。

如果用户在 G3 阶段指定了另一份口播稿，必须暂停镜头绑定，回到 G2 重新确认该稿的事实/声音状态；不得在 G3 静默替换。

### G3 人工交互门禁

G3 先一次性展示完整、连续、无重叠的时间线，包含原片时间码、对应口播章节、实际画面观察、烧录字幕风险和剧情风险。用户整体确认，或按 `segmentId` 指出局部保留、删除、替换或待定；反馈写入计划级 `humanReviewFeedback` 与 `timelineReview`。在一次计划确认和人工批准前保持 `status: review_required`，只有批准后才可进入 G4。

使用受控 Python 运行时，将 `<request>` 和 `<workspace>` 替换为绝对路径：

```powershell
python scripts/local_edit_engine.py doctor
python scripts/local_edit_engine.py plan --request <request> --workspace <workspace>
```

事实依据视频没有字幕流时，调用 `$media-evidence-prep`。本 Skill 不再拥有转写脚本或转写产物脚本。

展示 `segments`、理由、警告和 `humanReviewPoints`。`status: review_required` 的计划可以使用，但未经确认不得渲染。

```powershell
python scripts/local_edit_engine.py approve --plan <workspace>/plan-result.json --reviewer <reviewer> --output <workspace>/approved-plan.json
python scripts/local_edit_engine.py render --plan <workspace>/approved-plan.json --workspace <workspace>
python scripts/local_edit_engine.py qa --plan <workspace>/approved-plan.json --artifact <workspace>/renders/final.mp4
```

## 当前 MVP 边界

- 仅渲染 16:9、H.264 MP4，排除源音频；配音和 BGM 由当前 G4 Skill 负责。
- `selectionHints` 仅用于 fixture 或人工给定的计划，必须标为人工证据。
- 没有本地语义证据或已确认 `selectionHints` 时返回 `insufficient_material`。
- 当前不包含字幕、TTS、生成式文案、未授权音乐、任意平台预设和云端转写。
- 黑帧和静音检查在检测器实现前只能标为警告，不能报告为通过。
- 批准前读取 `editPlan.qualityPolicy`，确认视觉焦点、叠层安全、证据字幕和切点音频连续性要求。

## 安全规则

- 规划前和渲染前均校验每个源文件的 SHA-256。
- 源时间轴与输出时间轴必须分离：`segments` 使用源 `startMs/endMs`，`editPlan.timeline` 使用输出 `outputStartMs/outputEndMs`。
- 不渲染未批准的计划，也不在源文件变化后静默替换镜头。
- 不编造字幕、产品承诺、音乐权利、品牌批准或人工批准。

## 资源

- `scripts/local_edit_engine.py`：确定性 CLI 剪辑引擎。
- `scripts/validate_asset_library.py`：校验可选音乐、音效、字体和动效预设。
- `config/default-horizontal-explainer-v1.json`：默认视觉策略，可由调用方配置覆盖。
- `references/contract.md`：请求、响应、状态和证据规则。
- `references/local-toolchain.md`：共享 Windows 工具路径与检查方法。
- `references/module-map.md`：子 Skill 所有权和实现状态。
- `references/asset-library.md`：复用资产登记和选择规则。
- `assets/asset-library/manifest.json`：内置资产目录。
