# Material Intake

Start a project by copying `assets/material-pack-template/` to a caller-selected project folder. Read `00_使用步骤.md` first, then keep its seven numbered entries. Empty optional folders are valid.

Treat `01_需求说明.md`, `03_事实依据/`, and `04_授权说明.md` as the human-provided input layer. Do not ask the user for timecodes, hashes, an edit order, SRT, JSON, or a prebuilt editing project.

After intake, preserve source files unchanged. This Skill generates hashes and a manifest only. Media probes, contact sheets, source-time candidates, edit plans, QA reports, and other artifacts belong to downstream workflows.

Only use `05_风格参考/` to derive reusable style rules. Do not use its media, music, captions, text, or logo as output assets. Treat `07_授权音频/` as unavailable unless its use and authorization are explicit; default to no BGM.

Before final render, the Agent must generate a review package containing a readable script/caption draft, evidence references, source-time candidates, candidate visuals, and a playable rough-cut preview. Content review approves the factual and editorial result; technical review approves traceability and render/QA constraints. Neither approval may be inferred from a completed render.
