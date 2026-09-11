# BGM 检索词卡 v0.1

- 目录：netease｜分发边界：internal_test｜推导优先级：口头偏好 ＞ 主题翻译 ＞ 风格简报锚定
- 输入：偏好=我这几个选项倾向于 史诗｜主题=/Users/chuanzhangbigye/工作/WorkSpace/N8-实测-tiger/direction-input-v0.1.json｜简报=/Users/chuanzhangbigye/工作/WorkSpace/N8-实测-tiger/工作台/tiger-intro-001/G1-创作方向/G1-音乐检索/../G1-参考视频分析/BGM-风格简报-冷战奇迹-v0.1.json｜时间线=120000ms

| # | 检索词 | 来源 | 推导依据 |
|---|---|---|---|
| 1 | 史诗 电子 | theme | 用户偏好原词'史诗'＋参考曲模型试听笔记判定曲风为工业 techno（电子） |
| 2 | 工业 电子 | theme | 参考曲绝对笔记原话'工业 techno（Industrial Techno）' |
| 3 | 硬核 节奏 | theme | 笔记原话'冷峻、机械、充满压迫感与驱动力''适合硬核科幻战争快节奏混剪' |
| 4 | 鼓机 合成器 | theme | 笔记原话'失真底鼓、金属打击乐、合成器脉冲贝斯' |

- 过滤推导：时长下限 120s（轨必须盖住成片）；BPM 111–135（简报锚定，进推荐打分）
- 纪律：词由 Agent 推导、脚本不编造曲库命中；改词=重跑本脚本；**检索词卡不设门禁口令**，真正的门禁是候选池上的「你挑一首」；网易云候选一律 uncleared-platform-catalog，试听件只用于选型。

- 机器合同：/Users/chuanzhangbigye/工作/WorkSpace/N8-实测-tiger/工作台/tiger-intro-001/G1-创作方向/G1-音乐检索/BGM-检索词-v0.1.json
- 消费：`music_search_netease.py --terms-file /Users/chuanzhangbigye/工作/WorkSpace/N8-实测-tiger/工作台/tiger-intro-001/G1-创作方向/G1-音乐检索/BGM-检索词-v0.1.json`
