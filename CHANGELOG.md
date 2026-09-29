# 变更记录

## v1.21.0 — 2026-09-29 — **配音绿灯版本**

发布范围＝zaku-intro-003 测后批末件 ⑧（提交 `8eba71e`）：用户 09-29 裁决"就只用这三个（Samantha/Daniel/Karen），其他的我已经pass掉了"——英文成片直接用 macOS 系统声，百炼成品级 TTS 额度耗尽自此**不再卡点**；原"额度预检+403 结构化上报"修法随通道 pass 缓行（将来转付费通道再议）。zaku-003 问题清单 ①–⑮ 至此零开放。

- **绿灯通道成文（g2-choice-cards §3.5）**：预览级升成品级的唯一通道＝用户在试听卡上**逐字显式批准**（批准原话必须含"预览级"披露词，如"接受预览级用于正式成片"），原话登记进 G2 审核决定 `previewTierProductionApproval` 字段；不批则系统声只能做草稿声。禁止事后追认、禁止 Agent 代批——口子只放"知情用户拍板"，分级披露一个字不松。
- **机验在场（validate_g2_decision.py）**：新增 `validate_voice_tier()`——voiceBriefRef 指向 `local_tts.py` 清单且声明 `voiceTier=preview_only` 时，缺批准或批准不含披露词＝拒批点名；非 JSON/无 voiceTier 字段的历史手登清单（神经 TTS/真人通道）不触发本闸——机械判据只判在场的机械事实，schema 保持 0.2 不升版。`local_tts.py` 清单 `tierNotice` 同步绿灯新措辞。配音不单设专员：声音在 G2 诞生，下游只消费《G2-配音清单》wav+时长+哈希握手，provider 无关。
- **验证**：G3 校验链负例 4 例（缺批准拒／批准无披露词拒／逐字含披露词批准放行／production 级免批），套 61→65 例；py3.9 编译零错；发版前全量回归 45 测试文件逐文件绿。
- **已知限制**：Mimosa 完整扫描结论仍未取得，**不宣称项目安全**。

## v1.20.0 — 2026-09-29 — **人话引导版本**

发布范围＝zaku-intro-003 测后批表单批 ①④（提交 `18a8aaf`）：两条都是用户可见文案/沟通纪律缺口（用户 09-28 实测亲口提出），随批收官。

- **① G0 开工单第 4 问三形态并列**：旧问句"想要什么感觉？有参考视频/博主吗？"把能力藏在一句话里，新用户不知道可以甩一支满意视频当风格参考（本轮靠用户自己想起路径才用上）。现在 A 用几个词描述／B 给一支参考视频（"像它那样剪"，先分析节奏转场再照着来）／C 从以前的成片挑一支模仿——三选一即成立，并补边界说明（B/C 视频只当风格参考分析、画面不会剪进成片）；`g0-start-form.md` 与 `user-guidance.md` 核心五问卡两处同步。
- **④ 领域缩写首现必带人话释义（operator-dialogue 规则 8）**：事故＝过程消息里"DSP 分析"未加说明，用户原话"这个东西我见都没见过"。说人话纪律原本只覆盖卡片模板，过程性聊天实测漏网；现在一切用户可见文本（过程通报、进度锚点、错误解释）首现缩写必带一句人话释义（例："DSP 分析＝程序量波形：读 BPM/能量/卡点"），能用白话词直接用；用户被术语挡在门外＝Agent 违规。与卡片禁词表（final-echo-style-guide）两半合璧，合同才完整。
- **验证**：纯文案/纪律批，无代码改动；发版前全量回归 45 测试文件逐文件绿。台账 ①④ 回填，zaku-003 问题清单 ①–⑮ 仅剩 ⑧ 开放（外部配额议题，见台账行）。
- **已知限制**：Mimosa 完整扫描结论仍未取得，**不宣称项目安全**；⑧（bl 成品级 TTS 额度预检+403 结构化上报+降级链合同）留待用户定政策后处理。

## v1.19.0 — 2026-09-29 — **登记件机抽版本**

发布范围＝zaku-intro-003 测后批工具组末件 ⑫（提交 `f38ba9b`）：封面帧来源无机器校验——`G4-封面合同` 只有 `imagePath`，抽帧入口在编排方手里；实跑 shell 通配 fallback 误抓 `05_风格参考/冷战奇迹` mp4，参考片画面险成封面（红线：参考视频画面不得入成片），目检才拦下。

- **抽帧收进装配器**：封面合同改 `materialPack`+`sourceAssetId`+`sourceMs`（源内毫秒，时点与身份取自批准计划/G3 封面指令）+`fontFile/title/output`；`g4_assemble` 从登记 material-pack 反查精确路径→对在册 sha256 逐字验明正身（不符 `sha256 mismatch` 罢工）→ffprobe 实测源时长钳 `sourceMs`→机抽帧+叠标题；装配记录落 `coverProvenance`（assetId/资产路径/在册哈希/sourceMs/sourceTimelineMs/帧文件/帧 sha256）。
- **`imagePath` 通道退役**：合同出现即罢工（硬切：全部项目 completed、已封版旧合同留作审计记录，R3 不追溯）。定性：只要路径由编排方拼，通配猜的失败模式就一直在——登记件之外的画面（含参考片）结构上进不来封面，不靠目检。
- **四处成文**：render-contract《封面合同（⑫ 登记件机抽帧）》、SKILL 客户演示成片节（自选帧文件＝违规）、demo-quality-patch §3、G4 回显卡封面项写明登记件出处。
- **验证**：g4 套 38→43 例（正案机抽+provenance 落账；负例 imagePath 罢工／三必填各缺即拒／未登记 assetId 拒／在册 sha 漂移拒／sourceMs 超时长拒）；**活体彩排**（zaku-003 真登记件、项目只读、产物落 WorkSpace/cover-机抽复验-v0.1/）：sourceMs 25859 机抽帧→资产 sha AA6DFCCC… 逐字对上登记件、帧 sha 落账、目视确认＝夏亚红扎古太空持枪帧（非参考片）；假 assetId「style-ref-05-冷战奇迹」当场 `not a registered asset` 拒。py3.9 编译零错；发版前全量回归 45 测试文件逐文件绿。
- **已知限制**：Mimosa 完整扫描结论仍未取得，**不宣称项目安全**；测后批仅剩表单批（①④），逐条处理。

## v1.18.0 — 2026-09-29 — **专名词表版本**

发布范围＝zaku-intro-003 测后批工具组第六件 ⑨（提交 `c1f5155`）：bl 合成旁白的 ASR 回读无专名词表通道——`local_tts.py --verify-asr --asr-initial-prompt` 只覆盖自家 say 路径；bl（CosyVoice）产物回读走 `local_transcribe.py`，该脚本无词表参数，whisper small 把 吉翁/鲁姆/麦哲伦/乔尼/赤色彗星 全听成同音误字（吉翼翁/卢姆/迈辙轮/脚泥/赤色汇心），逐词比对假阴性一片红，等于没有自检（本轮靠人工判读兜住）。

- **`--initial-prompt` 透传＋词表进 cacheKey**：`local_transcribe.py` 新参数透传 faster-whisper `initial_prompt`，产物落 `initialPrompt` 留痕；词表进缓存键（新字段＋runtimeVersion 升 v0.3）——换词表＝换转写结果，不许复用旧稿，v0.2 旧缓存也不会被误复用。台账方案乙"专用回读比对小工具"**不建**：词表杀掉假阴性大头后，残余同音判读本属人耳环节，再造比对工具＝过度设计。
- **回读分支与关单纪律成文**：SKILL 工作流第 4 步与 cacheKey 复用条件补专名词表；g2-choice-cards 配音节新增外部合成通道分支——bl 旁白回读用 `local_transcribe.py --initial-prompt <同一份词表>`，仍有同音假阴性可人工判读"同音=通过"关单，但结论如实记 `asrSelfCheck`、不得写成机器通过（本轮处置成文化）。
- **验证**：media-evidence-prep 套 13→15 例（同词表才复用；无词表运行对不上带词表缓存→拒绝复用转真转写；空词表＝无词表形态）；**活体彩排**（zaku-003 真 bl 旁白 wav、项目只读、产物落 WorkSpace/media-transcribe-词表复验-v0.1/）：带词表回读与封存旧稿对盘——吉翁 2/2、鲁姆 1/1、乔尼·莱登 1/1、赤色彗星 1/1 逐字复活（夏鸭→夏亚 顺带纠正），麦哲伦→"迈折轮机"残留一处——按成文判读纪律处理，词表救回大头、机器不包 spelling。py3.9 编译零错；发版前全量回归 45 测试文件逐文件绿。
- **已知限制**：Mimosa 完整扫描结论仍未取得，**不宣称项目安全**；工具批余件 ⑫ 与表单批（①④）继续逐条处理。

## v1.17.0 — 2026-09-29 — **在册逐字对账版本**

