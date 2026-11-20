# BGM 检索词卡 v0.1

- 目录：freesound｜分发边界：internal_test｜推导优先级：口头偏好 ＞ 主题翻译 ＞ 风格简报锚定
- 输入：偏好=无｜主题=米老鼠98年进化介绍：从1928黑白蒸汽船到现代彩色树屋，温馨快节奏｜简报=无｜时间线=无

| # | 检索词 | 来源 | 推导依据 |
|---|---|---|---|
| 1 | upbeat playful synth | theme | 温馨快节奏（用户第4问原话）+介绍感开场 |
| 2 | electro swing happy | theme | 1928 时代梗×现代轻快（进化线方向卡） |
| 3 | warm cartoon pizzicato | theme | 卡通肢体幽默的弦乐拨奏质感（汽船威利画面气质） |

- 过滤推导：无
- 纪律：词由 Agent 推导、脚本不编造曲库命中；改词=重跑本脚本；**检索词卡不设门禁口令**，真正的门禁是候选池上的「你挑一首」；网易云候选一律 uncleared-platform-catalog，试听件只用于选型。

- 机器合同：工作台/mickey-intro-001/G1-创作方向/BGM找乐/BGM-检索词-v0.1.json
- 消费：`music_search_netease.py --terms-file 工作台/mickey-intro-001/G1-创作方向/BGM找乐/BGM-检索词-v0.1.json`
