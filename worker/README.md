# Parcel Finder skip trace Worker

A tiny Cloudflare Worker that lets the public Parcel Finder site (GitHub Pages) run **BatchData** skip traces without ever exposing the BatchData API key.
The browser sends owner / property rows plus an **access code**; the Worker calls BatchData's Property Skip Trace API (V3, `POST https://api.batchdata.com/api/v3/property/skip-trace`) with the key stored as a Worker secret, and returns results already shaped for the site's skip trace store.

Live URL: `https://parcel-skiptrace.brokerbranden.workers.dev` (Cloudflare account brokerbranden, Worker name `parcel-skiptrace`).

## Secrets and settings (never in this repo)
| Name | Kind | Meaning |
|---|---|---|
| `BATCHDATA_API_KEY` | secret | BatchData API token |
| `ACCESS_CODE` | secret | Code the dashboard sends in the `X-Access-Code` header (entered once per device) |
| `ALLOWED_ORIGIN` | variable | Default `https://brokerbranden-cmd.github.io` (the only browser origin allowed) |
| `MAX_PER_REQUEST` | variable | Default `50` records per request (max 100) |
| `DAILY_CAP` | variable | Default `500` records per New York day, counted across all callers. Raise it in Cloudflare (Workers > parcel-skiptrace > Settings > Variables) when you need more |
| `LIMITER` | Durable Object binding | Counters only (daily usage, per IP request times, failed-code times). No personal data is stored or logged |

Troubleshooting: an upstream failure returns `upstreamStatus` (and BatchData's short message, e.g. `Invalid token.`) next to the error code, so a wrong or expired `BATCHDATA_API_KEY` secret shows up as `provider_auth` / 401. Fix it with `npx wrangler secret put BATCHDATA_API_KEY` (or the dashboard). The key is never returned or logged.

Change the access code: Cloudflare dashboard > Workers & Pages > parcel-skiptrace > Settings > Variables and Secrets > `ACCESS_CODE` > Edit. Devices then get "access code not accepted" and ask again.

## API
* `GET /health` public. `{ok, service, configured}`; no secrets.
* `GET /status` header `X-Access-Code`. `{ok, dailyCap, usedToday, remainingToday, maxPerRequest}`. Used by the site to validate the code and show the daily allowance.
* `POST /skiptrace` header `X-Access-Code`, JSON body:
  ```json
  {"items":[{"id":"3059010010010","first":"Ana","last":"Perez","company":"","street":"1206 SW 2 ST","city":"Homestead","state":"FL","zip":"33030",
             "mailStreet":"PO BOX 7","mailCity":"MIAMI","mailState":"FL","mailZip":"33177"}]}
  ```
  Response: `{ok, results:[{id,status,name?,phones?,emails?,error?}], meta:{requested,sent,matched,withContact,nomatch,errors,billable}, dailyCap,usedToday,remainingToday,maxPerRequest}`.
  `status` is `match` (phones/emails), `nocontact` (BatchData matched the property but has no phone/email), `nomatch`, or `error` (e.g. `bad_address`, not billed, safe to retry).
  Phones are already in the store format `[10 digits, 'm'|'l'|'v'|'', flags]` where flags `1` = DNC and `2` = litigator / TCPA-restricted.
* Errors: `{error: code}` with `bad_access_code` (401), `locked_out` / `rate_limited` / `daily_cap` (429), `too_many_items` / `body_too_large` (413), `forbidden_origin` (403), `provider_*` (502/429), `not_configured` (503).

## Protections
* Access code compared in constant time (SHA-256 digests, no early exit); 8 wrong codes from one IP in 15 minutes locks that IP out for 15 minutes.
* CORS limited to `ALLOWED_ORIGIN`; browser requests from any other origin get 403.
* 20 requests / minute and 200 / hour per IP; max 50 records per request; daily cap (default 500) reserved *before* calling BatchData and refunded for no-match, error and failed requests, so it tracks what BatchData bills.
* The BatchData key is only used in the outgoing `Authorization` header. Errors are mapped to short codes; upstream bodies, exceptions and the key are never returned or logged (the source has no `console.*`).

## BatchData notes (from developer.batchdata.com, V3 Property Skip Trace)
* A matched property that returns at least one person is one billable record (`meta.results.matchCount`); no match is not billed. The Worker sends `requestId` per row to correlate results and `includeTCPABlacklistedPhones: true` so TCPA-flagged numbers come back flagged (they are shown with a badge and kept out of the Text list) instead of silently dropped.
* Per-record price is **not published**; it depends on your BatchData plan (pay per matched record, or monthly tiers). Check your BatchData account / pricing page.
* Each phone has `dnc` and `tcpa`; each person has `litigator` and `deceased` (deceased persons are skipped). Not legal advice: you remain responsible for TCPA / DNC / state rules.

## Develop / test / deploy
```
node worker/test/worker.test.mjs          # unit tests: no network, fake key
```
Deploy with wrangler (`cd worker && npx wrangler deploy`, then `npx wrangler secret put BATCHDATA_API_KEY` and `... ACCESS_CODE`) or through the Cloudflare API (multipart upload of `src/index.js` as an ES module with the Durable Object migration `new_sqlite_classes: ["Limiter"]`). `wrangler.toml` here mirrors the deployed configuration.
