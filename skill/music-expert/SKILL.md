---
name: music-expert
description: 对音乐做确定性分析与授权化找乐：分析任意音频或参考视频音轨的 BPM、节拍、起音、卡点表、能量分段与响度，产出可复用的分析报告和风格简报；并从公开音乐库找候选，Freesound 走自动检索、Pixabay/Mixkit 走人工下载加许可证据登记，每条候选都带完整授权与解码探针链。适用于需要理解或获取背景音乐风格的场景；不负责素材包整理、剪辑决策、渲染、QA 或交付，也不接入六节点管线的门禁。
metadata:
  pipelineNode: support
---

# BGM 专家（music-expert）

覆盖基线总账 ⑫（缺 BGM 内容/节奏分析）与"AI 自动找 BGM"的确定性前置，把过去只能靠运行时临场发挥的音乐能力沉淀为可复现、可审计的本地引擎。本 Skill 是**独立 support 组件**，不改六节点管线，只把对外合同定义到将来可直接接入 G0/G3/G5 的程度。范围三块：确定性分析引擎、找乐双轨、需求打分推荐。

合同先行：动手前读 `references/music-analysis-contract.md`、`references/sourcing-contract.md`、`references/style-brief-contract.md`；来源选型的实测证据在 `references/library-probes.md`。

## 执行入口（唯一）

- 分析：`scripts/music_analyze.py`。找乐自动轨道：`scripts/music_search_freesound.py`。找乐人工轨道：`scripts/music_register_candidate.py`。推荐排序：`scripts/music_recommend.py`。不要用临时脚本或手敲 ffmpeg 替代。

## 前置依赖

- `ffmpeg`/`ffprobe` 在 PATH。
- 节奏/能量分析库（numpy、librosa）只能从托管运行时 `P0C_MUSIC_RUNTIME_HOME` 加载；缺失即结构化 `blocked`，禁止运行时下载或 pip 安装（与 faster-whisper 同一纪律）。
- Freesound 自动检索需 `P0C_FREESOUND_TOKEN`；缺失即 `blocked`，不静默换到无授权来源。

## 工作流

1. 要理解一段音乐或某个参考视频的配乐感觉 → `music_analyze.py --input <文件> --output-dir <目录>`，需要风格简报再加 `--style-brief-out`。重跑同文件同版本命中 `cache_hit` 不重算。
2. 要自动找候选 → `music_search_freesound.py --query/--tags/--similar-to ... --output-dir <目录>`，得到带授权证据链的候选清单。
3. 用户手动从 Pixabay/Mixkit 等无 API 站下载了音乐 → `music_register_candidate.py --audio <文件> --license-type ... --license-evidence ... --output-dir <目录>` 登记（本脚本不联网、不复制源文件）。
4. 有需求画像（时长/BPM/能量/响度上限）或风格简报后 → `music_recommend.py --profile <画像.json> --candidates <候选清单...> --reports-dir <分析目录>` 打分排序；候选不足会显式报"补检索/放宽画像/缩短成品"三选一，不自行拼凑。

## 边界与红线

- 源素材只读：分析不修改输入，产物只写显式输出目录。
- 授权不可含糊：没有许可证据链的音乐不进候选池；默认 `internal_test`，上调需人工复核许可条款。
- 不越界：不执行 G0 素材包登记、不做剪辑决策、不渲染、不做 QA/交付；这些属于对应节点 Skill。

## Pipeline Integration

本 Skill 不读写 `工作台/<projectId>/pipeline-state.json`，不推进任何节点，不登记门禁收据。将来与管线的接缝（G0 `use_library_later` 调检索、G3 引用卡点表、G5 审计许可）另起批次，通过 specialist SKILL 的引用接入，而非把逻辑塞进本 Skill 或节点脚本。

## 标准产物

- `BGM-分析报告-*.json`、`BGM-风格简报-*.json`
- `BGM-候选清单-freesound-*.json`、`BGM-候选登记-*.json`
- `BGM-推荐-*.json`

## 故障处理

所有脚本以结构化 JSON 到 stdout：退出码 0=成功/复用、2=输入非法或依赖/授权被拦、1=运行时失败。缺 ffmpeg、缺分析运行时、缺 Freesound token 均为 `blocked`，错误信息指明缺哪个受控依赖及其声明变量；不得回退到下载、爬站或无授权来源。

## 资源

- `SKILL.md`：本使用合同。
- `agents/openai.yaml`：平台卡片。
- `references/music-analysis-contract.md`：分析报告与 cacheKey 合同。
- `references/sourcing-contract.md`：双轨找乐与授权证据合同。
- `references/style-brief-contract.md`：参考视频→风格简报合同。
- `references/library-probes.md`：曲库与引擎选型实测结论。
- `scripts/music_analyze.py`、`scripts/music_search_freesound.py`、`scripts/music_register_candidate.py`、`scripts/music_recommend.py`：四个唯一入口。
- `tests/test_music_analyze.py`、`tests/test_music_sourcing.py`：确定性与阻断回归。