发布范围＝zaku-intro-003 测后批工具组第五件 ⑦（提交 `529ef7f`）：经验库 `music_library.py verdict` 对不在册 sha 不拒、静默新建只含 verdicts.jsonl 的**幽灵 track 目录**——实跑中凭记忆写 sha（只核实前缀 9F61EA0B）险些入库，幸而全量比对发现尾段 …430B vs …D291 不同、删幽灵重录。红线"哈希绝不凭记忆"本轮升格为机器对账。

- **`require_registered()` 全量对账**：派生层四入口（`verdict`／绝对笔记 `listen`／许可翻转 `grant`／锚点 `anchor`）只许挂在已 `ingest` 且**全量 sha 逐字**（大小写归一后）对上身份卡的曲目上——台账初案"命中前 16 位即放行"不够：目录前缀撞车而尾段不符＝判决串档到真曲档案上（本行事故本体正是撞前缀），一律 `track_not_registered` 当场拒、一字节不落盘、指路先 ingest 且 sha 从登记件/分析报告现字。`put_listen` 内层同闸防御纵深；acoustic 原有身份先行闸保留。
- **库规成文**：`experience/music/README.md` 新增《入库通道纪律（⑦）》——幽灵进不了库从此靠工具而非自觉。
- **验证**：listen 套 8→10 例（幽灵 sha 拒且无新目录；同前缀假尾段对四入口全拦＋真档案逐文件零沾染断言；在册真 sha 大小写归一照过）；**真库只读复验**＝在册曲前缀+假尾段当场拒、experience/music 文件校验和前后一致（库未动一字）；发版前全量回归 45 测试文件逐文件绿、py3.9 编译零错。
- **已知限制**：Mimosa 完整扫描结论仍未取得，**不宣称项目安全**；工具批余件（⑨⑫）与表单批（①④）继续逐条处理。

## v1.16.0 — 2026-09-29 — **自锚否决版本**

发布范围＝zaku-intro-003 测后批工具组第四件 ⑥（提交 `a63a6f7`）：omni 耳朵笔记两轮互斥的机器设防——首轮 A/B 把 LOW-PHONK 既当参照曲又留在候选池，"10/10 同曲"满分实为退化自比；换参照后同一首歌体判直接矛盾（6/10 能用 vs 4/10 不能用），全靠用户追问复验才救场。

- **自锚否决闸**：A/B 模式装载候选后先比参照曲与每个候选预览件的**文件 sha256**（比台账初案"路径命中"更强——改名/换目录/拷贝都拦得住，只认同一段字节），任一相同当场 `invalid reference_is_in_candidates` 点名标题、指路"剔除该曲重跑，或确认真正感觉源应是别的文件"，**一耳不开**（闸在模型调用之前）；绝对模式无参照、不参与。
- **参照身份机器字段**：A/B 与画像（`--reference-note`）产物都写 `referenceSha256`，回显卡头带 `sha 前12位…`——画像卡与 A/B 卡是否"同一只耳朵听同一参照"只认 sha 对账，不认文件名。
- **并呈纪律入合同**：listen-notes-contract 新增"参照身份红线"（参照曲=用户点名的感觉源，永不与候选同文件）与"换参照＝换考题"（A/B 是相对评价，锚不同结论自然不同；两轮互斥必须并呈两轮原文各带参照与 sha、终审交人耳——免责条款从纸面变刚需）；music-expert SKILL 编排节同步成文。
- **验证**：listen 套 7→9 例（自锚拒断言零模型调用+零产物落盘；referenceSha256 与文件真实 sha 对账、两卡同 sha）；**真素材彩排**＝重放 zaku-003 事故现场——LOW-PHONK 本尊当参照+封存库内原池当场拒且点名（项目只读、产物落 WorkSpace/music-listen-自锚复验-v0.1/），剔除后重跑 heard 3、字段与卡面 sha 实证一致；发版前全量回归 45 测试文件逐文件绿、py3.9 编译零错。
- **已知限制**：Mimosa 完整扫描结论仍未取得，**不宣称项目安全**；工具批余件（⑦⑨⑫）与表单批（①④）继续逐条处理。

## v1.15.0 — 2026-09-29 — **规范根语义闸版本**

发布范围＝zaku-intro-003 测后批工具组第三件 ⑤（提交 `2dea7bb`）：`g1_direction.py write --workspace` 参数语义踩坑——该参数真实语义＝仓库规范根（`工作台/` 的父目录），实跑时按直觉传了项目目录，拼出 `工作台/<id>/工作台/<id>/G1-创作方向` 嵌套路径（本行项目当场已把误落简报搬回规范位、stray 目录核实删除无残留）。

- **语义闸（机械判据只判机械事实）**：`workspace_semantics_issue()`——传入 workspace 解析后的绝对路径**任何一段名为「工作台」**（＝已在/就是规范目录之下），write 当场 `blocked workspace_semantics`，detail 点名"该参数＝规范根，请改传仓库规范根"，一字节不落盘；不猜意图、不留后门（想写到别处＝传对路径）。
- **措辞纠偏**（误导源在文档）：SKILL 调用点占位符 `<调用方工作区>` → `<仓库规范根=工作台/ 的父目录（不是项目目录！⑤）>`；语义段成文"⑤ 语义闸"一节；`--workspace` help 写死语义与拼接规则；脚本 docstring 同口径。
- **验证**：g1 套 14→15 例（负例双形态：传项目目录、传工作台根本身→均当场拒且断言嵌套目录未生成）；py3.9 编译零错；发版前全量回归 45 测试文件逐文件绿。
- **已知限制**：Mimosa 完整扫描结论仍未取得，**不宣称项目安全**；工具批余件（⑥⑦⑨⑫）与表单批（①④）继续逐条处理。

## v1.14.0 — 2026-09-29 — **解码即证据版本**

发布范围＝zaku-intro-003 测后批工具组第二件 ③（提交 `d187d8c`）：库内批次机械排序全 0 分（含用户已批准锚点 LOW-PHONK）修复。真因**推翻台账初疑（styleTags）**——盘上排序四首 notes 全为 `decode_probe_not_passed`：`music_recommend.score()` 解码门槛只读候选自带 `decodeProbe` 字段，而手动登记/库内导出记录根本没有该字段 → 机械一票清零；styleTags 缺失只是次级事实（画像要 5 标签而候选无标签，修复后如实显示 `tags 0/5` 参与折算，不造假兜底、也不至于清零）。

- **解码证据两层合同**：打分门槛认两种证据——候选 `decodeProbe: passed`，或候选匹配到分析报告且报告 `source.sha256` 与候选身份 sha 逐字相同（报告由分析器真解码成功才落盘，在场即作证，标 `decode_via_analysis`）；候选显式记 `failed` 的机器失败事实不被旧报告翻案（保守红线）；两者皆无维持零分。身份仍只认 sha 逐字——无报告候选的 `unanalyzed` 指路闸一字未动。
- **成文与纠偏**：sourcing-contract 登记产物节写明两层合同，并修正此前"候选记录都带 decodeProbe"的不实陈述（检索/下载轨道当场跑探针；手动登记/库内导出可无该字段）。
- **验证**：recommend 套 4→8 例（缺字段+报告在场→打分并标证据；failed→零分不被翻案；无报告→仍 unanalyzed；无 sha 字段→按文件字节身份成立）；**活体彩排**＝zaku-003 真库内批次只读复跑（画像从封存排序逐字提取、产物落 WorkSpace/music-recommend-库内复验-v0.1/）：四首 0.0 → 弥渡 0.8453/Devil 0.7877/Gone Bad 0.7773/LOW-PHONK 0.7490，passing 4/3、enough，3/4 未清权侵权警告与 LOW-PHONK cleared-for-project 免警原样；发版前全量回归 45 测试文件逐文件绿、py3.9 编译零错。
- **纪律不变**：机器分仍"只作排序参考，永不单独定推荐"——排序失真修好不等于机器分升格（zaku-003 耳朵 A/B 定推荐的处置留档有效）。
- **已知限制**：Mimosa 完整扫描结论仍未取得，**不宣称项目安全**；工具批余件（⑤⑥⑦⑨⑫）与表单批（①④）继续逐条处理。

## v1.13.0 — 2026-09-29 — **下载通道复活版本**

发布范围＝zaku-intro-003 测后批工具组第一件 ②（提交 `51b9c11`）：网易云检索通道下载层全灭（0/120）修复。病根＝预览 302 一律跳 `http://` 授权 CDN，被 09-21 收紧的 SSRF 白名单守卫按 https 规则拦死——检索命中、排除原因全在工具层，个人/内测选型通道自此不可用。

