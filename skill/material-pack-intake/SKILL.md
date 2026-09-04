---
name: material-pack-intake
description: 在下游制作 Agent 开始前，创建、校验并登记标准本地媒体素材包。适用于用户提供原始视频、图片、文档、风格参考、品牌资产或音频，并需要整理为七目录结构、哈希和机器清单的场景；不负责转写、脚本、剪辑、渲染、字幕或 QA。
metadata:
  pipelineNode: G0
---

# 素材包整理

本 Skill 只负责 G0 输入治理，正式项目产物写入 `工作台/<projectId>/G0-素材包/`；它拥有素材包，下游 Skill 拥有全部生产产物。用户回显遵循 [P0-C 路径展示合同](../p0-c-pipeline/references/path-display-contract.md)；素材包 JSON 和命令输出中的机器路径保持原始字符串。

## 对话式引导

必须主动带用户完成素材包。先展示 `references/g0-start-form.md` 的**核心五问**（做什么、给谁看、发哪个平台、素材在哪、想要什么感觉、BGM），接受自然语言回答，不要要求用户写技术字段。

收到核心回答后：
1. 根据平台自动推导画幅和时长建议。
2. 看到素材文件夹后，按需追问：品牌资产、禁用内容、授权范围、参考素材分类、配音需求。
3. 把收集到的信息写入 `01_需求说明.md` 和 `04_授权说明.md`。

整理完成后，**必须向用户展示资料清单回显**（已收到什么、待确认什么、项目信息），用户确认后才执行 `register` 和 `validate`。

详细规则见 `references/g0-start-form.md` 和 `references/user-guidance.md`。

## 命令

使用受控 Python 运行时：

```powershell
python scripts/material_pack.py init --pack <新素材包目录>
python scripts/material_pack.py register --pack <素材包目录>
python scripts/material_pack.py validate --pack <素材包目录>
```

- `init`：将七目录模板复制到一个不存在的目标目录。
- `register`：为 `02_原始素材/` 和 `07_授权音频/` 计算哈希，保留已声明的编辑输入，并写入 `material-pack.json`。
- `validate`：报告必填输入、可选目录、清单路径安全和哈希不匹配，不改动源媒体。

## 边界

1. 引导用户前先读取 `assets/material-pack-template/00_使用步骤.md` 和 `references/user-guidance.md`。
2. 目录含义见 `references/material-intake.md`，交接合同见 `references/material-pack-workflow.md`。
3. 不修改 `02_原始素材/`、`03_事实依据/` 或 `07_授权音频/` 的源文件。
4. `05_风格参考/` 只用于当前项目的风格规则，绝不将参考媒体转为输出资产；全局参考片不得悄然视为某个项目的输入，除非用户明确登记或复制其项目级引用信息。
5. 授权不明就如实登记为不明，不推断发布权。
6. 转写、脚本、编辑计划、预览、渲染、字幕和 QA 必须在素材包外部；当前项目按目录规范写入 `工作台/<projectId>/` 的对应节点目录。归档目录和 `新工作区/` 不得作为正式产物位置。

## G0 Fixed Start Form

Before receiving files for every new project, present `references/g0-start-form.md` 的**核心五问**。用户可以自然语言回答，不需要写技术字段。BGM 必须明确记录为 `provided`、`use library later` 或 `no BGM`。后补音乐必须创建或更新素材包版本记录，注明使用范围，不得静默合并。

整理完成后必须向用户展示**资料清单回显**，确认后才执行 register 和 validate。

The precedence rules for older intake wording are defined in `references/g0-policy.md`.

## Pipeline Integration

When `$p0-c-pipeline` owns the project, return only the validated material-pack path, pack status, authorization, and distribution status. Do not create downstream artifacts or advance G1. The pipeline creates `pipeline-state.json` only after intake reports a complete pack.

## 完成标准

七个条目存在、需求说明与授权说明的必填字段均已有效填写、至少有一个源文件，并且 `material-pack.json` 校验哈希一致时，素材整理完成。可选目录可以为空。
