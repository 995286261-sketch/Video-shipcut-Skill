# 工作台选址合同（v1.35.0）

> 一句话：**新项目的落点是机器合同，不是 AI 的临场判断。** 本合同把 connector 形态早已硬闸化的
> `workspaceRootRef` 实例配置语义搬回本地 skill 仓：人选一次、机器记账、越界即罢工。

## 1. 规范根解析（唯一正道）

`skill/p0-c-pipeline/scripts/project_layout.py` 的 `resolve_workspace_root()` 是全部脚本与编排的
唯一住址真源，优先级固定：

| 序 | 出处 | source 值 | 语义 |
| --- | --- | --- | --- |
| 1 | 环境变量 `P0C_WORKSPACE_HOME` | `env` | 机器环境注入的根（宿主/CI 行为，视为人已定；AI 不得自行 set） |
| 2 | 仓根 `工作台选址.json`（gitignore，永不入库） | `choice` | 用户经一次性选址小卡逐字确认的事 |
| 3 | 仓库根（脚本自身住址回推） | `default` | 默认=开箱即用；同时=「尚未选址」的信号 |

工作台恒为 `<根>/工作台/`；项目恒为 `<根>/工作台/<projectId>/`（一层，不多不少）。

## 2. 首次必问（编排规程，一次性）

- 新会话进 G0 前，编排先跑 `pipeline_state.py workspace-root`（只读）：
  `needsUserChoice=true`（source=default 且无记录）→ 出一张**一次性选址小卡**：
  - 甲（推荐、直接确认可过）：仓库内 `工作台/`——样例项目都在，方便对照；
  - 乙：用户点名的其他目录（如大容量盘），用户给目录或原话即视为选址答复。
- 选完必须落账：`pipeline_state.py workspace-root --set <根> --user-words '<用户逐字原话>'`。
  **无逐字原话=拒写**（选址是人的决定，AI 永不代选——批准口令同纪律）。选甲也要落账，落账后不再问。
- 这是机器级静态事实，不是 G0 动态追问项：**只问这一次**，后续新项目静默沿用登记根；
  换址须人再次逐字选址（旧项目不搬家，state 里已带各自 workspaceRoot，两址并存合法）。

## 3. init 硬闸（罢工形制）

`pipeline_state.py init` 写 state 前核落点：`<登记根>/工作台/<projectId>/pipeline-state.json`
必须逐层相等，否则 `blocked`（exit 2），报错点名登记根、出处（env/choice/default）与实收路径；
**罢工先于建目录**（不产生半途项目）。合法住址只有登记合同的三种，AI 没有第四种自由。

选址记录半形/歪形（缺 kind/root/userWords）→ 读写两侧一律如实报错，不静默降级
（v0.13.1 教训：申报歪形必须当场现形）。

## 4. 留痕与续工

- init 成功后 state 记录 `workspaceRoot: {root, source, workbench}`；`status` 摊出，审计不用猜。
- `工作台选址.json` 含本机绝对路径＝机器私有事实，**gitignore 常驻**（公开仓红线：个人住址不入库；
  用例 `test_choice_file_never_enters_the_repo` 盯梢）。

## 5. 边界（如实申报）

- 闸门设在工作台户口落盘的 `init` 时点（项目成为正式项目的出生闸）；G0 素材登记先于开工单落账，
  其目录由 intake 按编排给的住址创建——编排规程要求该住址同样取自第 1 节解析结果，
  把闸前移到 intake 属后续批次候选，本批不扩面。
- connector 形态不受本合同影响（面板 statePath 硬拼 `<ctx.workspace>/工作台/<pid>/`）；
  **待办挂账**：connector 快照下次升钉至 ≥v1.35.0 时，`script/flow` 真引擎通道须随 spawn 注入
  `P0C_WORKSPACE_HOME=<workspaceRootRef>`，否则 init 闸会按引擎仓默认根对账而罢工（面板工单必炸，
  升钉批必须带上这一行）。
