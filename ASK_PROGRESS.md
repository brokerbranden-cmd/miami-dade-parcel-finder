# Ask box (plain-English -> filters) progress
Started 2026-10-20 12:40 ET in /workspace/pf-fx (HEAD 882bc07 = pending progress commit, unpushed).
Plan: ask.js (parser, pure, node-testable) + app.js wiring (PF.askApply via applyState like IDEAS) + index.html #askBar under header + ui.css; tests/e2e_ask.py (ask vs hand-written hash, desktop+mobile) + tests/unit_ask.js; sw v24; ASK_PHASE2.md design note.
## Log
- ask.js parser written + node smoke ok
- app wiring + UI committed (WIP), mobile layout checked; next tests/e2e_ask.py + unit
- tests: unit_ask ALL PASS, e2e_ask desktop ALL PASS (8098 dev server); added to regression
- 12:55 Branden's exact email template is the new default ({first_name}); unedited old default migrates; e2e_email updated, desktop PASS

## Oct 20 (later)
- Email owner (BCC) and opt-out strip are committed, with tests.
- ASK_PHASE2.md written.
- Phone flags: the DNC/Litigator badges, the drawer warning and the CSV Flags columns are removed. Every number gets Call and Text. The flag data stays stored (q[2]), and the bulk Text list still leaves out DNC numbers.
- Bad email: stored in localStorage pf.bademail.v1. The 3 known bounces are pre-marked. Bad emails are dimmed, have no Email button and are left out of BCC.
- Next: fast-forward parcel-finder, run the regression, push, verify live.
- sw v25; folder picker stays inside the viewport (mobile); scenarios s01 dispatch fix. Regression rerun next.
- scenarios preset helper (line 43) also dispatches: force-clicks on hidden More-ideas chips landed on the new Ask bar at the top