- **修法（用户 09-29 定案口径：红线是 guard 本身不许拆）**：`upgrade_cdn_scheme` 只在**白名单域名在场**时把 http 跳转升级为 https 再交 guard 逐跳校验——只动 scheme、主机校验原样、名单外 http 原样拒、测试套件 loopback http 例外不被动；升级主机逐候选记 `previewSchemeUpgraded` 留痕；sourcing-contract 轨道三守卫条成文。
- **验证**：netease 套 9→15 例（名单内升级过 guard、https 原样、名单外不升级、无网络即拒、loopback 例外保留、默认 base 本为 https）；**活体复验**=真检索 3/3 试听件下载成功、decode passed、license/boundary 字段原样（升级实发 m801/m701.music.126.net）；发版前全量回归 45 测试文件逐文件绿、py3.9 编译零错。
- **边界不变**：netease 候选仍 `uncleared-platform-catalog`/internal_test，进成片必须官方渠道整轨+登记（轨道三纪律一字未动）；对外项目主轨仍是 Freesound。
- **已知限制**：Mimosa 完整扫描结论仍未取得，**不宣称项目安全**；工具批余件（③⑤⑥⑦⑨⑫）与表单批（①④）继续逐条处理。

## v1.12.0 — 2026-09-29 — **报告生成器版本**

发布范围＝zaku-intro-003 测后批第三件 ⑭（G5 质检报告标准生成器）＋彩排当场抓出的同族缺陷 ⑮（builder 装配字段静默抬空），提交 `2a72106`。

- **⑭ `--report-out`＝metadata-validation-report.json 唯一正道**：`g5_validate_delivery.py --bundle <包> --media --report-out <包>/metadata-validation-report.json`——机器跑完全部校验（任一不过=不落盘，报告只描述合格包）后，artifacts 对包内每个证据文件现算 `path`+大写 `sha256`（关单三件套合法除外：报告自身不能自指、manifest/decision 封版必改写，改由收据 basisRefs+R2 basisHashes 绑定）；checks 只写本轮实测事实（无 `--media` 拒生成；未跑项写死「待补」占位——能力可缺、事实不能编）；status 固定 `g5_pending_human_review`（机器无权宣告完成）；带 `generatedBy` 出处行；已存在报告拒绝覆盖（⑭/㉘ 同源纪律）。当年病根＝报告全程手搓 JSON，7 项握手产物漏登 sha256 拖到 R1 关单闸才拦、来回重冻一次。
- **封版新序列（schema/SKILL 成文）**：组件齐 → builder 建 **pending manifest**（⑭ 配套缺席容错，002-⑬ finishedAt 豁免延续）→ 机器生成报告 → 编排替换待补占位为人话+回显卡 → 人审 → 封版改写（决策/manifest/report status）→ `--bundle --media` 终验 → record-review/approve。
- **⑮ builder 罢工点名（彩排第一拍抓出）**：G3 计划合同只要求逐段 evidenceRefs、顶层 `evidenceRefs`/`humanReviewPoints` 从未入合同——老跑法封版段手补进 manifest 掩盖了缺口；新序列下 builder 不再静默抬空数组，缺字段当场罢工点名（补登责任=G5 装配步、来源=包内计划副本）。历史封链不追溯（R3）。
- **验证**：G5 套 21→28 例（生成 6 例含真 lavfi 小媒体夹具、生成报告直喂 R1 `validate_g5_report` 活证、负例 5 案；builder 负例 1 例双断言）；**真 zaku-003 交付包 WorkSpace 副本全链彩排**：17 件全指纹、终验 valid、R1 一次通过、封存版 11 件手登指纹与机器重算逐一一致（项目原件零触碰）；发版前**全量回归 45 测试文件逐文件绿**、py3.9 编译零错。
- **已知限制**：Mimosa 完整扫描结论仍未取得，**不宣称项目安全**；测后批余件（工具批②③⑤⑥⑦⑨⑫、表单批①④）继续逐条处理。

## v1.11.0 — 2026-09-29 — **放置轨重规划版本**

发布范围＝zaku-intro-003 测后修复批第二件 ⑬（提交 `7ca35cc`）：G4 响度 sha 闸的"装配前对放置轨重规划一拍"补进合同与编排——G2 规划对象常为连续试听轨、装配输入是按声音简报放置的配音轨，sha 对不上是按设计必拦而非事故，标准出路从"条件反射回 G2"改为先重跑 loud_plan 再定性。

- **判定口径（机械判据只判机械事实）**：重规划 `status` 档与 `targetProfile` 三元组逐字不变＝决定输入未变→G4 回显记账、换用新计划继续、**不重开 G2**（盲目重开＝门禁过重的反例，zaku-003 实跑当场验证）；status 翻转／目标变／出路条数种类变＝才回 G2 重确认试听卡。出路文案内嵌实测数字随轨放置会毫分漂移（核盘查实 9.99→9.98 dB、8.80→8.79 dBTP——顺带修正台账⑬"三出路逐字同"的不精确表述），数字新旧并陈摊入 G4 回显随 `确认 G4` 人眼确认，机器不代判"差多少算没变"（判断环节 harness 做薄纪律）。
- **落点四处**：loudness-contract §8 批三条新增重规划步骤+判定口径+实跑第一案实录；`g4_assemble` sha 闸罢工文案两情形指路+docstring 同口径；g4-choice-cards 响度执行记账新增"放置轨重规划记账"行样式；local-video-render SKILL 执行入口同步。
- **验证**：sha-drift 负例测试锁三关键词（重跑 loud_plan／不回 G2／决定输入）；zaku-003 真素材双向彩排（只读）——G2 计划×放置轨=罢工新文案逐字上屏、G4 重规划×放置轨=闸过且 status/profile 实证逐字不变；G4 两套件 38+14 绿、py3.9 编译零错；**发版前全量回归 45 测试文件逐文件单跑全绿**。
- **已知限制**：Mimosa 完整扫描结论仍未取得，**不宣称项目安全**；测后批余件（⑭ 关单路上，再后工具批/表单批）逐条继续。

## v1.10.0 — 2026-09-29 — **依据上卡版本**

发布范围＝zaku-intro-003 响度接线实测跑（09-28～29，六门禁全过 completed_with_accepted_warnings）测后修复批**第一件 ⑪**（用户 09-29 亲口抓到"转场编辑理由在卡与观看页双双无出口"，并定总原则"**每一步都要有所依据**"；方案三点经用户"我没意见"批准：非硬切才强制理由／依据区在八列表下方追加／理由只进展示与入场闸不加重执行层）。提交 `f40e6a3`。

- **合同层**：编辑计划段级新字段 `transitionReason`——凡选叠化/黑场入/黑场出必须携带非空理由（为什么动效而不是默认硬切），`validate_g3_plan.py` 机器强制，没登记理由不许动效；硬切为缺省态不强制，防套话稀释字段。plan-contract / transition-contract / g3-choice-cards / g3-plan / video-edit-plan SKILL 五处文档同步（理由改动=计划改版口径）。
- **渲染层**：`render_g3_review_card.py` 从已批准计划逐字渲染——第 5 列兑现表头承诺的"用途/实际画面观察"（用途=段级 `transitionReason` 逐字，画面观察沿用既有字段）；八列表下方对含非硬切计划自动追加固定**『转场依据区』**（逐切点：边界｜指令·时长｜依据）。旧版计划缺字段如实标"未登记"，不编造。
- **观看页**：`transition_preview.py` 把理由逐字带入预览清单 `previews[].transitionReason`，观看页每个切点卡标题下、播放器前显示"依据：…"行——先看依据，再看小样。
- **执行层零改动**：理由＝展示+入场闸，G4 指令构造/G5 审计与上一版逐字节一致；R3 纪律——只对新提案生效，已封存包不追溯（现行测试无对已封 G3 计划复跑 validate_g3_plan 的通道，天然安全）。
- **验证**：转场卡套 11→19 例（三类非硬切缺理由/空白理由负例、硬切无理由不拦、卡第 5 列与依据区渲染正例），预览套 11→13 例（清单携带+观看页依据行、旧条目缺字段不编造）；**发版前全量回归 45 测试文件逐文件单跑全绿**、py3.9 编译零错；zaku-003 真素材彩排（全局 WorkSpace，项目目录与门禁零触碰）：两处叠化补登记理由后新卡依据区与观看页依据行肉眼验证通过。
- **已知限制**：Mimosa 完整扫描结论仍未取得，**不宣称项目安全**；测后修复批 ①–⑭ 余件（⑩⑪ 已闭环）逐条讨论后逐条处理。

## v1.9.0 — 2026-09-28 — **响度接线版本**

发布范围＝`skill/loudness-expert/` 专员产物接入 G2/G3/G4/G5 四节点全部生效（工单 `docs/响度接线工单-v0.1.md`，用户 09-28 "接"令开工、"全都弄完再说"定四批统一发版口径——本线豁免"更新即发版"新规一次；逐批提交：批一 `3ed285e`/`65eb85e`/`39d100c`/`8729187`、批二 `12d7414`、批三 `176c909`、批四见本版）。

