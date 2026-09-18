# BGM 检索词卡 v0.1

- 目录：freesound｜分发边界：internal_test｜推导优先级：口头偏好 ＞ 主题翻译 ＞ 风格简报锚定
- 输入：偏好=背景音乐你从 freesound 里找好了｜主题=工作台/psycho-zaku-intro-002/G1-创作方向/G1-方向输入-v0.1.json｜简报=工作台/psycho-zaku-intro-002/G1-创作方向/G1-参考视频分析/BGM-风格简报-冷战奇迹-v0.1.json｜时间线=300000ms

| # | 检索词 | 来源 | 推导依据 |
|---|---|---|---|
| 1 | epic | theme | 主题：标题『怪物』的压迫感与UC末期大战叙事 |
| 2 | cinematic | theme | 主题：军武机甲科普介绍片的片头包装气质 |
| 3 | dark | theme | 主题：精神感应骨架/新人类的心理恐怖与悲剧底色 |
| 4 | trailer | brief | 简报锚定：123BPM、全曲能量高位、3个高潮段，属预告片音乐典型形态 |
| 5 | percussion | brief | 简报锚定：拍间隔中位487ms、卡点637个，节奏驱动明显 |

- 过滤推导：时长下限 300s（轨必须盖住成片）；BPM 111–135（简报锚定，进推荐打分）
- 纪律：词由 Agent 推导、脚本不编造曲库命中；改词=重跑本脚本；**检索词卡不设门禁口令**，真正的门禁是候选池上的「你挑一首」；网易云候选一律 uncleared-platform-catalog，试听件只用于选型。

- 机器合同：工作台/psycho-zaku-intro-002/G1-创作方向/G1-音乐检索/BGM-检索词-v0.1.json
- 消费：`music_search_netease.py --terms-file 工作台/psycho-zaku-intro-002/G1-创作方向/G1-音乐检索/BGM-检索词-v0.1.json`
