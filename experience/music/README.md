# 音乐经验库（experience/music）

跨项目的"我们验证过的曲子"档案。**唯一写入口是 `skill/music-expert/scripts/music_library.py`**（Agent 不手改 JSON，与 pipeline-state 同一纪律）。

## 身份与结构

一首歌一个目录：`tracks/<sha256 前 16 位>/`，身份 = 音频内容的 SHA-256（换名字、换来源、哪个项目发现的都不影响归并）。四层次序不可互相冒充：

| 文件 | 层 | 回答的问题 | 性质 |
|---|---|---|---|
| `track.json` | 身份卡 | 这是谁？什么许可？| 红绿灯所在，license 只升不降 |
| `acoustic.json` | 声学层 | 什么 BPM？高潮低谷在几分几秒？| 确定性分析产物，免费复用 |
| `listen.md` | 模型层 | 听起来是什么类型什么气质？| 听觉模型**绝对属性**笔记，带 `model/prompt` 版本戳，追加式 |
| `verdicts.jsonl` | 人证层 | 人怎么评价它？| append-only，用户原话，永不修改历史 |

`roles` 字段区分角色：`anchor`（用户确认过、可当风格参照）/`candidate`。风格锚不再单设库——锚就是档案的角色。

## 三条红线

1. **音频本体永不进库**。未清权试听件（`uncleared-platform-catalog`）的"日后复用"= 凭 `aliases.sourceUrl / neteaseId` 重新取回 + SHA 对身份卡验明正身；已清权文件是项目素材资产，`audioRefs` 只记指针。库里出现任何 mp3 即为事故。
2. **红灯跟着记录永生**：`query --project-boundary` 是任何项目引用前必做的动作；未清权 + 边界不符 = 🔴 不得使用。许可状态只能由 `grant`（真实登记证据）翻转，并自动记 `license_granted` 事件。
3. **相对评价不做库事实**："与某参照曲贴合 7.5/10" 依赖参照物，不入 `listen.md`（脚本硬拒）；绝对属性笔记带版本戳，换模型/升级提示词后旧笔记标过期、不冒充新结论；没真听过的歌，库里一个字都不写。

## 复用（读侧）

- 找乐：搜索前先 `query --match`，已建档的歌直接带出三层笔记；试听笔记层 `--library` 命中即零成本复用，只有没听过的才花钱听，听完自动写回。
- 定风格：`query --role anchor` 供 G1 选参照曲。
- 排卡点：`acoustic.json` 的 `climaxSegment/segments` 供 G3/G4 取时间戳。
