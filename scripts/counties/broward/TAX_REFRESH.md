# Broward tax-delinquent layer: data source, re-download, rebuild

**Source (public):** Broward County Tax Collector reports on `https://county-taxes.net/broward` (Cloudflare-protected, browser-only: no scripted download). First load: **Oct 18, 2026** (the as-of date in the app).
Refresh is **manual (download from the browser) or browser-driven** (box desktop browser). Do not try to bypass the challenge; if blocked, download by hand and drop the files in place.

## Files (in `$RAW/broward/tax/`, default `/workspace/raw/broward/tax/`; `raw/` is git-ignored)
| File | Report | Notes |
|---|---|---|
| `broward_unpaid_tax_certificates.csv` | Unpaid tax certificates, all years (back to 1998) | Account Number (= folio with dashes), Tax Yr, Cert #, Cert Sale Date, Cert Buyer, Cert Status, Deed Status, Redemption Amt / Unpaid Tax (often blank), Assessed Value |
| `broward_unpaid_real_estate_2023_2025.csv` | Unpaid real-estate taxes, tax years 2023-2025 | Balance Amount, Cert Status, Deed Status, Advertised Number. **Report subtotal rows (blank Account Number, 'Grand Total') are dropped.** |
| `broward_tax_deed_auction_<yyyy-mm-dd>.csv` | One file per scheduled tax-deed sale date | Account Number, Deed Sale Date, Tax Yr, Applicant, Deed Application # |
| `broward_prior_3yr_unpaid.csv` | Small Boca-only sample (account-level balance) | unioned (used only where the account has no balance rows in the 2023-2025 report) |
| `broward_unpaid_real_estate.csv` | Old 2014-2017 report (mostly Paid In Full) | **not used** |

## Steps
1. In the browser run each report (all rows) and download the CSV; one auction file per sale date (the Tax Collector lists several upcoming dates). Note the download date.
2. Put the files in `/workspace/raw/broward/tax/` (delete auction files for past sale dates, or leave them: sales before the as-of date are ignored).
3. Dry run: `python3 scripts/counties/broward/add_tax.py --dry --asof YYYY-MM-DD` (match rates, counts, audit; writes nothing).
4. Apply: `python3 scripts/counties/broward/add_tax.py --asof YYYY-MM-DD`. It patches `data/broward/main|condo (.bin.gz, -detail.bin.gz)` + `meta.json` (`tax`) + `tax-audit.json`; no full rebuild; Miami-Dade / Monroe data untouched. Idempotent (columns replaced, distress points not double counted).
5. Re-run `add_tax.py` after any full `build_broward.py` rebuild. Bump the service-worker cache (`sw.js`), run `tests/e2e_broward.py`, push.
Suggested cadence: after each auction date and the late-May certificate sale; new auction dates appear on the Tax Collector page about 2 months ahead.

## Rules (see the `add_tax.py` header; counts in `data/broward/tax-audit.json`)
* **Match:** Account Number minus dashes, upper-case = the 12-character pack folio (condo units keep letters: 494330-BE-0390 -> 494330BE0390).
* **Delinquent year** = tax year <= 2025 that is either in the 2023-2025 unpaid report, or a live certificate row (Issued / Purchased / Transferred; Surrendered = surrendered to apply for a tax deed, year still unpaid; Redeemed with a deed Applied/Certified). Redeemed-without-deed, Canceled and Deleted certificates are ignored. 2026 bills (mailed Nov 1) are not delinquent until Apr 1, 2027.
* **Balance** = report Balance Amount; else the certificate's Redemption Amt / Unpaid Tax; else unknown (older certificate-only years have no amount in the export; the drawer says the total can be higher).
* **Certificate** = outstanding investor certificate (buyer shown); **county-held** = buyer BROWARD COUNTY. **Tax deed auction upcoming** = account is in an auction file with a sale date on/after the as-of date; **tax deed applied** = deed status Applied / Certified.
* Distress: tax points added to `dscore` (certificate 10 + 4 per extra year, max 18; none 6; tax deed application or auction +30, Miami-Dade scale) and signals TD / TC / TX; vacancy hint +10.

## Contact rule (shown in the drawer)
FS 197.432(13): the holder of a tax certificate may not, directly or through an agent, initiate contact with the owner to encourage or demand payment until 2 years after April 1 of the year the certificate was issued (14: can bar the holder from future sales; unfair / deceptive trade practice). It is a rule for certificate holders, not a general ban on anyone approaching the owner. Not legal advice.
