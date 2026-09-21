# subtitle-expert 章程 v0.1（已拍板并执行）

> 2026-09-21 随 002 裁决批次起草为草案；同日用户口令"push，然后万事大吉了我们就弄 subtitle-expert 了"拍板剥出立册。文件名保留"章程草案"以存历史。执行结果与本章程的出入，如实记在文末《执行记录》。

## 为什么是它（earned，不是想象）

按"底座+插件"定案（用户 2026-09-21）：节点专员串联=底座，领域能力=插件。插件入册门槛四条，字幕全部踩中，且事故记录最厚：

- **跨四节点**：G2 出字幕文本（转写）→ G3 排版/ASS/SRT 生成与校验 → G4 烧录 → G5 格式与画面 QA。
- **归属已裂**：字幕样式合同（caption-style-contract）在 local-video-render（G4），布局校验器（validate_g3_subtitle_layout）在 video-edit-plan（G3），SRT 换算两边都沾——能力没有主人，接缝处出事。
- **事故链**：㉖（ASS 违反自身布局合同无人校验）→ ㊍（SRT 时基差 10 倍）→ ㉔（时间码可读性）→ **⑧（校验器绿灯≠渲染正确，字幕被裁，002 唯一用户可见级高危）** → ⑩㉛（字体预检与清单）。音乐域当初就是这种成色的事故堆出了 music-expert。

## 范围（四块，对齐 music-expert 结构）

1. **渲染器能力探测**：一次探测产出能力档（autoWrap、字形覆盖、libass 版本），缓存按宿主环境键控——⑧ 的根治：绿灯必须建立在所选能力档之上。
2. **排版合同与生成**：断行引擎（CJK 显式 `\N` 语义断行、两行均衡、宽度模型）、ASS/SRT 同源生成（消灭时基换算分叉）。
3. **烧录参数合同**：G4 逐字执行的字幕层参数（样式、边距、安全区、章节卡期间隐藏规则）——从 caption-style-contract 迁入。
4. **QA 审计**：G5 字幕面检查（语法、同步、越界 ROI 判读纪律⑪）合同化。

## 插件四标准（继承 music-expert 定案）

显式参数与文件产物、依赖全环境变量（通用名优先）、合同自带接线说明书（照 sourcing-contract 末节写法）、缺能力结构化 blocked。

## 接线点（剥出后的握手清单）

| 节点 | 现状 | 剥出后 |
| --- | --- | --- |
| G2 | local_transcribe 产转写 | 不变；字幕文本权威源仍是 G2 口播稿（专员不碰权威层） |
| G3 | validate_g3_subtitle_layout 在 video-edit-plan | 移入专员；G3 只调脚本、消费合同 |
| G4 | caption-style-contract 在 local-video-render；烧录在 g4_assemble | 合同移入专员；g4_assemble 逐字执行+哈希对账（照 BGM 混音合同先例） |
| G5 | qa-contract 判读纪律 | 移入专员 QA 合同；G5 消费 |

## 不做什么

- 不做语音识别新产品（转写仍归 G2）；不做花字/动效模板库（想象需求，无事故证）；不改口播稿内容权威层（BGM 同款纪律）。

## 成本与风险

- 迁移=两份合同搬家+一处校验器搬家+引用清扫，估计单批可完成；风险=硬编码引用漏清，靠全量回归兜底。
- 反对意见如实呈出：⑧ 的原地修复**已经落地**（7ba993c），剥不剥不再买"能修 bug"，只买"归属清晰+可整体迁移"。若你判断当前维护成本优先，维持现状完全成立。

## 执行记录（2026-09-21，剥出立册）

- **落册物**：`skill/subtitle-expert/`（SKILL.md，`pipelineNode: support`，花名册已登记）——
  - 块1 能力探测：`scripts/subtitle_probe_renderer.py` 新写（探测 ffmpeg/libass 版本；`autoWrap=true` 必须随附实测证据，否则拒收），产物 `字幕-渲染器能力档-v0.1.json`；缺 ffmpeg 结构化 blocked。
  - 块2 排版合同与校验：`scripts/subtitle_validate_layout.py` 自 video-edit-plan 迁入（含 ⑧ autoWrap 档位逻辑，零行为改动）；`references/layout-contract.md` 立为唯一事实源（合同形状＋能力档语义＋生成规则＋接线说明书末节）。
  - 块3 烧录参数合同：`references/style-contract.md` 自 local-video-render 的 caption-style-contract.md 迁入（正文原样保留，仅加归属头）。
  - 块4 QA 纪律：`references/qa-contract.md` 新写（⑪ ROI-only 边缘检测与判读纪律；"绿灯≠渲染正确"——画面发现裁切=能力档选错，回 G3 改档，不背渲染锅）。
- **与章程的出入（如实）**：
  - 块2 的"断行引擎、ASS/SRT 同源生成器"**未新建**——防过度设计红线：暂无事故证明需要生成引擎；SRT 换算规则（cs×10 零填充＋真实换行）已作为文档纪律固化进 layout-contract.md，生成仍由节点按合同执行。
  - 块1 的"字形覆盖探测"**未做**——㉛ drawtext 字形预检留在 G4 装载守卫内（非字幕排版能力），SKILL 边界已写明不抢。
  - 块3 的"g4_assemble 哈希对账"只落了**合同指向**：G4 逐字消费 `--subtitle-ass`（G3 冻结产物）＋读专员 style-contract，未新增对账机制——SRT 时基类事故（㊍）的修复已由换算规则承担，复现证据出现前不加层。
- **接线清扫**：G3（SKILL 改为"只调专员脚本、不实现规则"，g3-plan.md 校验命令指向专员＋能力档说明保留）、G4（SKILL 指向专员 style-contract）、G5（media-qa-delivery qa-contract 字幕面改指针）；旧脚本、旧 caption-style 合同、旧测试删除，grep 零残留。
- **验证**：新套件 12/12（校验器 9＋探测器 3，进程内 importlib 模式）；全量回归 9 套全绿（subtitle-expert 12、video-edit-plan 90、music-expert 96、local-video-render 34、其余 5 套照常）。
