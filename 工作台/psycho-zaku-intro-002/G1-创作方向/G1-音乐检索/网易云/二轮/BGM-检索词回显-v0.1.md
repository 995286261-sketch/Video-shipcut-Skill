# BGM 检索词卡 v0.1

- 目录：netease｜分发边界：internal_test｜推导优先级：口头偏好 ＞ 主题翻译 ＞ 风格简报锚定
- 输入：偏好=背景音乐你从 freesound 里找好了（Freesound 整轨供给不足，供给面卡片呈报）｜主题=工作台/psycho-zaku-intro-002/G1-创作方向/G1-方向输入-v0.1.json｜简报=工作台/psycho-zaku-intro-002/G1-创作方向/G1-参考视频分析/BGM-风格简报-冷战奇迹-v0.1.json｜时间线=300000ms

| # | 检索词 | 来源 | 推导依据 |
|---|---|---|---|
| 1 | 工业电子 | theme | 笔记原话：参照曲实测为快节奏工业电子/Techno（模型听觉笔记） |
| 2 | 硬核 Techno | brief | 笔记原话：参照曲为硬核Techno、快节奏高能量 |
| 3 | 机械感 电子 | theme | 笔记原话：参照曲具强烈机械感（题材=机甲契合） |
| 4 | 紧张 电子鼓点 | theme | 笔记原话：紧迫叙事性+节奏驱动 |
| 5 | 战斗 电子 BGM | theme | 主题：UC末期战场叙事的平台语汇 |

- 过滤推导：时长下限 300s（轨必须盖住成片）；BPM 111–135（简报锚定，进推荐打分）
- 纪律：词由 Agent 推导、脚本不编造曲库命中；改词=重跑本脚本；**检索词卡不设门禁口令**，真正的门禁是候选池上的「你挑一首」；网易云候选一律 uncleared-platform-catalog，试听件只用于选型。

- 机器合同：工作台/psycho-zaku-intro-002/G1-创作方向/G1-音乐检索/网易云/二轮/BGM-检索词-v0.1.json
- 消费：`music_search_netease.py --terms-file 工作台/psycho-zaku-intro-002/G1-创作方向/G1-音乐检索/网易云/二轮/BGM-检索词-v0.1.json`
