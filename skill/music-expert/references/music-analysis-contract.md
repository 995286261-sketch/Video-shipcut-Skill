# BGM 音乐分析合同

`scripts/music_analyze.py` 是本 Skill 分析能力的唯一入口。它把一段音乐（或参考视频里的音轨）转成确定性的《BGM 分析报告》，供检索、推荐和 G3 卡点表使用。分析不改变任何源素材（只读）；产物写入显式 `--output-dir`。

## 唯一入口与依赖

- 音频解码：`ffmpeg`/`ffprobe`（PATH）。
- 节奏/能量分析库（numpy、librosa）：只能从托管运行时加载，路径由环境变量 `MUSIC_EXPERT_RUNTIME_HOME` 声明（历史别名 `P0C_MUSIC_RUNTIME_HOME`）。缺失时返回结构化 `blocked`，**禁止在运行时 pip 安装或下载**。
- 输入没有音频轨（例如纯画面视频）返回 `invalid`；无法解码返回 `blocked`（与 G0 ㉓ 同一根因防线：流媒体加密缓存改名的假文件在此也会被拦下）。

## cacheKey 与复用

报告带 `cacheKey`：

```json
{"sha256": "<源文件字节 SHA-256>", "analysisVersion": "music-expert-analysis-v0.2", "sampleRate": 22050, "mediaKind": "audio|video-with-audio"}
```

- `analysisVersion` 每次报告输出语义变化必须升号（v0.2 修正了 ebur128 响度误读哨兵值 -70 的问题）；旧 v0.1 报告因版本不同不会被复用，避免错值串档。

- 重跑同一文件、同版本、同参数：输出目录或 `--cache-root` 中已有相同 cacheKey 的报告即 `status: cache_hit` 直接返回，不重新计算。
- 参数或 `analysisVersion` 变化 → 生成新报告文件，旧报告保留可追溯。
- `analysisVersion` 只有在 DSP 参数或模型实质变化时才允许升号；禁止像基线时期那样用版本号变通制造重算。

## 报告字段（整数毫秒为唯一机器真相）

| 字段 | 含义 |
| --- | --- |
| `source.*` | 路径、SHA-256、`mediaKind`、探测/实测时长（`decodedDurationMs` 以解码样本为准） |
| `tempoBpm` | 节拍跟踪得到的 BPM |
| `beatsMs[]` | 拍点毫秒序列 |
| `onsetsMs[]` | 起音点毫秒序列 |
| `hitPoints[]` | **卡点表**：拍点为 `beat`，偏离最近拍点 >120ms 的起音为 `accent`，供 G3 剪辑对齐 |
| `energySegments[]` | 能量分段 `startMs/endMs/energyMean`（贪心变化点切分，无聚类依赖） |
| `energyCurve[]` | 粗采样能量曲线，用于风格相似度 |
| `loudness` | ffmpeg `ebur128`：`integratedLufs`、`loudnessRangeLu`、`truePeakDbtp`（口播 ducking 余量评估） |

## 风格简报（`--style-brief-out`）

生成参考音乐→检索条件的《风格简报》：`bpmRange`（±10%）、归一化 `energyShape`、`segmentCount`、`suggestedQueryTerms`（机器事实之外的检索词由 Agent 依情绪补写，简报本身不编造曲库结果）。它是 `music_recommend.py --profile` 与 `music_search_freesound.py --similar-to` 的上游输入。

## 落盘核验

分析报告、风格简报、候选清单写入后必须核验"文件存在且非空"，否则 `blocked`——与基线 ㉒ 修复同一规则，杜绝"退出 0 但没产物"的静默成功。
