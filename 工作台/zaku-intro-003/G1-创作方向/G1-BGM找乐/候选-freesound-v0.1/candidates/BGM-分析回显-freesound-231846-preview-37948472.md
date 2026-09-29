# BGM 分析回显 — freesound-231846-preview.mp3

- 做了什么：ffmpeg 全量解码核验 → librosa 节奏/起音/能量分析 → ebur128 响度实测（版本 music-expert-analysis-v0.2）；同文件重跑命中缓存不重算
- 全局事实：0:11.761 ｜ 89.1 BPM（拍间隔中位 674ms）｜ 卡点 26（13 离拍重音 + 13 拍点） ｜ 积分响度 -14.5 LUFS
- 注：true peak 本次未测得（ebur128 输出缺项）；混音前如需限峰请另测

## 分段分析

此卡的数字与《BGM 分析报告》JSON 同源；"音乐结构/对剪辑的意义"两列为能量档位规则的机械草稿，供人工复核修正。

| 段 | 区间 | 能量 | 音乐结构 | 对剪辑的意义 |
|---|---|---|---|---|
| 1 | 0:00.000–0:07.523 | 0.088 | 开场·主高潮（全曲最高能量） | 高潮区：信息密度最高的画面、最快剪辑节奏放这里 |
| 2 | 0:07.616–0:11.703 | 0.006 | 尾段归零 | 尾段归零；成片淡出对齐本段起点最顺 |

结构读法：2 段，其中高能量段 1 个。单一高潮结构：高潮句用 --climax-sentence 交给对齐器即可。

## 产物

- 分析报告：`/Users/chuanzhangbigye/工作/MySpace/Video-shipcut Skill/工作台/zaku-intro-003/G1-创作方向/G1-BGM找乐/候选-freesound-v0.1/candidates/BGM-分析报告-freesound-231846-preview-37948472.json`
- 对齐（可选）：`music_align.py --report <本报告> …` 产出《BGM-对齐建议》与《BGM-对齐回显》
