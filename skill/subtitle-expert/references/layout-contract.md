# 字幕布局合同与渲染能力档（layout-contract）

字幕领域的唯一事实源：G3 布局合同的机器形状、断行生成规则、渲染器能力档语义与校验入口。节点专员只调用与消费，不改规则（用户 2026-09-21 定案剥出，002 问题⑧㉖㊍为出生证）。

## 合同形状（G3 产物，validator 逐字校验）

```json
{
  "schemaVersion": "0.1",
  "node": "G3",
  "projectId": "<项目 ID>",
  "lanes": {
    "narration": {
      "zone": "70-84% height",
      "fontsize": 14,
      "maxLines": 2,
      "autoWrap": false
    }
  }
}
```

- `fontsize`/`maxLines`：正数/正整数，ASS 样式字号必须与合同一致（漂移即违规，㉖）。
- **`autoWrap`（渲染器能力档，002-⑧）**：**缺省=false=保守档**——假设渲染器不会自动断 CJK 长行（本机 libass 实测行为）。只有当 `subtitle_probe_renderer.py` 产出的能力档带**实测证据**（`--auto-wrap-evidence`）时，合同才允许写 `true`。无证据的 true 就是编造能力，禁止。

## 校验入口（唯一）

```bash
python skill/subtitle-expert/scripts/subtitle_validate_layout.py --ass <G3-字幕时间轴.ass> --layout <G3-字幕布局合同.json> [--srt <subtitles.srt>]
```

保守档下的判定模型：空格是唯一合法断点；**任何不可断且超宽的连续段（典型为无空格中文长句）直接判违规**（渲染器会裁切而不是折行）；行数=`\N` 硬断行数+空格折行数，超 `maxLines` 违规。`--srt` 附带交付副本格式校验（`HH:MM:SS,mmm` 零填充、单调不重叠、与 ASS 逐 cue 对齐，㊍）。

## 生成规则（G3 写 ASS/SRT 时执行）

1. **一条口播一排版块**；超一行宽度时在**自然语义边界**插显式 `\N`，两行均衡，单行 ≤27.5 全角当量（002 实测绕法转正）。
2. ASS 为样式母版，SRT 为交付副本，**同一数据源派生**：SRT 时基=ASS 百分秒 ×10 零填充，`\N` 转真实换行（㊍的根治）。
3. 关键词强调用同一字幕块内的富文本 tag，禁止拆独立图层。
4. 校验未通过必须重新语义断行，不得靠渲染器自动折行兜底、不得缩字号救。

## 接线说明书（本专员与六节点的全部接缝）

| 节点 | 接缝 | 消费/产出 |
|---|---|---|
| G2 | 字幕文本权威源 | 专员**不碰**口播稿内容层；转写/口播稿经 G2 批准后进 G3 作字幕文本唯一来源 |
| G3 | 布局合同+时间轴生成 | 探能力档（probe）→ 写合同与 ASS/SRT → `subtitle_validate_layout.py` 过检 → 产物入 G3 最终回显与门禁收据 `subtitle_timeline` 项 |
| G4 | 烧录执行 | `g4_assemble.py --subtitle-ass` 逐字执行已批准 ASS；样式排版策略见 `style-contract.md`；字体字形覆盖由 G4 ㉛ 预检守门（drawtext 路线），字幕烧录走 libass |
| G5 | 字幕面 QA | `references/qa-contract.md`（越界 ROI 判读纪律⑪、SRT 交付格式）；收据 `check_frames` 含字幕检查帧 |

改任一接缝先改本合同；节点侧文档与本合同冲突时以本合同为准。
