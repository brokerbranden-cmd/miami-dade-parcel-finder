# Email owners (Outlook deeplink / mailto) progress (resume-friendly)
Started 2026-10-19 16:15 ET. Base: 1c70795 (pending local progress commit, unpushed).
Plan: skiptrace-ui.js (Email button + template editor modal + repeat warning), app.js (skBridge.markEmailed -> SEND.sent[f].em + 'Emailed <date>' badge + SV email activity when saved), ui.css, index.html (Email template button), sw v22, tests/e2e_email.py desktop+mobile in scripts/pre_push_regression.sh.
DNS (read-only, 16:13 ET): SPF ok (includes spf.protection.outlook.com + secureserver.net, -all); MX ok (prophunters-com01b.mail.protection.outlook.com); DKIM selector1/2 CNAMEs present but targets NXDOMAIN -> DKIM signing not enabled in M365; DMARC p=none, no rua.
Rules: never git clean, explicit git add paths, no shots/ test_runs/ tests/export_sample.csv. Regression on PORT=8097 via nohup.
## Log
