# BGM 检索词卡 v0.2

- 目录：freesound｜分发边界：internal_test｜推导优先级：口头偏好 ＞ 主题翻译 ＞ 风格简报锚定
- 输入：偏好=BGM的话你从 freesound 找｜主题=工作台/sinjuku-intro-001/G1-创作方向/G1-方向输入-v0.1.json｜简报=工作台/sinjuku-intro-001/G1-创作方向/G1-参考视频分析/BGM-风格简报-冷战奇迹-v0.1.json｜时间线=180000ms

| # | 检索词 | 来源 | 推导依据 |
|---|---|---|---|
| 1 | industrial techno aggressive | theme | 模型对参照曲《冷战奇迹》节选十次 A/B 亲耳判定：快节奏、强鼓点、工业电子/Techno（BGM-试听笔记回显-v0.1，非脑补） |
| 2 | dark electro driving | theme | 同上耳朵证据的黑暗+推进双属性；driving 对应快节奏混剪需求（G1 风格规则：~3s 镜头快节奏） |
| 3 | action trailer electronic | theme | 新安洲机体快剪的预告片动作感，但限定 electronic 体裁与参照曲一致 |
| 4 | hard electro rhythm | theme | 参照曲硬派质感与明确节拍（笔记多次指出候选曲'无固定节拍'是首要淘汰因，此项直击节拍存在性） |

- 过滤推导：时长下限 180s（轨必须盖住成片）；BPM 111–135（简报锚定，进推荐打分）
- 纪律：词由 Agent 推导、脚本不编造曲库命中；改词=重跑本脚本；**检索词卡不设门禁口令**，真正的门禁是候选池上的「你挑一首」；网易云候选一律 uncleared-platform-catalog，试听件只用于选型。

- 机器合同：工作台/sinjuku-intro-001/G1-创作方向/G1-BGM找乐/BGM-检索词-v0.2.json
- 消费：`music_search_netease.py --terms-file 工作台/sinjuku-intro-001/G1-创作方向/G1-BGM找乐/BGM-检索词-v0.2.json`