- **批一 G2 配音**：试听卡嵌入素材响度天花板披露（"最响可到 X LUFS（目标 −14）"，数字逐字取专员产物）、够不着同轮出路选项卡；`validate_g2_decision.py` 升 schema **0.2**——`loudnessPlanRef` 必带+产物身份+旁白源 sha256 对账，**批准后重合成配音=批准自动失效**（R2 同型）。历史 0.1 决定不追溯（R3）。
- **批二 G3 剪辑计划**：目标档双式记账——`packagingDecisions.loudnessTarget` 三元组逐字对账 G2 所绑专员计划（帧率⑧甲同型"卡说 X 机器渲 X"）；`validate_g3_plan.py` 批量拒缺拒差；换档必须回 G2 重规划、机器不代换。
- **批三 G4 装配（丙·分档口径，用户"走你推荐的"拍板）**：`g4_assemble.py --loudness-plan` 产物握手（身份头+规划源 sha+串项目罢工）；三口径对账 G2 targetProfile==manifest.loudnessTarget（`g4_prepare` 镜像自 G3 包装决定）==执行链参数，缺一拒装；**ready→逐字两遍线性**、预渲染纯口播量纲实测超容差=罢工（兜住 loudnorm 静默回退红线）；**blocked→显式受控 dynamic**（标准压缩链按 targetProfile 展开）+loudnorm stats 落账、I 超差=disclosed-exceedance+reviewNote 必进回显第③节摊开确认、永不静默不罢工；TP 超上限+0.3 余量两档共同硬闸；旧 `--normalize-narration-lufs` 仅历史补跑并与计划旗标互斥。定标事件①：彩排第一轮长天真口播落点 −15.6 超差 1.60 LU 证伪"一刀切硬闸"（=一切真项目永久罢工=假闸），语义随批入合同 §8.3。
- **批四 G5 交付**：`loud_verify.py` 三态（passed/disclosed-exceedance/failed）——blocked 计划验收必 `--assembly-record` 绑定逐字对账装配记录 loudness 块（planRef sha/mode/targetProfile）；交付包**条件 REQUIRED**：时代写在产物里——edit-plan 带 `packagingDecisions.loudnessTarget` 即必交 `loudness-audit.json`（`g5_validate_delivery.py` 校验身份/状态/目标档一致/masterSha 新鲜），批二前历史封包（含 sinjuku 基线）零影响、无需新标记、严禁补件（R3）；disclosed-exceedance 关单须 `human-review-decision.acceptedWarnings` 点名"响度"（摊开必确认贯穿到交付人审闸）；`--media` 现测 ebur128 与报告复现对账 >0.3 LU/dBTP 拒（哈希抓字节变化、复测抓换件重渲漂移）。定标事件②：真成片 TP −1.2 踩 −1.5+0.3 浮点边界误判越限——合成信号全绿未暴露、真素材抓出，边界比较补 1e-9 容差，坐实"接一个、真跑验一个"。
- **文档**：合同 `loudness-contract.md` §8 四批全部转"已接线生效"（唯一 as-built 口径）；g2/g3/g4/g5 各卡型响度行、`media-qa-delivery` SKILL/qa-contract/delivery-bundle-schema、花名册、交接文档、台账 ⑪ 行闭环（待决三点全部落地：闸口=G4 罢工+G5 必过；−14 维持为计划承诺、闸随承诺物理性分档；天花板披露提前到 G2 试听卡）。
- **验证**：四批各带 WorkSpace 真素材彩排（项目目录与门禁零触碰）：G2 六源双形态卡+zaku 全链、G3 正反例过闸、G4 blocked/ready 两档装成+负向四案（含串项目实盘第一案）、G5 正案 valid+`--media` 原样复现、负三案全中（撤响度点名/抽审计/换成片字节双闸齐响）。**发版前全量回归 45 测试文件逐文件单跑全绿**；套件水位：专员 43 例（含端到端三态）、G4 本地渲染 38、G5 交付 21（含 sinjuku 基线 R3 锁例）、G3 61。
- **已知限制**：Mimosa 完整扫描结论仍未取得（各 commit 带 library_source_unavailable 兼容放行提示），**不宣称项目安全**；omni"第二只耳朵"接入观察类环节仍未接线（加分轮单独议）；平台融入适配（sourceAsset 合同、gN 前缀改名）按 09-21 决定挂起。下一步：完整实际测试（新项目、素材由用户亲手提供）。

## v1.8.0 — 2026-09-28 — **响度专员版本**（独立建设，未接线）

发布范围＝`skill/loudness-expert/` 第四插件专员独立建成（用户 09-28 裁决归属＝甲·独立专员，节奏定案**"先建成单独 skill、独立测试完毕后再考虑接入节点，后续遇到分贝问题能复用"**；出生证＝实片台账 ⑪ + loudnorm 静默回退 dynamic 调研，全程记录 `docs/响度专项-调研与方案讨论-v0.1.md`）：

- **四唯一入口+共享内核**：`loud_measure.py`（ebur128 验收口径 I/TP/LRA 全实测；无 ffmpeg=结构化 capability_missing exit 2，不出估计数——人不得代填）；`loud_plan.py`（loudnorm pass1 规划口径四实测喂回 measured_* 零换算 + **linear=true 前提先算后放行**——官方文档 8.97：条件不满足时滤镜静默退回 dynamic 不报错，这是专员存在的理由；不可行=blocked 落盘摊开 exit 1 + 可修数值出路三选（提 TP/降目标/先压缩，ffmpeg-normalize 算术升格为罢工）；**ceilingLufs 素材响度天花板永远给出**＝G2 配音披露数据源；目标必须 `--profile video|podcast` 或显式三件套，半默认/混给/缺目标一律拒——⑧ 口径继承）；`loud_verify.py`（独立 ebur128 复测成片，对账 目标±1.0 LU 与 TP 上限+0.3 余量，plan 身份不符/非 ready 拒）；`loud_echo.py`（固定表格卡，呈现层零算术、数据逐字取产物、卡尾出处行——⑤ 防手制卡先例，非本专员产物拒渲染）。
- **唯一事实源合同** `references/loudness-contract.md`：量纲四分（LUFS 平均有多响／dBTP 会不会爆／LU 动态宽度／dB 只准表相对增益，禁混称"分贝"）；目标档表（video −14/TP −1.5/LRA 9＝现行 g4 实链验证值；podcast −16/−2/7＝ffmpeg-normalize 预设调研值；新档须带出处）；验收闸常数如实声明非隐藏默认；偏差三成因排查序；**§8 接线说明书＝届时蓝本（G2 天花板披露→G3 双式记账→G4 两遍线性+超差罢工→G5 loudness-audit 必过），当前未接线、任何节点门禁不得引用本专员产物作批准依据**。
- **测试**：36 例五套件逐文件全绿——物理阶梯锁（振幅减半=集成响度精确降 6.02 LU±0.4）、双引擎互证（同文件 loudnorm 与 ebur128 读数 ±0.5 内，谁漂当场现形）、端到端闭环（quiet 源→ready 规划→**按 chain 真渲染**→独立复测 passed）、拒绝面（半默认/身份不符/blocked 验收/缺件）。自证轮抓到：本机 lavfi `sine` 源默认峰值 ≈−18 dBFS（volumedetect/loudnorm/ebur128 三表同读数=源非尺）——教训"绝对值不许想当然"入已知限制，迁移新宿主照跑阶梯锁验表。
- **omni 活体试验**（"第二只耳朵"验色）：`bl omni --model qwen3.8-omni-flash --video <unicorn 交付包 v0.3 成片 39 秒> --text-only` 一次过——三项判断全带时间码（人声逐段稳定；两个最危险音效簇 0:13–0:16/0:30–0:33 无掩蔽；音画逐段对账），并**主动发现 1–2 秒音画错位**（0:11–0:16 话音讲"独角分裂 V 字"，V 字特写实际在 0:09–0:10）。结论：观察类环节升级成色属实（接线工单带此依据）；纪律不变——模型意见永不充当数值闸，该错位以听感意见入账、不推翻已批准交付。响应存档 `/Users/chuanzhangbigye/工作/WorkSpace/响度-omni试验-v0.1/`。
- **验证**：发版前 **45 测试文件逐文件单跑全绿**（2 例既有环境 skip 如实标注）、py3.9 全编译零错、8 项目 state 读盘正常；**本版零节点脚本改动**——门禁/校验器/装配线一字未动，历史封存包不受影响（无需重验）。
- **已知限制**：专员**未接线**（接线工单等用户口令，蓝本=合同 §8；问题 2 闸口正式生效与问题 4 披露方式届时拍板）；omni 审听接入观察类环节同样在接线轮议；Mimosa 完整扫描结论仍未取得，**不宣称项目安全**。

## v1.7.1 — 2026-09-28 — **帧率与合同真实性修补版本**

发布范围＝转场实跑 `unicorn-gundam-transition-001` 测后台账 ⑦⑧⑨⑩ 修复批（`aa0609e`→`6525b84` 七笔，用户 09-24 裁决口径：**"有问题就卡住，或者跟随源素材，不要随便用一个默认值，不能偷偷干"**）＋⑪ 响度开放项入册。本版发版起执行用户新规：**主干有实质更新即发版打 tag，不攒未版本化批次**。

