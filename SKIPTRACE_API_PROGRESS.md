# Skip trace API (BatchData via Cloudflare Worker) progress (resume-friendly)
Scope: Worker in worker/, UI buttons (bulk 'Skip trace these' + per-card + drawer 'Skip trace'), tests/e2e_skiptrace_api.py (mocked worker), unit tests.
Never print/commit BATCHDATA_API_KEY or ACCESS_CODE. Don't commit data/*.gz, meta.json, shots/, tests/export_sample.csv. No git clean / git add -A.
## Findings
- CF auth OK via user-Cloudflare MCP (account 4131ccf716f2a4ff2fb7c98e246f0541, subdomain brokerbranden). Worker name: parcel-skiptrace -> https://parcel-skiptrace.brokerbranden.workers.dev
- BatchData: use V3 POST https://api.batchdata.com/api/v3/property/skip-trace, Bearer key, body {requests:[{requestId, propertyAddress:{street,city,state,zip}, name?, mailingAddress?}], options:{includeTCPABlacklistedPhones:true}}; max 100/req.
  Response result.data[] each {input, property, persons[{name, phones[{rank,number,type(Mobile|Land Line|..),dnc,tcpa,reachable,tested}], emails[{email}], litigator, deceased}], meta{matched,error}}; result.meta.results{requestCount,matchCount,noMatchCount,errorCount}. Billed only per matched property with >=1 person. Price: NOT public (custom per plan) -> UI says 'check your BatchData pricing'.
## Log
- 20:14 worker/src/index.js + worker/test/worker.test.mjs written, 20 unit tests pass. Next: deploy worker, then client.
