# 参考视频配乐风格简报合同

场景："我喜欢那个参考片子里音乐的感觉" → 转成可检索、可打分的机器条件。

## 生成路径

1. `music_analyze.py --input <参考视频> --style-brief-out <简报.json>`：先对视频音轨出分析报告，再派生《风格简报》。
2. 简报是**纯机器事实**：只含从音频测出的量，不含任何"建议曲目"。检索词 `suggestedQueryTerms` 留空数组，由 Agent 依片子的题材/情绪补写自由文本，脚本本身不编造曲库命中。

## 简报字段

```json
{
  "purpose": "reference_music_style_brief",
  "sourceTitle": "<参考视频文件名>",
  "sourceReport": "<源音频 SHA-256>",
  "bpm": 120.0,
  "bpmRange": [108.0, 132.0],
  "durationMs": 155390,
  "energyShape": [0.1, 0.3, "..."],
  "segmentCount": 6,
  "suggestedQueryTerms": []
}
```

## 下游用法

- 直接作为 `music_recommend.py --profile` 的画像来源（`bpmRange`、时长、分段数、能量形状）。
- 若参考音频本身来自 Freesound，可用其 sound id 走 `music_search_freesound.py --similar-to` 做内容相似检索（Freesound 服务器端已算好声学特征）。
- 未来 G1（⑤）对参考视频的复用，可直接引用本简报与分析报告（cacheKey 已按源文件哈希钉死，跨项目命中可校验）。