- **⑧乙＋⑨ 帧率单一字段统一、静默默认全删**：编辑计划顶层 `fps` 为唯一机器位置（`editPlan.fps` 机械拒收）；`g4_prepare` 缺即罢工；`g4_render`/`g4_assemble` 的 default-24 分支删除，manifest 无 `targetFps` 且无显式 `--fps` 拒办；`g4_validate --fps` 死参数改活——段渲染文件实测 `r_frame_rate` 对账批准帧率（±0.1）。24fps 事故链的 G4 段闸门自此补齐。
- **⑧甲＋⑨ G3 源头闸（双式记账）**：`validate_g3_plan` 强制顶层 fps 正整数 + `packagingDecisions.fps == plan.fps`——卡上说 X、机器渲 X，不等=拒批；卡片纪律=源帧率作建议预选值，非机器自动跟随（g3-choice-cards 新增「帧率双式记账」「字幕轴 G3 硬握手」两节，包装决定逐项清单补帧率行）。
- **⑧丙 末道闸不可跳过**：`g5_validate --media` 帧率对账缺声明不再静默跳过——export-config 缺 `video.fps` 直接报错（旧代码 `if expected_fps and …` 正是 24fps 成片钻过的空子）；对账提为纯函数 `fps_reconciliation_error` 三态单元锁死（缺声明=错／容差通过／偏差或探测失败=错）。本跑当年靠人工发现的 24fps，自此机器自抓。
- **⑦甲 字幕轴 G3 硬握手**：包装决定引用字幕轴必须带 `subtitleCheckRef`——报告 skill/purpose 身份（subtitle-expert / subtitle_check_srt）、`status=passed`、报告 `sha256`==现场重算轴文件哈希，缺／过期／未过三死路各一负例（G3 套件 52 例，含新 7 例）。
- **⑦乙 继承产物重检规则**：material-pack-intake 边界规则 7——从旧项目克隆／沿用的任何产物，进入批准依据前必须按当前版本校验器／专员握手重跑落报告（洗 ID 不洗内容＝实跑照搬旧字幕轴 50ms 重叠直到 G5 才拦的出生证教训）。
- **⑩ 修订轮合同重锁通道**：新唯一入口 `skill/music-expert/scripts/music_mix_contract_rebind.py`——reopen-g3 重批计划后、重跑 G4 前**再生同参数新版混音合同**：参数逐字段深拷贝无覆盖入口（机器自证 `comparable` 相等）、只重锁 `evidence.planSha256`、BGM 音频字节复验不符拒锁（变音乐就不是重锁场景）、版本自增永不覆盖（㉘）、`rebind` 出处块如实登记 from/reason/at；`g5_audit_bgm_chain` 零改动自然吃新版合同。合同 reopen 节钉死：**手改旧合同＝伪造，禁止；长期红灯披露不是稳态**。历史封包按 R3 政策不追溯。
- **⑪ 响度开放项入册**：现行三层规则（口播目标 −14 LUFS／TP −1.5；BGM 垫床 −12dB＋句级 duck −6dB，窗口取对齐产物；amix `normalize=0`、源音频不进成片声轨）＋待决三点（偏差是否升级硬门禁、目标值口径、G2 素材天花板披露）记入项目问题清单；09-28 用户令**立项响度专项**（⑪ 入册为 09-24；归属调研与方案讨论见 docs 与交接文档）。
- **验证**：发版前全量回归 **40 测试文件逐文件单跑全绿**（rebind 新套件 4 例、G3 52 例、G4 contract/assemble/render-profile 夹具随新合同迁移、G5 帧率三态新例）；两封存包在新闸下复验 `status=valid`——`unicorn 交付包-v0.3` 与 sinjuku 基线包，规则收紧不追红历史。
- **已知限制**：⑪ 响度三点待决（专项设计轮进行中）；重锁通道暂只有单元夹具背书、未在真实修订轮实机走过；平台融入适配（sourceAsset 合同、gN 前缀改名）仍按 09-21 决定挂起；Mimosa 完整扫描结论仍未取得（各 commit 带 library_source_unavailable 兼容放行提示），**不宣称项目安全**。

## v1.7.0 — 2026-09-24 — **门禁真实性版本**

发布范围＝Leader 反馈轮三件套 R1/R2/R3（`c344757`/`4bccc36`/`7158424`，台账回填 `c11c6e6`/`17ee32e`/`c2c7ad4`）＋⑤ G3 卡出处机械校验（`7273c80`）＋转场流程首次实跑收口入库（`unicorn-gundam-transition-001` 全产物）：

- **R1 门禁不再只查文件存在**：G4/G5 approve 入口接入 `validate_g4_report/validate_g5_report`——非 JSON/invalid/张冠李戴/产物过期/缺指纹绑定一律 exit 2 阻断；G5 按报告所在目录逐件产物重算 sha256 对账（单条与 chapterClips 数组形态均吃下）；`g4_validate.py` 加 `--candidate`（报告绑候选成片指纹+ffprobe 时长 ±200ms 对账时间线，非同一版即 fail）。实盘冒烟第一时间抓到 sinjuku"登记哈希从未对同实物"真案——封存包不追溯改写、台账留记录。
- **R2 审批绑定被审文件指纹**：record-review 把审核卡+全部 basisRefs+全部 checklist evidenceRef 的 sha256 冻进快照 `basisHashes`（登记那一刻＝真人所见版本被绑定）；approve 关单前重算比对，变更/缺失点名文件阻断并指路"重渲卡→重登记→重确认"；approvalRef 豁免（批准文件关单时才写，合同如实写明）。《人工批准信任边界》入合同：CLI 无法密码学自证真人、本地信任根=宿主会话、**代录≠制造**、Proxima 接入后换可信审批事件只改 `approvalSource` 字段。
- **R3 随包样例自洽+盘上版本标记**：`test_g5_delivery` 新增 2 例——本版基线包（sinjuku）必须过当前校验（今后合同演进弄烂基线当场红）+六历史 G5 包各带 `contract-era.json` 机器可读版本标记（政策=禁删校验绕开、禁补造检查报告冒充迁移；只加标记不动封存内容）。她"六份均缺"核实一字不差：09-21 合同加严当晚 6 样例集体变红而无测试变红＝自洽层缺失。
- **⑤ G3 卡出处机械校验**（本实跑 G3 抓，用户令「模板统一更新」当场落刀）：review_gate 登记强制 `render_g3_review_card.py` 出处标记，手制卡 record-review 直接拒——「回显必须是固定表格卡片」从口头纪律升级为机器闸。
- **转场实跑首次全流程**（unicorn-gundam-transition-001，克隆自 unicorn-gundam-intro-001）：G0–G5 六门禁全过 completed，交付包 v0.3 封存 valid/internal_test（30fps · 0:38.832 · 四章节切片+SRT+字幕/转场/BGM 三份握手审计）。**reopen-g3 修订通道两次实战走通**（第 2 轮修 ⑦ 字幕 50ms 重叠、第 3 轮修 ⑧⑨ 成片 24fps 回归→fps:30 单一机器字段+预览免 flag 自证）；R1/R2 首战实盘有效（含 21 指纹全链重登记）。问题台账 ①–⑩ 入库；**⑩＝修订轮改写计划后与 BGM 混音合同指纹锁无重锁协议（bgm-chain-audit 15/16），测中不动刀、带披露封包**，与 ⑦⑧⑨ 修补案并批测后落刀。
- **验证**：发版前全量回归 **39 测试文件逐文件全绿**（含 R1 负向 11 例、R2 负向 8 例、⑤/R3 新例）；实跑六门禁逐字口令与批准记录盘上齐。
- **已知限制**：⑦（甲/乙）、⑧（甲/乙/丙）、⑨、⑩ 修补案未拍板（测后批次）；Mimosa 完整扫描结论仍未取得，不宣称项目安全。

## v1.6.0 — 2026-09-23 — **试装预览版本**

发布范围＝转场试装预览四批（`10422f4` 立骨／`bfa8493` G3 硬门禁／`2842d7c` 活体彩排收口／`3879e82` 观看页）＋同批挂账裁决（`3923f74` 清扫、`5eae66f` 推荐层转正）：

