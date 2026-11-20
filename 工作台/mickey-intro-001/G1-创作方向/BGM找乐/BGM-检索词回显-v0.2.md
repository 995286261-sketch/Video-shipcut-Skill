# BGM 检索词卡 v0.2

- 目录：netease｜分发边界：internal_test｜推导优先级：口头偏好 ＞ 主题翻译 ＞ 风格简报锚定
- 输入：偏好=无｜主题=米老鼠近百年演变：1928汽船威利黑白管弦 → 现代米奇妙妙屋｜简报=无｜时间线=120000ms

| # | 检索词 | 来源 | 推导依据 |
|---|---|---|---|
| 1 | happy orchestral adventure | theme | 受控词表 warm/orchestral+米老鼠黄金时代管弦乐拟像 |
| 2 | playful cartoon strings brass | theme | 受控词表 playful+体裁直译(第一轮 playful 标签实测多为 lo-fi/电子，改体裁词直取真卡通管弦) |
| 3 | upbeat warm cinematic comedy | theme | 快节奏+温馨+喜剧短片体裁 |

- 过滤推导：时长下限 120s（轨必须盖住成片）
- 纪律：词由 Agent 推导、脚本不编造曲库命中；改词=重跑本脚本；**检索词卡不设门禁口令**，真正的门禁是候选池上的「你挑一首」；网易云候选一律 uncleared-platform-catalog，试听件只用于选型。

- 机器合同：工作台/mickey-intro-001/G1-创作方向/BGM找乐/BGM-检索词-v0.2.json
- 消费：`music_search_netease.py --terms-file 工作台/mickey-intro-001/G1-创作方向/BGM找乐/BGM-检索词-v0.2.json`
