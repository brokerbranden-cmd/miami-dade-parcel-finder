# Ask box — phase 2 design note (not built)

Phase 1 (shipped) is a local rule-based parser (ask.js): no network calls, no cost, and it works offline.
Phase 2 would add an LLM only for asks the parser can't fully understand (the ones that leave `unknown` words or hints).

## Flow
1. The browser runs PFAsk.parse first. If nothing is left unknown, it does not call the LLM.
2. Otherwise it POSTs `{county, text, schema}` to a Cloudflare Worker (`/ask`). The schema is the list of allowed hash keys and values, built from the same tables ask.js uses (cities, hoods, presets, distress layers per county).
3. The Worker calls the LLM with a JSON-schema-constrained output. It returns only `{set:{...}, jump?, owner?, explain}`, which is validated against the allow-list in the Worker and again in the browser.
4. The browser shows the result as the same editable chips, labeled "AI guess". The user can remove any chip. It never auto-sends or auto-saves anything.
5. On error, timeout (more than 4 s) or cap reached, it falls back to the phase-1 result and its hint.

## Keys / secrets
- The LLM API key is stored as a Worker secret (`wrangler secret put LLM_KEY`). It is never in the repo or the static site.
- The Worker allows only the Pages origin (CORS) and checks Origin.
- No property data is sent: only the typed text plus the static schema.

## Cost (rough)
- About 1.5k input tokens (schema) plus 100 output tokens per call.
- With a small, fast model that is about $0.0003–0.001 per ask, so 1,000 asks a month comes to roughly $1 or less.
- The Workers free tier (100k requests a day) covers the Worker itself.

## Abuse / limits
- Per-IP rate limit (for example 20 a minute) using a Workers KV or Durable Object counter.
- Hard daily cap (for example 500 calls); after that the Worker returns 429 and the client falls back to phase 1.
- Logging is optional and off by default.

## Needs from Branden
- An LLM provider account and API key.
- Approval to deploy one Worker on his Cloudflare account.
- A chosen daily cap.
