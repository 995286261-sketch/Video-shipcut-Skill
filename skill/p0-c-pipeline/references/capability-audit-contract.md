# 能力预检申报合同（唯一事实源）

v1.34.0（用户令 2026-10-22 开工；批次方案见 `docs/改进-能力预检申报-v0.1.md`）。
借鉴源＝OpenMontage preflight 申报纪律（AGENT_GUIDE.md:546 "不许到素材阶段才暴雷"）；
形态按我方纪律重做：探针转调现成入口、卡片走五段骨架、申报配机器硬闸。
治的我方病史：say/bl 静音回退、网易云 SSRF 走到才暴雷（zaku-003 台账②）、token 当场缺当场配。

## 1. 本体

- 入口：`scripts/capability_audit.py --project 工作台/<pid> --profile <特征csv> [--voice 音色]`
- 特征名单来自 G0 九问答案（BGM→bgm、配音→narration、烧字卡/字幕→subtitles、转场→transitions 常留待 G3 增量）。未入单＝`not_applicable`：不探测、不报缺、证据里 `probed:false`——**未涉却声称探过＝造假**。
- 每项转调对应专员现成探针（字体深检留在装配闸 ㉛、字幕深检在 subtitle_probe_renderer、转场深检在 transition_probe_host、听觉在 music_listen_omni、音色在 local_tts）——本脚本零领域判断。
- 状态三值：`ready` / `missing`（必带人话 remedy）/ `not_applicable`。**申报非预授权**：有缺口仍 completed、不阻塞 G0 批准；缺口节点走到前必须补齐或人工拍板降级（无听觉能力停靠点等既有机制吸收之）。
- 凭据只验在场、值永不读取永不回显（测试带金丝雀串断言）。
- 产物：`工作台/<pid>/G0-素材包/能力盘点-v<N>.json`，版本自增永不覆盖（㉘形制）。

## 2. 入册与时效

- `pipeline_state.py capability-audit --state … --audit-file …` 入册 `capabilityAudit` 块（file/上指SHA/probedAt/profile/summary/missing）；重跑入册旧块进 `capabilityAuditHistory`。手补件（kind/schemaVersion 不符）拒收。
- `validate_state`：块**可选**——老项目无块＝legacy 不追溯；**在场必须四字段齐**，半块不当 legacy 放过（v0.13.1 申报歪形教训常驻化）。
- `status` 输出带 `capabilityAudit`，编排每节点开工先读。

## 3. G4 硬闸（申报类=硬闸，用户 10-22 定案）

装配（g4_assemble）经 `resolve_capability_block(pipeline-state, waiver)` 四去向，全部落账+摊卡、无一静默：
1. `bound`——盘点在册、指纹相符、`probedAt ≥ G3 approval.approvedAt`；
2. **罢工**——文件不在/指纹不符/时间戳旧于最近一次 G3 批准/时间戳不可解析（报错点名重跑与入册命令）；
3. `waived`——唯一豁免：`--capability-audit-waiver '<用户逐字原话>'`，空文本拒、与 --pipeline-state 互斥；**AI 永不代用户披露**；
4. `legacy-unaudited`（state 无块的老项目）/`legacy-unwired`（未传 state 的历史补跑）——如实披露放行，摊上回显卡；新编排必须传 state。

防的实案：按默片开工→中途加配音→音色包没装→渲染出哑片。

## 4. 卡律（配套 final-echo-style-guide v1.5）

- G0 最终回显：③区结论行（全绿一行"工具盘点：全部就绪"；有缺口点名+影响+补法指路）；④区内联盘点表（列：能力｜实测结果｜状态｜缺了影响哪儿｜怎么补；数字逐字取盘点文件；卡尾出处行 `能力盘点-vN.json · <probedAt>` 不得删）。
- G1–G5 最终回显：**有事才报**——全绿不加行；存在与当前节点相关的缺口→③区一行提示；无关缺口只挂④区文件链接。
- 增量盘点：计划变更致名单变化（如 G3 新加转场）→编排重跑增量、出新版本、变化行单独呈小卡（专员表格卡形制，随本节点闸出，不加对话轮）。
- 禁词：①–③段说"工具箱盘点/这台机器暂时没耳朵"，`capability-audit/ebur128/xfade` 等字段名只进④区。