- **转场试装预览（先看后批）**：痛点=批准转场时看不到效果、必须整片渲完才知道（㉔ 颗粒叠化事故的手工小样无记录=反面教训）。`transition-expert/scripts/transition_preview.py` 对计划每个非硬切切点产低清无声小样（约两秒+上下文）。**防幻觉宪法=预览与成片代码同源**：入口复用 `transition_validate_plan.validate_plan` 与 `transition_directive.build_directive`（同 boundaries/offsets/extras 算术零新公式），裁剪/缩放/xfade/settb/黑场滤镜与 g4_render/g4_assemble 同式（跨专员零 import，`FormulaParityTests` 逐片段断言同构锁死）。**窗口被批准裁切钳制**：`[S−D/2−C, S+D/2+C]`、C=min(1200ms, 手柄富余)，永不展示批准裁切之外的画面；黑场档全额预留 D。渲染前源素材 sha 三方对账（evidence↔material-pack磁盘），不过=结构化 `blocked_previews` 带披露句，不猜不装。
- **G3 硬门禁（用户裁决：硬门禁+如实豁免）**：`validate_g3_callback` 新增对账——计划含非硬切转场而预览缺席=卡校验拒并点名切点；清单 `planSha256`≠当前计划=stale 拒（改版自动逼重跑）；小样/观看页文件缺失或 sha 不符=拒；Ref/Waiver 二选一；无转场计划不得挂预览；`audio` 必须 false。唯一豁免=`blocked_previews` 原文入卡并如实披露"你批准的是未见过的效果"，不许静默跳卡。G3 收据 basisRefs 挂清单路径（不新增 checklist id，㉙）。
- **回显呈现（用户 09-23 验收定案）**：`render_g3_review_card` 八列对账表一字未动，表后新增「转场试装预览（先看后批）」区——首行统一挂 **▶ 一页看全部**链接（用户拍板），另逐切点一行（类型·时长·成片窗口 m:ss.mmm·无声小样链接）。**《转场-预览观看页-v<M.N>.html》由脚本生成**：自包含内嵌播放器、与清单同目录同版号、呈现层零算术数据全取清单；布局规格=代码即规格，不另写文档（用户选，免两处不一致）。
- **产物合同**：《转场-预览清单-v<M.N>.json》schemaVersion 0.2——四输入哈希绑定（plan/evidence/hostProfile/mediaPack）+`viewerPage`/`projectId` 字段+逐条 `{boundary,type,durationMs,windowMs,file,probedLenMs,expectLenMs,sha256,renderArgs 全量入册可逐字重建}`；`next_versioned_path` 自增永不覆盖（㉘）；小样按边界 id 命名（弃人肉 A/B/C）；中间件删除。
- **活体彩排（sinjuku-intro-001 已批 G3 v0.6+87.6MB 真源，全局 WorkSpace）**：三小样实测时长=批准窗口分毫不差；中点帧与交付成片同镜对同混合观感；预览窗口中心=指令 offset+D/2 真中点——查实当年手工"平滑中点"帧实取在过渡起点，新预览比它准。如实入账：第三切点混合相位差 ≤100ms=成片多段 xfade 链文件取整累积漂移（小样从源直裁无此漂移），属观感层容差不阻塞（执行==指令由 G5 transition-audit 机器对账）。
- **同批挂账裁决**：转场词表定案四档（硬切/叠化/黑场入/黑场出）、第二批缓建；**推荐层转正**——三层分工入合同=编排出提案带【默认=推荐｜理由】、专员脚本零机器推荐只摊可行性事实、决定权在人逐切点；tiger《Infinity》不换曲+通用纪律（未清权资产须在用户可见环节带"会违反权益"人话标签）；远端仓库改名撤销（永久保留 Video-shipcut-Skill）。
- **验证**：全量回归 **39 个测试文件逐文件单跑全绿**（预览套件 11 例、门禁卡套件 26 例，含观看页自包含/死链拒/旧清单兼容缺席）；彩排 v0.2 重跑+模拟审批卡经用户视角验收通过。
- **已知限制**：小样不复现源字幕遮蔽等包装层（只验转场观感，卡上明写）；无声是裁决非缺陷（混音属 G4）；Mimosa 完整扫描结论仍未取得（各 commit 带 library_source_unavailable 兼容放行提示），不宣称项目安全。

## v1.5.0 — 2026-09-23 — **转场专员版本**

发布范围＝transition-expert 立册+执行链三批（`9bf3d08`/`0b496ad`/`c0127fd`）＋首次全链实片验收（验收003，sinjuku-intro-001 G0–G5 闭环）＋29 条测后修复批次（`873c128` 代码／`a6f4ca2` 合同／`5d81ee2` 产物入库）：

- **transition-expert 插件专员 No.3**（出生证=G3 八列卡"转场指令"列挂空合同：字段只活在回显层、G4 零实现、002 批准过"叠化/按 G4 微调"含糊句）：受控词表四档（硬切缺省/叠化/黑场入/黑场出，wipe 预留）；三定律=**音不动画面服从、手柄回填网格不变、缺料摊牌永不静默降级**；G3 词表卡（卡-计划逐字对账）→批准后确定性派生《转场执行指令》（三哈希绑定）→G4 prepare 无指令拒办/render 按指令扩切手柄/assemble xfade 链+黑场→report 反查"实际做的==批准的"→G5 `transition-audit.json` 入交付包 REQUIRED+转场中点必检帧。
- **实片验收（sinjuku-intro-001，验收003）**：新安洲介绍 170.167s/27 段/3 处叠化（internal_test，BGM LOW-PHONK/Freesound 清权轨，AI 配音 longtian_v3），六门禁全过、交付包 v0.1 `--media` valid。观感裁决当场发生（㉔）：xfade 的 `dissolve` 实为噪声抖动式混合（中点颗粒感），"叠化"映射改 `fade`（平滑交叉淡化），探测合同按观感词义对齐；㉖ 终审卡"同卡双义"事故（推荐 3 叠化 vs 关单句按现状）→ reopen→v0.6 重批→G3/G4 重走，催生唯一关单口令新规。
- **29 条测后修复（零开放）**：代码——㉕ 审批口令归一化扩"单一无条件确认从句"自然句形（条件/否定/祈使/转折/疑问/他节点引用仍拒）、㉘ 专员产物 `next_versioned_path` 版本自增永不覆盖、㉒ 长链中段 xfade 时基当场修（junction 两侧 settb=AVTB）+补盲区复现用例、㉗ reopen-g3 接受 G4/G5 跨节点回退+用例、⑯ `validate_g3_plan` 机器强制连续网格、⑩⑨ 解释器诊断与单跑口径、音乐侧①②④⑤⑥⑦⑧；合同——⑰ 黑场前置条件+标准出路、⑱⑳㉑ G3 瓦片只定向/结构校验先行+帧缓存/编排逐切点主动提案、㉓ 包装描述与帧证据同屏+G5 逐字核对关口、⑭ 配音清单 schema/⑪ 核证降级链/⑬ 语速校准/⑫ 选曲时长机器比对、⑲ 字幕宽度模型权威、style-guide v1.2（⑮ 全卡默认推荐＋㉖ 唯一关单口令语义）、㉙ G5 收据三行速查。逐条落点见 `工作台/sinjuku-intro-001/验收003-问题清单.md`。
- **验证**：全量回归 **38 个测试文件逐文件单跑全绿**（⑨ 教训立为口径：合跑路径注入可掩盖缺陷）；G5 交付包 valid；转场中点帧目视=平滑双影、网格 170.200s（帧取整）零位移、响度与硬切版一致。
- **已知限制**：㉓ 描述字段仍无机器对账（只有卡片同屏+G5 人工关口双堵）；转场经验库第一批不建（冻结律，待第二个转场项目数据）；Mimosa 完整扫描结论未取得（本批各 commit 均带 library_source_unavailable 提示按兼容策略放行），不宣称项目安全。

## v1.4.0 — 2026-09-21 — **字幕专员版本**

发布范围＝002 验收测后裁决 14 条批次 ＋ "底座+插件"定案 ＋ subtitle-expert 剥出立册与彻底化（提交 `b7cc9c2`…`603be16`）：

- **002 十四条裁决批次收口**（批 A `7ba993c`／批 B `e2c21b4`／批 C `abaf3c1`／收口 `dc9b2f1`）：⑧ 渲染器能力档 `autoWrap`（缺省保守档=本机 libass 不自动断 CJK 长行，绿灯必须建立在所选能力档之上——002 唯一用户可见级高危根治）、⑤ validate_g3_plan 批量报错、⑦ approve 重读收据比对快照（changed since record-review）、⑨ editPlan.fps 经 manifest targetFps 贯通 prepare→render→assemble（`fpsSource` 溯源）、③ Freesound 时长两档（放宽重试+`durationShortfall` 显式标注，决策权在卡）、④ 候选耗尽四选一主动脱出、⑪⑫⑬⑭ 合同兑现（ROI 判读纪律/REQUIRED 对账/finishedAt 语义/mpdecimate 判读链）、① 新对话开场只报磁盘事实成文（AGENTS 路由 6+operator-dialogue 规则 6）、⑥⑩ 口径。② 早已修，销账。逐条去向=002 问题清单尾部《测后裁决执行台账》。
- **music-expert 加固**（`b7cc9c2`）：环境变量通用名补齐（`MUSIC_EXPERT_*` 优先、`P0C_*` 兼容别名）；两检索器 SSRF URL 白名单守卫（Mimosa L3 拦截后修复，含 3 组守卫测试）。
- **"底座+插件"定案**（用户 2026-09-21）：节点专员串联=底座，领域专员=可迁移插件；插件四标准=CLI+产物文件握手（零跨节点 import）/依赖全环境变量（通用名优先、禁硬编码路径）/合同自带接线说明书/缺能力结构化 blocked 或保守默认。
- **subtitle-expert 剥出立册**（`b43eb12`/`35e0cbc`，插件专员 No.2，出生证=002 问题⑧㉖㊍）：布局校验器自 video-edit-plan 迁入、style-contract 自 local-video-render 迁入、新增渲染器能力档探测 `subtitle_probe_renderer.py`；layout/qa 两合同＋接线说明书立为唯一事实源（`references/layout-contract.md`）。章程三块"新引擎"防过度设计未建，出入如实记于章程《执行记录》。
- **彻底化批**（`dee6568`，用户复审"剥离出来了就彻底一点，不要节点里有一点专员里有一点"）：G4 内嵌的章节卡 cue 修剪（`trim_ass_cues`+ASS 时基解析）迁入专员 `subtitle_trim_cues.py`，G4 改 CLI 调用、只烧派生件（批准源永不改动，装配记录 `subtitleCuesTrimmed` 语义不变）；G5 私有 SRT 正则删除，改产物握手——交付包新增必备件 `subtitle-srt-check.json`（专员 `subtitle_check_srt.py` 报告，validator 校验 status=passed＋sha256 新鲜度）；生成纪律入机验：`--srt` 逐 cue 对时对文（10× 时基漂移必拒，㊍ 锁死点）、新增 `--source` 对 G2 口播句子 JSON 逐块对齐（一条批准口播块=一个排版块）、事件重叠判"强调拆层"；修探测真缺陷——libass 版本正则误把 configuration 行 `--enable-libass --enable-libfreetype` 的 flag 当版本号（改为只认独立版本行，拿不到如实 unknown）。
- **展示资产**：总流程图 v0.2 定稿并入库上 GitHub（`43421d5`，补 确认G2 链＋2x 高清导出）。
- **验证**：subtitle-expert 套件 12→33 全绿；002 实产物活体复验贯穿 G3/G4/G5/探测（13 events 全中、漂移拒、trim 源零改动、复检 passed）；全量回归 9 套全绿。
- **标签**：本版按用户拍板走数字版本系列（`v1.4.0`，annotated）；此前误用专名 tag `subtitle-expert` 同日撤销删除。

