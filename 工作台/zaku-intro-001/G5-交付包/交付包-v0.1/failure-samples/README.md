# 真实故障样本 — zaku-intro-001（只记实际发生与处置，不虚构通过）

| 故障 | 发现方式 | 处置 | 证据 |
|---|---|---|---|
| 源字幕遮蔽带不足（批准表 y950–1080，实测字幕 y880–990） | G4 QA 抽帧 | 带顶上调 y875，合同附修正注记 | 工作台/zaku-intro-001/G4-剪辑与渲染/qa/check-83.jpg |
| 遮蔽窗口不足 + 漏登记第三句源字幕 | 逐 0.5s 亮度扫描 | 窗口扩为输出 81.030–87.800s | qa/v02-87.0.jpg → qa/v03-87.0.jpg（遮死） |
| BGM 完全不可听（−18/12 叠加=恒定 −30dB → −40 LUFS） | 用户耳朵（G4 门禁前） | 重拍 −12/6 → −8/4；新增可听窗守卫 + 装配后实测对账（总账㉜） | 混音合同 predictedLufs / 装配记录 measuredInPlaceLufs −22.4 |
| 章节卡钉死画面正中，违反批准布局合同（title 道 0–15%） | 用户观感 | g4_assemble 新增 yRatio 通道，zaku=0.06 | qa/v05-0.5.jpg |
| drawtext 字体豆腐块（PingFang.ttc face0 缺简体字形）+ 路径含空格炸滤镜图 | v0.1 抽帧 | 换 Hiragino Sans GB 并加引号 | G4-封面合同 / 章节卡合同 fontFile |
| 在位电平测量挂死（-stream_loop -1 + atrim 在 mp3 不传播 EOF） | 21 CPU-分钟无输出 | 输入侧 -t 截断 + subprocess timeout=300 | g4_assemble.py measure_bgm_in_place |

作废版本 v0.1–v0.5 及旧合同归档于 工作台/zaku-intro-001/G4-剪辑与渲染/work/作废/，仅审计用，不作为交付物。
