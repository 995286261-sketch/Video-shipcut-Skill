# Material Pack Workflow

This is the reusable no-prompt intake flow. The user prepares the human input layer; the Agent creates and owns the technical layer. Do not ask users to prepare timecodes, hashes, EDL, SRT, JSON, or editing project files.

## 1. User Creates the Pack

Copy `assets/material-pack-template/` and complete only the following.

| Item | User supplies | Required? |
| --- | --- | --- |
| `01_需求说明.md` | Topic, target audience, duration range, output orientation, style intent, prohibited claims, and a voice brief | Yes |
| `02_原始素材/` | Original local video, image, document, or audio files. No pre-cut or burned-in derivatives when originals are available. | Yes |
| `03_事实依据/` | Product facts, approved copy, manuals, PDFs, screenshots, transcripts, or an approved narration draft if one exists | Strongly recommended |
| `04_授权说明.md` | Source, allowed usage, restrictions, and unknown rights marked as unknown | Yes |
| `05_风格参考/` | 当前项目专用的参考媒体或链接/说明，并明确其只用于风格规则；需要跨项目复用时，在新项目重新登记为该项目的参考输入，不从归档或旧工作区读取 | Optional |
| `06_品牌资产/` | Logo, palette, fonts, forbidden expressions | Optional |
| `07_授权音频/` | Locally supplied BGM/SFX with permitted use stated | Optional; its absence does not decide BGM. G0 must record provided / use_library_later / no_bgm. |

## 2. Agent Registers the Pack

The Agent must then:

1. Validate the seven-entry layout and preserve source files unchanged.
2. Compute hashes and basic file metadata, then write `material-pack.json`. Media probing belongs to `$media-evidence-prep`.
3. Keep technical analysis needed for registration outside the pack, under a caller-selected workspace.
4. Report whether the pack is complete, which optional entries are absent, and which source/authorization fields are unknown.
5. Hand off the pack root and its `material-pack.json` to the downstream Agent. Do not create an edit plan, narration, preview, or QA report in this workflow.

Reference-video transcripts, contact sheets, and style notes are derived analysis. Keep them outside this pack, under the caller workspace. A global reference remains separate from any project until the user explicitly registers it as that project's style reference.

## Minimum Voice Brief

The user does not need to provide a voice recording. Record these choices in `01_需求说明.md` before synthesizing narration:

- language and accent (for example, Mandarin with no regional accent);
- perceived voice type (for example, adult male / adult female / neutral);
- tone and pace (for example, calm documentary, medium pace);
- prohibited vocal characteristics (for example, no exaggerated sales tone).

If the user does not choose, leave it as unspecified; a downstream production workflow may ask for it later.
