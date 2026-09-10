# 检索词合同（BGM-检索词 v0.1）

回答"找 BGM 的关键词从哪来、长什么样、谁消费"。适用轨道：网易云试听选型（主）、Freesound（同 schema）。

## 推导规则（人读，Agent 执行）

检索词由 **Agent 推导提出**，脚本只做校验、归一、过滤推导与出卡——**脚本永远不编造曲库命中**（与风格简报 `suggestedQueryTerms` 留空同一立场）。推导优先级：

1. **用户口头偏好**（最高）：用户说过"我要 phonk 那种"→ 原话词直接成 term，`source: preference`；
2. **主题翻译**（主路径）：读 G1 方向简报/需求说明的题材+情绪，翻译成**音乐风格词**而非主题名词（"机战科普热血"→ `phonk 器乐`、`燃向 电子`、`史诗 战斗 BGM`；不是"扎古"）。中英各备（平台标签中文、genre 词英文）；
3. **风格简报锚定**（可选，有参考片才有）：`bpmRange`/`energyShape` 给翻译加数字依据（112 BPM 高能重复结构 ≈ phonk 族，不是 70 BPM 史诗管弦），并直接进 `filters.bpmRange`。

口播稿**不是**检索词来源：新顺序（蓝图先行）选曲先于写稿；旧顺序稿只做能量精化。

条数 2–6，多了去重截断；每张卡必须逐词写明 `rationale`（哪条推导、依据什么），回显给用户**可增删改后重跑**——检索词卡不设门禁口令（选型辅助），真正的门禁是候选池上的"你挑一首"。

## 机器合同

`scripts/music_search_terms.py` 产出 `BGM-检索词-v0.1.json`：

```json
{
  "schemaVersion": "0.1", "skill": "music-expert", "purpose": "bgm_search_terms",
  "catalog": "netease|freesound",
  "inputs": {"preference": "…|null", "themeRef": "方向简报路径|null", "styleBriefRef": "路径|null"},
  "terms": [{"term": "…", "rationale": "…", "source": "preference|theme|brief|agent"}],
  "filters": {"durationMinSec": 114, "durationMaxSec": null, "bpmRange": [101.1, 123.6]},
  "distributionBoundary": "internal_test", "retrievedAt": "…"
}
```

- `filters.durationMinSec` 由 `--timeline-ms` 推导（轨必须盖得住成片，向上取整）；`bpmRange` 取自风格简报（有则填）。
- 消费方：`music_search_netease.py --terms-file <该 json>` 逐词检索、合池去重，出一份候选清单；Freesound 轨道接线时同样消费。
- 同时渲染《BGM-检索词回显》固定表格卡（`music_echo` 同源样式），与 JSON 一起交用户过目。

## 与节点的接缝（接入主线时只做这三件事，专员侧不再动）

1. G0 `use_library_later` 槽位登记时采集口头偏好；
2. G1 末（方向简报批准后）Agent 按本合同推导词、调 `music_search_terms.py` 出卡；
3. 检索→推荐→挑曲→整轨登记回填。分析时点随"初次分析统一进 G1"的节点侧定案走（见交接文档）。
