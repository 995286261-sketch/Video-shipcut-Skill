# Leader 反馈 · 问题清单 v0.1

外部使用反馈台账（skill 本体，非某视频项目验收）。反馈由 leader 使用 v1.4.0 后提出，用户逐条转达、一条条处理（用户 2026-09-23 定案：不一股脑给，防幻觉）。

## 基线事实（已核盘，勿凭记忆改）

- **载体**：`/Users/chuanzhangbigye/Downloads/Video-shipcut-Skill-main.zip`（GitHub main 快照下载）。
- **版本钉死＝v1.4.0「字幕专员版本」**（发布提交 `173d16c`，annotated tag `v1.4.0`）：
  - 解压文件集与 `git ls-tree v1.4.0` **3641 个路径逐字节一致**（IDENTICAL file sets）；
  - 抽查 `VERSION` / `validate_g3_callback.py` / `pipeline_state.py` 三文件 sha256 前 12 位与 tag 一致。
- **解压审计副本**（只读参照）：`/Users/chuanzhangbigye/工作/WorkSpace/Leader版本审计/snapshot/Video-shipcut-Skill-main/`。
- **使用程度**：未完整剪完一条视频，"大致机器跑了一遍"（用户 09-23 转述）——定性时须考虑反馈可能来自部分链路/环境差异。
- **v1.4.0 与当前 main（v1.6.0）之间的已知差集**（判"新版是否已修"的对照面）：
  - v1.5.0：transition-expert 立册+执行链三批（词表卡/指令派生/G4 xfade/G5 audit）；验收003 二十九条测后修复（含 ㉕ 口令归一化扩自然句形、㉘ 产物版本自增永不覆盖、⑯ 连续网格机器强制、㉒ 长链 settb、㉖ 唯一关单口令语义、style-guide v1.2 等）。
  - v1.6.0：试装预览四批（先看后批小样+G3 硬门禁+观看页一页看全部）；推荐层转正。

## 处置流程（每条五步）

① 原文照录 → ② 在 v1.4.0 审计副本上核实复现 → ③ 定性（v1.4.0 独有已修 / 现行版本仍存在之缺陷 / 使用姿势或环境差异 / 事实类不改）→ ④ 需修的走修复+回归 → ⑤ 台账回填去向与提交号。

## 状态图例

`开放`（待核实）｜`已核-待修`｜`已修-待回归`｜`已闭环`｜`新版已修`（v1.5.0/v1.6.0 已覆盖，附提交号）｜`非缺陷`（使用姿势/环境，附解释）｜`事实保留`

## 反馈台账

| # | 反馈原文（照录） | 核实结果（v1.4.0 上） | 定性 | 状态 | 去向/提交 |
|---|---|---|---|---|---|
| R1 | 质检失败仍可批准。审批入口解析 G4/G5 质检报告，校验结果、项目及产物版本。失败、报告缺失、结果过期、必需人工检查未完成时阻断；不能仅检查文件存在。invalid/failed 报告不能推进；有效报告与对应产物匹配且人工批准后才可推进。加入负向自动测试。 | 审批入口＝`pipeline_state.py` G4/G5 approve 块：`require_g4_file`/`require_g5_file` 只查"文件存在+在正确目录"+G5 文件名+basisRefs 在场，**不读报告内容**（status/projectId/新鲜度一概不解析）——属实。例外：人工检查完成度在审查收据层已机器强制（review_gate.py:72–75 逐项 required+completed+evidenceRef），"报告缺失"会被 required-args 拦一半。**现行 main（v1.6.0）该块与 v1.4.0 逐行相同**（v1.4.0..HEAD diff 仅涉 ㉕/㉗）＝非 v1.4.0 独有，现行仍存在。 | 有效缺陷（挂空合同同族：质检工具 g5_validate 内容级校验健全，但门禁不强制读其结果） | **已闭环（本地；push/发版等口令）** | 方案 A 落地（提交 `c344757`，本地未 push）：① `pipeline_state.py` 新增 `load_qa_report`/`validate_g4_report`/`validate_g5_report` 接入 G4 本地直渲染与 G5 approve——非 JSON/failed/张冠李戴/过期/缺产物绑定一律阻断（exit 2）；G5 可批值集定为 {`g5_pending_human_review`, `valid`, `completed*`}（实产物终态核实），chapterClips 数组形态同检；人工检查完成度仍由审查收据层强制（既有，不重复建）。② `g4_validate.py` 加 `--candidate`：报告补 projectId+候选成片 sha256+ffprobe 实测时长（与时间线 ±200ms 对账，非同一版即 fail）；无参调用向后兼容（不产生 candidate 字段）。ChatCut 分支无本地候选，不适用此绑定（如实注记）。③ 负向自动测试：test_pipeline_state 夹具从一行 "fixture" 文本升级为真 JSON 报告+真字节产物，新增 9 例（含"过期被拒→按提示重登记→放行"修复通道例）；test_g4_contract 新增 2 例（指纹绑定正例+错版/缺失负例）。④ 合同/SKILL：pipeline-state-contract G4/G5 条目、delivery-bundle-schema（唯一事实源先改）、qa-contract、local-video-render SKILL《--candidate 存档规程》。⑤ 实盘冒烟：7 个已关单项目 G5 报告只读重放——6 全过闸；**抓到真案**：sinjuku 报告 `sourceTimecodeList` 登记哈希与实物从未一致（旧 validator 不查该键、旧门禁只查存在性故漏网）；封存包按合同不追溯改写，留此记录。全量回归 39/39 逐文件绿。附带修复：`pipeline_state.py` 原有 `sha256_file` 返回小写与新增校验的大小写口径冲突（同名函数遮蔽），统一为大写——此坑实盘冒烟第一时间暴露。 |
