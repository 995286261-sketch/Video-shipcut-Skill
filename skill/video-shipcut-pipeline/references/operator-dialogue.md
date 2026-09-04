# Operator Dialogue

Use short conversational commands. Always read state before replying. For every status, continuation, node handoff, and approval response, follow [路径展示合同](path-display-contract.md): show existing local artifact and input paths as clickable Markdown links, while leaving machine-state path fields as plain strings.

| User phrase | Pipeline action |
| --- | --- |
| New project / user provides media | Start G0: first present the fixed intake form (including an explicit BGM choice), then collect materials, validate the material pack, initialize state, and start G1. |
| Continue project / Next step | Report current node, valid inputs, risk, and exact next action. |
| Confirm G1 | Register direction approval and route G2. |
| Confirm G2 | Register narration, fact-decision, and confirmed voice-decision paths, then route G3. |
| Reopen G2 from G3 | Only when G3 finds missing or corrected evidence, facts, or approved narration: create a reviewable amendment file, run the supported `reopen` transition, amend G2, and obtain renewed G2 approval before returning to G3. |
| Confirm G3 | Register plan approval and route G4. |
| Confirm local G4 candidate | Register validated local render and route G5. |
| ChatCut export is ready | Register actual export path for the ChatCut branch and route G5. |
| Confirm G5 | Register human QA, accepted warnings, and close delivery. |
| Project status | Report state without changing it. |

Do not ask a user to produce hashes, SRT, timecodes, or JSON. Present reviewable candidates and record the user's decision.

For a blocked node, explain the single missing input or decision and do not propose an invented substitute.