## v1.3.0 — 2026-09-18 — **BGM完善版本**

发布范围＝以下四批（单卡交互合同、主线接线①G0/②G1、music-expert N10+锚定打分）＋发布期内追加：

- **N8 测后裁决 26 条四批修复**（52c072c/27c6815/c6d5f09/19d2b9d）：validate_g3_plan 批量报错、评审/审批模式对称、g4_prepare 工作台守卫、drawtext 字形覆盖预检（TTC 首-face 陷阱红线）、《交付包组件 Schema》唯一事实源、口令归一化下沉等；回归 7 套全绿。
- **找乐通道路由定案**（d5ae193）：对外=Freesound 默认轨、个人/内测=网易云可留，通道在 G1 末回显卡可切换；**Freesound 首次活体接通**（5709f21）：CC URL 许可分类器修复 + preview 键名/短链派生漂移修复 + 3 组回归。
- **G0 卡 BGM 通道预告**（19c862c）：问题 5 选项 B 写明检索通道与切换点。
- **正式验收录制闭环**（方案 A）：psycho-zaku-intro-002 G0–G5 六门禁全过（09-18 `确认G5`），交付包 v0.1 封存 valid/completed，`确认交付≠逐条接受`语义走完；`验收002-问题清单.md` 14 条落档（高危=⑧ CJK 断行布局校验器与 libass 渲染能力不一致——绿灯≠渲染正确）。
- 已知限制：002 项目 107MiB 源素材超 GitHub 单文件上限不入库（与 tiger 同法 `.gitignore`，SHA 已录 G0 manifest/素材包，凭证据可重取）。

### v1.3.0 批次 · 单卡交互合同（用户 2026-09-11 定案，N8 活测产物）

- **每节点仅一次最终回显**：中途偏好类决策点（标题/角度/检索词/挑曲/风格参数）不再独立停靠提问，Agent 预选推荐项、以【默认=推荐｜依据】并入节点最终回显卡；用户否决哪条只重跑哪条。门禁口令（确认G1…确认G5）一个不减。
- **归属如实**：默认项被确认记"用户验收推荐默认项"，不得写成"用户选择"；G0 开工单五问、G3 目标主体身份判定、G5 人工验收**永不预选**。
- **默认选曲规则**：默认项=听觉模型 A/B 判"能使用"中的最高适配（N8 证据：机器分 0.881 居首者模型判 2/10——纯机器分不得当推荐）；capability_missing 时挑曲停靠点复活问用户。A/B 试听笔记从"可选"升格为"做默认选曲的必备输入"。
- **体裁标签红线**（问题⑫教训）：给未被任何耳朵听过的曲子写风格词必须标"未试听推测"；参考曲在场先跑绝对笔记、词以笔记原话为准。
- **最终回显样式指南 v1.0**（问题⑰，同日追加定案）：`p0-c-pipeline/references/final-echo-style-guide.md`——六节点门禁卡统一五段骨架（一句话结论→决策点≤两行/条→待办与事实状态→证据与产物[机器字段唯一容身处+项目绝对根路径]→操作区）+ 禁词表（机器枚举值/内部黑话/SHA 等不得上正文①–③段）；专员卡与 G3 八列硬校验不改格式、按内联原则进④区；冲突以门禁合同为准。接缝：operator-dialogue 第 1 条、p0-c-pipeline SKILL、g1-choice-cards 呈报指向。**v1.1（同日用户复审）**：决策点呈报改"问题→选项列全→【默认已选：X｜依据】"三小节，题面与选项先行、默认盖章在后。
- 落点：`p0-c-pipeline/references/operator-dialogue.md`（单卡合同节）+ 两个 SKILL；`video-edit-plan`（g1-choice-cards、g1-direction-guide、SKILL 找乐编排 2/3/4 步）；`music-expert`（SKILL 2.6/2.7、search-terms-contract）。纯合同/文档改动，脚本零改动，回归 27/27 不变。

### v1.3.0 批次 · 主线接线批次②：G1 末找乐编排 + 槽一致性后门封堵

- 堵静默改主意后门：`g1_direction.py validate` 新增 G0 `bgm` 槽一致性检查——方向简报的 `bgmDecision` 与槽冲突即拒（改主意必须先走 `pipeline_state.py bgm-choice` 留痕）；G1 只能继承槽，不能覆盖槽。
- video-edit-plan SKILL 新增"G1 末：找乐编排"节（严守节点专员=编排+卡片、音乐能力全归 music-expert 的分工）：查库先行零成本 → 检索词卡（偏好原话第一优先、不设口令）→ netease 找候选 → 锚定排序 → omni 试听笔记（可选，能力缺失如实提示）→ 候选歌卡（侵权横幅必显）→ 用户挑曲一句即决定（原话入 verdicts）→ 官方渠道整轨登记 → bgm-choice 翻槽 → **初次分析统一 G1** 补三哈希链+档案写回。停止条件与 G2/G3 硬门禁闭环。
- 测试：g1_direction +1（不一致拒、一致继承放行）。

### v1.3.0 批次 · 主线接线批次①：G0 待找乐槽（接上 music-expert 的第一步）

- 兑现 g0-policy 的"下游提醒"空头支票：G0 的 BGM 声明成为机器事实全程携带——模板新增可选 `BGM preference:`（用户口头偏好**原话**，检索词推导第一优先输入）；`material_pack.py register` 把 `bgm` 段（decision/preference/libraryPending/clearCondition）写进 material-pack.json；`pipeline_state.py init` 抬进 state.bgm；`status` 在槽未清时输出 reminder。
- 新命令 `pipeline_state.py bgm-choice`：翻槽唯一入口——翻到 `provided` 必须带登记证据（无证据拒绝），`no_bgm` 免证据；每次翻槽 append `history`，槽不得靠聊天清空。
- 硬门禁（N9 顺序）：`libraryPending` 期间 **G2/G3 approve 直接拒绝**；`validate` 检出"use_library_later 但 07 出现文件"的矛盾。
- 文档同步：pipeline-state-contract 增 BGM slot 节、p0-c-pipeline SKILL 增机器携带说明+硬门禁、g0-start-form/g0-policy 措辞兑现；测试 pipeline +2、material-pack +2（含模板提示行不算用户输入）。

### v1.3.0 批次 · music-expert 找乐（N10）+ 锚定打分

