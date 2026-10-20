# Email owners (Outlook deeplink / mailto) progress (resume-friendly)
Started 2026-10-19 16:15 ET. Base: 1c70795 (pending local progress commit, unpushed).
Plan: skiptrace-ui.js (Email button + template editor modal + repeat warning), app.js (skBridge.markEmailed -> SEND.sent[f].em + 'Emailed <date>' badge + SV email activity when saved), ui.css, index.html (Email template button), sw v22, tests/e2e_email.py desktop+mobile in scripts/pre_push_regression.sh.
DNS (read-only, 16:13 ET): SPF ok (includes spf.protection.outlook.com + secureserver.net, -all); MX ok (prophunters-com01b.mail.protection.outlook.com); DKIM selector1/2 CNAMEs present but targets NXDOMAIN -> DKIM signing not enabled in M365; DMARC p=none, no rua.
Rules: never git clean, explicit git add paths, no shots/ test_runs/ tests/export_sample.csv. Regression on PORT=8097 via nohup.
## Log
- 16:40 built feature (app.js markEmailed/emBadge, skiptrace-ui.js Email button/template/repeat warning, index.html stTplBtn, ui.css, sw v22); tests/e2e_email.py desktop+mobile PASS locally; added to pre_push_regression.sh. Next: full regression (nohup), push, live verify.
- 17:46 full pre-push regression 15/15 green (summary_prepush_20261019-161806). Pushed 5a4b775 (with 1c70795, ac7aac7). Live e2e_email desktop+mobile ALL PASS (50 checks each). DONE.
## Skip traced view (2026-10-19 evening)
- Built in /workspace/pf-fx (ff'd to ec443d5): 'Skip traced' view tab (app.js renderTraced/trRows/trCSV, index.html #vTraced/#trbox, ui.css, skiptrace-ui emailHTML export), sw v23, tests/e2e_traced.py desktop+mobile PASS locally, added to pre-push regression.
- Worker has no history endpoint (only /status, /skiptrace) and was left unchanged: the view lists the per-county local store, which holds every Worker result returned on this device + imports.
- Regression runs from /workspace/parcel-finder (8097 server serves that dir) after ff to the pf-fx commit; push from there.
- 20:15 added Saved folders (saved.js folders API + migration to default 'My saved', app.js tabs/new/rename/delete/per-folder CSV/picker on save + Saved cards + drawer, backup JSON v3 carries folders); tests/e2e_folders.py desktop+mobile PASS, e2e_saved + e2e_traced still PASS; in regression. Killed my own interrupted regression run first. Next: regression from /workspace/parcel-finder, push, live verify.
- 21:05 regression 19/19 green (summary_prepush_20261019-200421), pushed 9071ab1 (incl. ec443d5 EMAIL_PROGRESS), live e2e_traced + e2e_folders desktop+mobile ALL PASS on Pages (sw v23). DONE.
