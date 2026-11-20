# 失败样片说明

本包无失败样片：候选成片 v0.1 一次装配即通过全部机器校验（g4_validate valid、解码/黑帧/静音/重复检查见 metadata-validation-report.json）。

过程性失败（非成片缺陷）如实指向盘上审计，不藏账：

- 首版 8 段并账计划被 G4 brief sentenceStitch 罢工七条（问题 ㉓）→ reopen-g3 返工 12 段逐句落位重批：`工作台/mickey-intro-001/G3-剪辑计划/G3-回炉说明-逐句落位-v0.1.md`。
- 响度目标两次不可达（⑳ 出路取整 + ㉔ 放置轨物理下限）→ 二次 reopen-g3 定格 −17.7：`工作台/mickey-intro-001/G4-剪辑与渲染/响度/` 与问题清单 ⑳㉔。
- 转场预览 blocked_previews 抓到 seg-04 叠化物理不可能（源尾手柄 2ms，㉒ 正向样本）→ 降级硬切 G3 批准：`工作台/mickey-intro-001/G3-剪辑计划/预览小样/`。
- 测中缺陷 ⑩–㉗ 全程只登记不修复（用户口径）：`工作台/mickey-intro-001/问题清单-v0.9.md`。
