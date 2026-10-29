# parcel-sync: team sync for the private site (app.prop-hunters.com)

Saved properties (folders, notes, statuses, outreach logs), Send-to tags / sent marks, skip trace results (phones / emails),
call results and bad-email marks sync between every browser signed in at **https://app.prop-hunters.com** (Cloudflare Access,
email one-time code). The public GitHub Pages copy never syncs; it shows "sign in at app.prop-hunters.com to sync" and offers a
backup file that can be restored on the app (each site has its own browser storage, so data saved on github.io has to be moved once).

- `src/index.js`: Cloudflare Worker on the route `app.prop-hunters.com/sync-api/*` (same origin as the app, inside the Access
  application). Every request must carry a valid Access JWT (RS256, team certs, `aud`, `iss`, `exp`, `email`); service tokens
  (no email) are refused. No CORS, foreign Origin refused, nothing logged.
  - `GET /sync-api/me` -> `{ok, email, now}`
  - `POST /sync-api/sync` (`X-PF-Sync: 1`, JSON) `{since, push:[{ns,k,v,at}]}` -> `{cursor, more, changes:[{ns,k,v,at,by,seq}], accepted, rejected}`
  - one row per record (`ns` = browser store incl. county suffix, `k` = folio / folder id / phone / email), last edit wins on `at`
    (server clock), `v = null` is a delete, `by` = Access email of whoever made the edit.
- D1 database `parcel-sync` (free tier). Schema is created on first use.
- `../sync.js`: browser side (local first, outbox while offline, status pill, who-edited fields).

Deploy (needs a Cloudflare API token with Workers + D1 edit on the account): `cd sync-worker && npx wrangler deploy`.
Team access: add each person's email to the Access policy of the "Parcel Finder" application (Zero Trust > Access > Applications).

Tests: `node test/sync.test.mjs` (Worker logic on node:sqlite) and `python3 ../tests/e2e_sync.py [port]` (real Worker in
`wrangler dev` + fake Access + two browsers). No real personal data lives in this repo; test data uses 555 numbers.
