# 变更记录

## v1.1.0 — 2026-09-04

将 leader 审阅后的 P0-C v1.1.0 交付补丁合回主仓，并统一命名。补丁内容源自 TASK-050"上能同创智能剪辑 Demo"的实际渲染与人工评审。

### 命名统一

- 产品名 Video-shipcut → P0-C；编排入口 Skill `video-shipcut-pipeline` → `p0-c-pipeline`（目录与 `$` 调用名同步）。
- 环境变量前缀 `SHIPCUT_*` → `P0C_*`。
- 根文档（AGENTS、PRD、README、目录规范、历史调研）与流程图同步更名；流程图改用 SVG 作为 README 主图，旧 PNG（含旧名称，无法从 SVG 无损再生）移除，可从 git 历史找回。

### 工具链跨平台

- 运行依赖从"仅 Windows + `D:\WorkTool`"改为 macOS/Windows/Linux 通用：优先从 `PATH` 解析 FFmpeg/Python，`P0C_*` 变量为可选覆盖。
- Python 最低版本明确为 3.10（脚本使用 PEP 604 联合类型语法），推荐 3.12。
- 测试在缺少 FFmpeg 时优雅跳过（`test_engine_cli.py`）。

### G4 成片质量补丁（本次核心）

- 新增 `skill/local-video-render/references/demo-quality-patch.md`：画幅策略、clean master 不变量、封面、章节卡节奏、句子级旁白、字幕对齐实际音频、分轨与 ducking、清晰度、授权记录、机器/人工 QA。
- `render-contract.md` 增加 v1.1 扩展字段（`aspectRatioPolicy`、`cover`、`narration`、`captions`、`audio` 等），示例见 `examples/g4-render-profile.example.json`。
- `g4_render.py`：默认 `preserve_source`，用 ffprobe 从首个批准源探测画幅；`explicit` 必须同时给宽高；`--crop-bottom-ratio` 默认从 0.14 改为 0。
- `g4_validate.py`：宽高改为可选，未指定时自动检测分段画幅一致性。
- 新增 `tests/test_g4_render_profile.py`。

### 上下游合同传导

- G3（`video-edit-plan`）：含封面/章节卡/旁白/固定字幕的项目，计划必须预登记画幅策略、封面帧、句子边界、字幕样式、ducking 策略与 clean master 输入，否则保持 `review_required`。
- G5（`media-qa-delivery`）：demo-quality-patch 的机器 QA 与人工 QA 纳入交付门禁，缺任一必需证据不得报告完成。

## v0.1 — 2026-09-04

初始发布：G0–G5 六节点流水线 Skill 与示例项目 `unicorn-gundam-intro-001`。
