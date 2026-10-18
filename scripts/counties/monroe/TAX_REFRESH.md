# Monroe tax-delinquent layer: data source, re-download, rebuild

**Source (public):** Monroe County Tax Collector's reports on the county-taxes.net portal, `https://county-taxes.net/fl-monroe` (reports area).
First load: Oct 16, 2026 (as-of date shown in the app). The site is browser-only (JavaScript app behind a Cloudflare challenge): `curl` / WebFetch return only the page title, so the
CSVs cannot be pulled by a plain script. Refresh is **manual (download from the browser) or browser-driven** (the box desktop browser / a Playwright run with a real, non-headless profile; do not try to
bypass the challenge: if it is blocked, download by hand and drop the files in place).

## Files (all land in `$RAW/monroe/tax/`, default `/workspace/raw/monroe/tax/`; `raw/` is git-ignored)
| File | Report | Columns |
|---|---|---|
| `monroe_unpaid_taxes*.csv` | Unpaid / delinquent taxes (all tax years, status Unpaid) | Tax Yr, Account Number, Property ID, Owner Name, Owner Address, Account Status, Balance Amount, Bidder #, Cert #, Assessed Value, Physical Location, Physical Location City |
| `monroe_county_held_certificates.csv` | Tax certificates held by the county (bidder 99999) | Tax Yr, Account Number, Property ID, Cert #, Cert Buyer, Owner Name, Cert Status, County Held, Price to Purchase |

Name each pull so the order is obvious (`monroe_unpaid_taxes.csv`, then `..._v2.csv`, `..._v3.csv`). Keep the older pulls: the script uses them for the audit (which rows were paid between pulls).

## Steps
1. In the browser open the reports page for Monroe, run the unpaid-taxes report with **all tax years** and download the CSV (and the county-held certificates report). Note the date.
2. Copy the files into `/workspace/raw/monroe/tax/` (`$RAW/monroe/tax/`).
3. Dry run (prints the dedupe + match audit, writes nothing):
   `python3 scripts/counties/monroe/add_tax.py --dry --asof YYYY-MM-DD --pulls <oldest.csv> ... <newest.csv>`
4. Apply (patches `data/monroe/main|condo(.bin.gz|-detail.bin.gz)` + `meta.json` `tax` + `tax-audit.json`; no full rebuild; Miami-Dade / Broward data untouched):
   `python3 scripts/counties/monroe/add_tax.py --asof YYYY-MM-DD --pulls <oldest.csv> ... <newest.csv>`
5. A full `build_monroe.py` rebuild re-runs `add_salex.py` only; run `add_tax.py` again afterwards (it is idempotent: columns are replaced).
6. Bump the service-worker cache (`sw.js`), run `tests/e2e_monroe.py`, push.
Suggested cadence: after each tax-certificate sale (May) and every 1-2 months while the November discount / April 1 delinquency dates pass.

## Rules the script applies (documented in `add_tax.py` header and `data/monroe/tax-audit.json`)
* **Match key:** `Account Number` (= `Property ID`, 7 digits) is the Property Appraiser `ALT_KEY`, not the RE number, so the "last 14 digits of the folio" rule does not apply to this export. Account -> ALT_KEY -> 20-digit folio, verified by site address (about 99% agree) and owner name.
* **Dedupe across pulls:** key = (Account, Tax Yr). The newest pull wins for every key it has. A key present only in an older pull is treated as paid / redeemed and dropped (`--keep-older-only` shows the sensitivity). Oct 16, 2026: v2 (2,304 rows) is a subset of v1 (4,025) with higher (interest-accrued) balances; v1-only rows are 1,581 current-year (2026) rows + 140 delinquent-year rows.
* **Delinquent year** = tax year <= as-of year - 1 (2025). The current-year bill (2026) is not delinquent until April 1, 2027; it is carried separately (drawer line, flag bit 4) and is not counted in "years delinquent".
* **Certificate** = a Cert # / Bidder # on a delinquent year; **county-held** = bidder 99999 or the held-certificates list.

## Contact rule (shown in the drawer)
Florida Statute 197.432(13): a tax-certificate **holder** may not contact the property owner to demand payment (and the owner is not obliged to deal) during the first 2 years after the certificate was issued; the restriction is on certificate holders. It is not a rule against an investor / home-buyer contacting an owner about buying the property. Monroe's next tax-certificate sale: **May 2027**.
