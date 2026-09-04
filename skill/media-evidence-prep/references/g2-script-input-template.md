# G2 原创口播任务单

复制并填写以下字段。任何留空项都应被标为待确认，而不是由 Agent 擅自补齐。

```yaml
projectId: <项目 ID>
topic: <本期要解释什么>
audience: <目标观众>
targetDurationSec: <成片目标时长>
referenceScriptRef: <参考转写/口播稿路径>
referenceUse: <只借章节结构 / 可借节奏 / 其他明确授权>
lockedText:
  - text: <用户已定稿原文>
    continueAfter: <从哪句话之后允许续写>
chapterTemplate:
  - 引言
  - 历史
  - 发生了什么事情
  - 做了什么
  - 成果+实战
factSources:
  - <本地资料路径>
spoilerBoundary: <允许与禁止的剧情范围>
voiceBrief: <语言、年龄、性别、语速、语气>
audioPolicy: <BGM/原声策略>
distribution: <本地练习/可发布等>
```

交付时将每一章映射为：叙事问题、可播事实 ID、编辑观点、待核验项、预计口播秒数。
