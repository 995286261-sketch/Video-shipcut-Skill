# Operator Dialogue

Use short conversational commands. Always read state before replying. For every status, continuation, node handoff, and approval response, follow [路径展示合同](path-display-contract.md): show existing local artifact and input paths as clickable Markdown links, while leaving machine-state path fields as plain strings.

| User phrase | Pipeline action |
| --- | --- |
| New project / user provides media | Start G0: first present the fixed intake form (including an explicit BGM choice), then collect materials, validate the material pack, initialize state, and start G1. |
| Continue project / Next step | Report current node, valid inputs, risk, and exact next action. |
| Confirm G1 | After G1 is `review_required` and its fixed review-gate receipt is registered, record the exact response `确认 G1`, then register direction approval and route G2. |
| Confirm G2 | After G2's fixed review-gate receipt is registered, record the exact response `确认 G2`, then register narration, fact-decision, and confirmed voice-decision paths and route G3. |
| Reopen G2 from G3 | Only when G3 finds missing or corrected evidence, facts, or approved narration: create a reviewable amendment file, run the supported `reopen` transition, amend G2, and obtain renewed G2 approval before returning to G3. |
| Confirm G3 | After the G3 review-gate receipt is registered, record the exact response `确认 G3`, then register plan approval and route G4. |
| Confirm local G4 candidate | This is review feedback only. After the G4 review-gate receipt is registered, require the exact response `确认 G4` before routing G5. |
| ChatCut export is ready | Register the actual export path, create the G4 review gate, then require `确认 G4` before routing G5. |
| Confirm G5 | After the G5 review-gate receipt is registered, require the exact response `确认 G5`, then register human QA, accepted warnings, and close delivery. |
| Project status | Report state without changing it. |

Do not ask a user to produce hashes, SRT, timecodes, or JSON. Present reviewable candidates and record the user's decision.

For a blocked node, explain the single missing input or decision and do not propose an invented substitute.
