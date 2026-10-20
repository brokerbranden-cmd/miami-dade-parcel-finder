# Ask box (plain-English -> filters) progress
Started 2026-10-20 12:40 ET in /workspace/pf-fx (HEAD 882bc07 = pending progress commit, unpushed).
Plan: ask.js (parser, pure, node-testable) + app.js wiring (PF.askApply via applyState like IDEAS) + index.html #askBar under header + ui.css; tests/e2e_ask.py (ask vs hand-written hash, desktop+mobile) + tests/unit_ask.js; sw v24; ASK_PHASE2.md design note.
## Log
- ask.js parser written + node smoke ok
- app wiring + UI committed (WIP), mobile layout checked; next tests/e2e_ask.py + unit
- tests: unit_ask ALL PASS, e2e_ask desktop ALL PASS (8098 dev server); added to regression
- 12:55 Branden's exact email template is the new default ({first_name}); unedited old default migrates; e2e_email updated, desktop PASS
