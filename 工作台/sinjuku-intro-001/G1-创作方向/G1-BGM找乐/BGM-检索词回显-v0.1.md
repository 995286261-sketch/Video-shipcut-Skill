# BGM 检索词卡 v0.1

- 目录：freesound｜分发边界：internal_test｜推导优先级：口头偏好 ＞ 主题翻译 ＞ 风格简报锚定
- 输入：偏好=BGM的话你从 freesound 找（通道偏好，非风格偏好）｜主题=新安洲——红色彗星的再临，UC 末期夏亚定制机，快节奏混剪科普，机械史诗感｜简报=工作台/sinjuku-intro-001/G1-创作方向/G1-参考视频分析/BGM-风格简报-冷战奇迹-v0.1.json｜时间线=180000ms

| # | 检索词 | 来源 | 推导依据 |
|---|---|---|---|
| 1 | epic orchestral | brief | 参考片音轨实测为管弦+电子高能量（风格简报锚 123BPM），题材为机动战士史诗 |
| 2 | cinematic dramatic | theme | 介绍片叙事张力需求（coreViewpoint：承载传说的名机） |
| 3 | action trailer | theme | 快节奏混剪科普风格规则（镜头约3秒） |
| 4 | dark intense | theme | 夏亚/吉翁线的压迫感情绪，来自题材 |

- 过滤推导：时长下限 180s（轨必须盖住成片）；BPM 111–135（简报锚定，进推荐打分）
- 纪律：词由 Agent 推导、脚本不编造曲库命中；改词=重跑本脚本；**检索词卡不设门禁口令**，真正的门禁是候选池上的「你挑一首」；网易云候选一律 uncleared-platform-catalog，试听件只用于选型。

- 机器合同：工作台/sinjuku-intro-001/G1-创作方向/G1-BGM找乐/BGM-检索词-v0.1.json
- 消费：`music_search_netease.py --terms-file 工作台/sinjuku-intro-001/G1-创作方向/G1-BGM找乐/BGM-检索词-v0.1.json`
