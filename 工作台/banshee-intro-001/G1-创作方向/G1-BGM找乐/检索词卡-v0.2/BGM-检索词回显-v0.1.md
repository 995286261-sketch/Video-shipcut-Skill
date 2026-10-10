# BGM 检索词卡 v0.1

- 目录：netease｜分发边界：internal_test｜推导优先级：口头偏好 ＞ 主题翻译 ＞ 风格简报锚定
- 输入：偏好=无｜主题=无｜简报=工作台/banshee-intro-001/G1-创作方向/G1-参考视频分析/BGM-风格简报-冷战奇迹-v0.1.json｜时间线=160000ms

| # | 检索词 | 来源 | 推导依据 |
|---|---|---|---|
| 1 | 工业电子 压迫 | theme | 画像流派中文直译+情绪原词'紧张高压' |
| 2 | EBM dark | theme | 画像流派 EBM 原词+情绪'冷酷' |
| 3 | dark techno driving | theme | 画像英文检索词原样组合 |
| 4 | hard techno aggressive instrumental | theme | 画像'失真侵略性合成器贝斯'+'纯器乐需给人声留空间' |
| 5 | cinematic cyberpunk action score | brief | 本片为机体解说叙事片，需带叙事推进的动作配乐层（方向简报 coreViewpoint 依据） |

- 过滤推导：时长下限 160s（轨必须盖住成片）；BPM 111–135（简报锚定，进推荐打分）
- 纪律：词由 Agent 推导、脚本不编造曲库命中；改词=重跑本脚本；**检索词卡不设门禁口令**，真正的门禁是候选池上的「你挑一首」；网易云候选一律 uncleared-platform-catalog，试听件只用于选型。

- 机器合同：工作台/banshee-intro-001/G1-创作方向/G1-BGM找乐/检索词卡-v0.2/BGM-检索词-v0.1.json
- 消费：`music_search_netease.py --terms-file 工作台/banshee-intro-001/G1-创作方向/G1-BGM找乐/检索词卡-v0.2/BGM-检索词-v0.1.json`
