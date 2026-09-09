# 曲库探测与选型结论（2026-09-08）

本文固定"找乐"来源的事实结论，防止将来凭印象重议。网络调研 + 本机 curl 探测双重取证。

## 分析引擎选型

| 库 | 结论 | 依据 |
| --- | --- | --- |
| **librosa** | ✅ 采用 | v1.0.0，ISC 许可证（与 AGPL 仓库兼容），最近发布 2026-08（活跃），Python ≥3.12 |
| aubio | ❌ | GPLv3+，PyPI 最后发布 2019，无 macOS arm64 wheel |
| madmom | ❌ | 研究向、依赖旧版、维护弱 |
| essentia | ❌ | AGPL + 需商业授权，构建重 |

托管运行时先例：仿 faster-whisper 用 uv venv(py3.12)+numpy+librosa 建独立运行时（当前开发机示例位置 `~/工作/WorkTool/music-expert/runtime`，**仅为示例，非合同**），经 `MUSIC_EXPERT_RUNTIME_HOME`（历史别名 `P0C_MUSIC_RUNTIME_HOME`）注入 sys.path；缺失结构化 `blocked`。所有音频先经 `ffmpeg → pcm_s16le wav` 解码再喂 librosa，彻底绕开 libsndfile 的 mp3 支持问题。

## 找乐来源探测

| 来源 | 官方 API | 音乐搜索 | 许可机器可读 | 本机可达 | 处置 |
| --- | --- | --- | --- | --- | --- |
| **Freesound** | ✅ apiv2 | ✅ 文本/标签/相似 | ✅ 每条带 license | ✅ 401(需 token,正常) | **自动轨道唯一来源** |
| Pixabay Music | ❌ | 仅图片/视频 API | 许可页动态 | 400 | **人工登记轨道** |
| Mixkit | ❌ | 无 | 许可在弹窗动态渲染 | 301 | **人工登记轨道** |
| FMA | 旧文档域名已失效 | ? | ? | 200(站点)/旧 API 不可解析 | 待议，非阻塞 |

## 结论：双轨（见 `sourcing-contract.md`）

1. **自动**：Freesound（有官方 API + 每声许可 + 可下载预览 + 服务器端声学相似检索），严格过滤到 CC0/CC-BY。
2. **人工**：Pixabay/Mixkit 音乐无可用 API 且许可不可机器审计 → 人在浏览器合法下载 + 抄录许可证据 → `music_register_candidate.py` 登记。
3. **不做**：爬站、音乐生成、FMA 大数据集下载。

红线：任何来源默认 `internal_test`；无许可证据链不进候选池；缺 token/网络失败一律 `blocked`，绝不静默换到无授权来源。