- 检索词生成合同落地（`music_search_terms.py`，专员侧 I/O 固化：时长下限由时间线毫秒向上取整，风格简报 BPM 过滤；口头偏好＞主题翻译＞简报锚定）。
- 网易云搜索适配 `music_search_netease.py`（试听选型轨道三：候选写死 `uncleared-platform-catalog`/`internal_test`，风控结构化 blocked，绝不谎称许可；下载封顶=入选数）。
- 打分许可语义定案：`uncleared-platform-catalog` 在 internal_test 画像不压分（登记由链子把关），更严边界 ×0.3 重罚（专员自测抓出的结构性零通过）。
- 回显侵权可见性：逐条 `infringementRisk` + 顶部 ⚠ 横幅 + 人读推荐回显卡 `BGM-推荐回显-v0.1.md`。
- **锚定打分**（用户试听反馈"有不适配"）：画像带 `styleBrief` 时 BPM 改亲缘度（半速/倍速折叠容差）、新增能量曲线相似度（16 桶重采样+min-max 归一），段落数让权；无简报旧行为不变。zaku 复测：10 首由全部并列 1.000 拉开为 0.896–0.738 梯度，不贴合曲目（十面埋伏/生龙）降位。
- **模型试听笔记层**（`music_listen_omni.py` + `listen-notes-contract.md`，用户定案："没有听觉分析能力不能瞎编，必须明确提示用户"）：先探测音频模型能力（CLI 存在+API key），缺失 → 结构化 `capability_missing`+回显卡明写"此处不编造"；在场 → 逐首与参照曲 A/B 听，情调差距/贴合度笔记进卡；调用失败如实进 `partialFailures`；只听短名单（`--max-tracks` 封顶）控制计费；后端可换（百炼 omni/Gemini/本地开源权重）。首跑即真实拦下一例 PATH 缺失，未编造一字。
- **音乐经验库落地**（`experience/music/` + 唯一写入口 `music_library.py`，用户定址定案）：一首歌一档案，身份=音频 SHA-256；四层次序（track.json 身份卡含 license 红绿灯/acoustic.json 高潮低谷时间戳/listen.md 模型绝对笔记带模型+提示词版本戳/verdicts.jsonl 人类裁决 append-only）；风格锚并入为 `roles: anchor`，不再单设锚库。三条红线入 README：音频本体永不进库（凭证据重取+SHA 验身）、license 只升不降（grant 是唯一翻灯通道）、相对评价不做库事实。试听笔记层新增 `--absolute --library`：同模型同提示词命中零成本复用、只有没听过的才调用、听完自动写回。首批入库 4 条（LOW=锚+绿灯；Devil Game/Gone Bad/弥渡山歌=未清权红灯），活体绝对属性听写 4/4 成功——并纠正了文本检索的假阳性：Devil Game 实为 Hardstyle 非 phonk（标题党，曲名命中≠风格命中）。
- 回归 27/27（sourcing 锚定 3 例；listen"无能力不编造"3 例+复用零成本 1 例；library 身份/红绿灯/过期不冒充 6 例）。节点侧定案记录：BGM 初次分析统一放 G1、G0 只登记（待节点批次，见交接文档 §0）。

## v1.2.0 — 2026-09-10 — music-expert 落地与 BGM 全链接线

首个走完 G0–G5 全流程闭环的真项目（zaku-intro-001）在本版诞生；BGM 专员完成从"做好"到"接上"的三段接线（N5/N6/N7），确立"领域能力归专员、节点型专员只管编排"的架构方向（总账㉜、接线方案 §6）。

### music-expert support skill（2026-09-08 建，本版发布）

- 新增独立 support skill `skill/music-expert/`（`$music-expert`）：覆盖基线总账 ⑯（已验证）与 ⑫（部分推进，找乐自动轨道待 `P0C_FREESOUND_TOKEN` 真实取证）。
- 确定性分析引擎 `music_analyze.py`：librosa 节拍/起音 + 能量分段 + ebur128 响度，产出《BGM 分析报告》（含卡点表）与风格简报；受控运行时 `P0C_MUSIC_RUNTIME_HOME`、`cacheKey` 复用、缺依赖结构化 blocked。
- 双轨找乐：`music_search_freesound.py`（仅 CC0/CC-BY、授权证据链、解码探针，缺 token 不静默换源）、`music_register_candidate.py`（人工许可登记）；`music_recommend.py` 画像打分、候选不足显式上报不硬凑；标签粗匹配（`music_tags.py`，3 维 18 标签受控词表）。选型与可达性实测固化在 `references/library-probes.md`。

### BGM 三段接线（N5/N6/N7）与 G2 蓝图（N9）

- **N5/N9**：`music_align.py` 对齐/蓝图双模式（轨偏移/高潮锚点/卡点吸附/逐句 ducking 区间）；G2 门禁 3.5 节蓝图循环（BGM 先行节拍蓝图，时间码三层身份：蓝图窗口=参考、目标码=意图、实测码=事实）；`music_echo.py` 分析回显卡固化。
- **N6（G4 混音合同链）**：`music_mix_plan.py` 出《BGM-混音合同》——三重哈希对账（BGM 文件↔计划 bgmPlan↔分析报告缓存键↔对齐产物）+ **可听窗守卫**（在位预估电平出 [人声目标−18, 目标−6] LUFS 拒绝出合同）；`g4_assemble.py` 无合同拒混 BGM、逐字执行合同、装配后**实测在位电平**与预估对账（>3 LU 或 <−33 拒绝交付）。§6-② 拍板固定衰减 dB，zaku 终值垫底 −8/压低 4。
- **N7（G5 链审计）**：`g5_audit_bgm_chain.py` 从装配记录 `bgmMix` 反向重放 G0 登记→素材包→G3 计划→对齐/报告→混音合同→装配记录，14 项检查（逐文件重算 SHA-256、参数逐字比对、可听窗算术复核、实测漂移、许可与分发边界一致性）。

### G4 实跑设防（zaku 教训，总账㉜）

- 源字幕遮蔽合同（`g4_render.py --source-mask`，比例带 + 切片内窗口 enable）；章节卡合同 `yRatio` 通道（默认居中向后兼容，修复硬编码正中违反布局合同）；旁白标准压限归一链（`--normalize-narration-lufs`，渲染后 ebur128 实测入装配记录，发现㊌）；在位电平测量防挂死（输入侧 `-t` 封顶 + 超时）。
- 纪律沉淀：遮蔽类处理表必须带实测像素/时间出处；门禁呈报必须全文内联。

### 管线与回显

- G2 回显格式定稿（四卡+自动回显+排版稿卡，标准样例 `skill/media-evidence-prep/references/examples/G2-完整回显样例-zaku.md`）。
- 批准口令脚本级归一（`确认G5`/`确定 G4` 等变体自动规范化、逐字原话留痕；带前缀整句拒收）。
- G5 交付包合同不变；`human-review-decision.json` 显式区分"确认交付"与"逐条接受警告"两种语义（本版为记录惯例，卡片拆问待后续）。

### 验收

- 全量回归 23/23（新增 test_music_align 24 例、test_music_mix_plan 10 例、test_g5_audit_bgm_chain 6 例等）；zaku-intro-001 全流程闭环（六节点全 approved，`g5_validate_delivery.py --media` valid 0 错误，BGM 链审计 14/14）作为本版活体证据入库。

## v1.1.0 — 2026-09-04

将 leader 审阅后的 P0-C v1.1.0 交付补丁合回主仓，并统一命名。补丁内容源自 TASK-050"上能同创智能剪辑 Demo"的实际渲染与人工评审。

### 命名统一

- 产品名 Video-shipcut → P0-C；编排入口 Skill `video-shipcut-pipeline` → `p0-c-pipeline`（目录与 `$` 调用名同步）。
- 环境变量前缀 `SHIPCUT_*` → `P0C_*`。
- 根文档（AGENTS、PRD、README、目录规范、历史调研）与流程图同步更名；流程图改用 SVG 作为 README 主图，旧 PNG（含旧名称，无法从 SVG 无损再生）移除，可从 git 历史找回。

### 工具链跨平台

- 运行依赖从"仅 Windows + `D:\WorkTool`"改为 macOS/Windows/Linux 通用：优先从 `PATH` 解析 FFmpeg/Python，`P0C_*` 变量为可选覆盖。
- Python 最低版本明确为 3.10（脚本使用 PEP 604 联合类型语法），推荐 3.12。
- 测试在缺少 FFmpeg 时优雅跳过（`test_engine_cli.py`）。

### G4 成片质量补丁（本次核心）

- 新增 `skill/local-video-render/references/demo-quality-patch.md`：画幅策略、clean master 不变量、封面、章节卡节奏、句子级旁白、字幕对齐实际音频、分轨与 ducking、清晰度、授权记录、机器/人工 QA。
- `render-contract.md` 增加 v1.1 扩展字段（`aspectRatioPolicy`、`cover`、`narration`、`captions`、`audio` 等），示例见 `examples/g4-render-profile.example.json`。
- `g4_render.py`：默认 `preserve_source`，用 ffprobe 从首个批准源探测画幅；`explicit` 必须同时给宽高；`--crop-bottom-ratio` 默认从 0.14 改为 0。
- `g4_validate.py`：宽高改为可选，未指定时自动检测分段画幅一致性。
- 新增 `tests/test_g4_render_profile.py`。

### 上下游合同传导

- G3（`video-edit-plan`）：含封面/章节卡/旁白/固定字幕的项目，计划必须预登记画幅策略、封面帧、句子边界、字幕样式、ducking 策略与 clean master 输入，否则保持 `review_required`。
- G5（`media-qa-delivery`）：demo-quality-patch 的机器 QA 与人工 QA 纳入交付门禁，缺任一必需证据不得报告完成。

## v0.1 — 2026-09-04

初始发布：G0–G5 六节点流水线 Skill 与示例项目 `unicorn-gundam-intro-001`。
