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
| R2 | 审核登记后改计划仍可放行。审批绑定脚本、计划、旁白、字幕、成片等实际被审文件的指纹。变更后使受影响审批失效；保存审批人/来源、时间、版本和意见，禁止 Agent 自行代替真人批准。同路径替换文件或修改内容后，旧批准不可复用；重新检查并确认后才能继续。不影响无关项目。（用户转达补充：其中"禁止 Agent 代替真人批准"含两类——①已复现代码问题=G4/G5 invalid 报告仍推进 + 登记 G3 卡后改计划同路径放行；②流程风险=CLI 收到口令字符串只能证明有人传了值、不能自证真人，要求现阶段如实说明信任边界、接 Proxima 后由宿主审核入口提供可信审批事件，不要求账号系统。） | ①＝**R1 重复报**（她在 v1.4.0 上测的，本台账 R1 行今日已修）。②＝**当场复现成功**（临时项目：登记 G3 卡→同路径偷换计划→`确认G3` 照样进 G4）：收据快照只冻结**路径清单**（basisRefs/reviewCardRef/evidenceRef 仅存在性检查），从不冻结**文件内容**；R1 盖不住（R1 对账"报告↔成片实物"，这是"审批卡↔被审文件"，互补两层）。③＝属实但如她自认是**边界声明非已证实缺陷**：口令防伪超出本地 CLI 能力。 | ①新版已修（=R1）；②有效缺陷（挂空合同同族）；③流程风险→文档+字段 | **已闭环（本地；push/发版等口令）** | 方案（用户 09-24 过目批准）：`review_gate.py` 新增 `reviewed_file_hashes`+`sha256_file` 单一事实源（自 pipeline_state 迁入，杜绝 R1 那种同名遮蔽事故）；`record-review` 把审核卡+全部 basisRefs+全部 checklist evidenceRef 的 sha256 冻进快照 `basisHashes`；`approve` 关单前重算比对，变更/缺失**点名文件**阻断并指路"重渲卡→重登记→重确认"；**approvalRef 豁免**（批准文件关单时才写，合同如实写明）；旧快照无 basisHashes=硬切拒批（7 项目全部 completed、零在途影响）；审批记录加 `approvalSource: "host-session"`+既有 approvedAt/Verbatim=她要的"来源/时间/版本/意见"留痕齐面。合同：pipeline-state-contract《被审文件指纹绑定》+《人工批准信任边界》两节、operator-dialogue 规则7（改过必重出卡、代录≠制造）。测试：R2 负向 8 例（原案复现/修复通道/豁免活证/evidenceRef/卡↔报告/旧快照/无关文件不误伤/留痕断言）；R1 的 11 例适配两层门禁语义（报告换版后须重登记再测解析层——重登记即"改过必重出卡"的机器兑现）。套件 39/39 绿。提交 `4bccc36`（本地未 push）。 |
| R3 | 样例不通过本版交付检查。随包六份 G5 目录均缺 subtitle-srt-check.json，其中包括内部草案。补一份本版完整成功基线；历史案例标记版本或迁移，不通过删除校验绕开问题。新基线通过当前交付校验及媒体检测；报告、字幕和视频互相匹配。失败草案不标记为已完成。 | 盘上复核（09-24）：7 个封存 G5 包，**6 个当前校验 invalid、缺的全是同一对文件**（subtitle-srt-check.json＝v1.4.0 加严、transition-audit.json＝v1.5.0 加严）——她跑 v1.4.0 时仓里正好 6 包（sinjuku 09-23 才入库），"六份均缺"一字不差；唯一通过者＝sinjuku（新规之后交付）。病根**不是门禁没脚本**（正是脚本报的警），缺的是①"随包样例必须通过当前校验"的自洽测试层（09-21 合同加严当晚 6 样例集体变红而无测试变红）＋②版本演化无盘上标记（"不追溯重验"只写在合同文档里）。unicorn 草案流水线状态确为 completed_with_accepted_warnings（按当时合同完成，非虚报，但盘上不可见）。 | 有效缺陷（自洽层缺失+标记缺失；校验器本身行为正确，未删任何校验项） | **已闭环（本地；push/发版等口令）** | 三件套（用户 09-24 批准）：甲·自洽测试入 test_g5_delivery——本版基线包必须过当前校验（今后合同演进弄烂基线当场红）+六历史包必须带标记；乙·六旧包各放机器可读 `contract-era.json`（sealedAt 取自封存报告、缺失项、政策：禁删校验绕开、禁补造检查报告冒充迁移——旧项目无对应指令链硬造即造假；只加标记不动封存内容）；丙·sinjuku 坐实本版基线=当前校验器含 `--media` 全片解码 **valid/0 错误**（27 段/4 章，报告-字幕-视频互匹配）。合同 delivery-bundle-schema 新增《contract-era.json》节+两处"不追溯重验"句挂标记。套件 13/13、全量回归 39/39 绿。提交号见下一条台账回填提交。 |
