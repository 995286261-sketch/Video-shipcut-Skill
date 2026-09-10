# 标签受控词表（主题粗匹配）

单一事实源是 `scripts/music_tags.py`；本文件给人看，两处必须同步修改。

标签属于**语义层**（人怎么理解这首曲子），刻意与分析报告的**声学层**（DSP 测出来的 BPM/能量/卡点）分离：`music_analyze.py` 的产物里永远不出现标签。

## 设计纪律

1. **粗匹配**：标签只做 大致 的主题圈选，不做分类器、不做语义推理。命中数进入推荐打分（10% 权重，回显为 `tags n/m`），未命中不解释原因。
2. **人工登记必须用词表**：`--tags` 里出现词表外的标签直接 `invalid`，错误信息会附上全部可接受标签。
3. **外部标签尽力映射**：Freesound 等来源的原始 tags 通过别名表 best-effort 归一为 `styleTags`，映射不上的直接丢弃——不发明语义。
4. **需求画像同样受控**：`profile.styleTags` 里出现词表外标签，`music_recommend.py` 直接拒绝，不做静默忽略。

## 词表（3 维 / 18 标签）

| 维度 | slug | 中文 | 主要英文别名 |
|---|---|---|---|
| mood | epic | 史诗 | cinematic, trailer, heroic, majestic |
| mood | dark | 黑暗 | dramatic, tense, suspense, aggressive, intense |
| mood | warm | 温暖 | uplifting, hopeful, inspirational, feel-good |
| mood | calm | 平静 | peaceful, relaxing, ambient-ish, gentle, chill |
| mood | melancholy | 忧郁 | sad, emotional, pensive, bittersweet |
| mood | playful | 轻快 | fun, quirky, happy, cheerful, bright |
| mood | mysterious | 神秘 | ethereal, hypnotic, dreamy, space, cosmic |
| genre | orchestral | 管弦 | symphony, strings, choir, score, film-music |
| genre | electronic | 电子 | synth, edm, techno, house, trance, synthwave |
| genre | acoustic | 原声 | guitar, piano, folk, ukulele, violin |
| genre | percussive | 打击 | drum(s), rhythm, 808, taiko, tribal |
| genre | jazz | 爵士 | blues, swing, lounge, bossa |
| genre | rock | 摇滚 | indie, punk, metal, alternative |
| genre | world | 世界 | ethnic, oriental, asian, african, celtic |
| energy | driving | 推进 | energetic, powerful, upbeat, action, anthemic |
| energy | steady | 平稳 | mid-tempo, groove, loop, background, funky |
| energy | ambient-low | 舒缓 | slow, minimal, quiet, sparse, drone, downtempo |
| energy | building | 渐强 | crescendo, rising, build-up, climax |

完整别名以 `music_tags.py` 的 `TAG_VOCABULARY` 为准。

## 扩表规矩

新增标签必须同时改 `music_tags.py` 与本表，且给出 3 个以上真实别名来源；一个项目临时起意的情绪词不进表——词表膨胀会让"大致匹配"退化成噪音。
