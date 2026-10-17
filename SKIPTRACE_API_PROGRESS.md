# Skip trace API (BatchData via Cloudflare Worker) progress (resume-friendly)
Scope: Worker in worker/, UI buttons (bulk 'Skip trace these' + per-card + drawer 'Skip trace'), tests/e2e_skiptrace_api.py (mocked worker), unit tests.
Never print/commit BATCHDATA_API_KEY or ACCESS_CODE. Don't commit data/*.gz, meta.json, shots/, tests/export_sample.csv. No git clean / git add -A.
## Findings
- CF auth OK via user-Cloudflare MCP (account 4131ccf716f2a4ff2fb7c98e246f0541, subdomain brokerbranden). Worker name: parcel-skiptrace -> https://parcel-skiptrace.brokerbranden.workers.dev
- BatchData: use V3 POST https://api.batchdata.com/api/v3/property/skip-trace, Bearer key, body {requests:[{requestId, propertyAddress:{street,city,state,zip}, name?, mailingAddress?}], options:{includeTCPABlacklistedPhones:true}}; max 100/req.
  Response result.data[] each {input, property, persons[{name, phones[{rank,number,type(Mobile|Land Line|..),dnc,tcpa,reachable,tested}], emails[{email}], litigator, deceased}], meta{matched,error}}; result.meta.results{requestCount,matchCount,noMatchCount,errorCount}. Billed only per matched property with >=1 person. Price: NOT public (custom per plan) -> UI says 'check your BatchData pricing'.
## Log
- 20:14 worker/src/index.js + worker/test/worker.test.mjs written, 20 unit tests pass. Next: deploy worker, then client.
- 20:15 WORKER DEPLOYED https://parcel-skiptrace.brokerbranden.workers.dev (secrets BATCHDATA_API_KEY + ACCESS_CODE set; code kept in /workspace/tmp/.skapi/code.txt chmod 600, NOT in repo). /health,/status verified (401 w/o code, 403 bad origin, CORS ok). deploy.js with secrets shredded. Redeploy later = need secrets again (use keep_bindings:['secret_text'] in metadata for code-only updates). Next: client skiptrace-api.js + UI + tests
- 20:16 skiptrace-api.js + tests/unit_skiptrace_api.js pass. Next: UI (skiptrace-ui.js bulk modal + card/drawer buttons), index.html button+script tag, app.js card click exclusion, ui.css, sw.js v16, e2e_skiptrace_api.py
