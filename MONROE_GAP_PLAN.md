# Monroe County permit / code-case gap plan (2026-10-22)

Scope: building permits and code-enforcement cases for Key West, Islamorada, Key Colony Beach and Layton.
Parcel counts are from `/workspace/raw/monroe/parcels.jsonl` by tax district (TAX_AUTH_C):
Key West 10KW+11KW+12KW = **11,223**; Islamorada 50VI = **6,805**; Key Colony Beach 50KC = **1,533**; Layton 50LA = **197**.
All probes are plain HTTP from the box, about 60 requests in total spaced 2-3 s apart. No HTTP 429s or blocks were seen. No robots.txt is published on etrakit/cvportal, and no terms-of-use page is linked from either search page.

## Summary

| City | Platform | Automation | Bulk / date route | Polite weekly sweep | Blocker | Records contact |
|---|---|---|---|---|---|---|
| Key West | CentralSquare eTRAKiT (ASP.NET/Telerik), etrakit.cityofkeywest-fl.gov/etrakit | **WORKS** (no login; a reCAPTCHA script loads but no challenge appears on search) | Permits: `ISSUED EQUALS <date>` (also AT LEAST/AT MOST). Code cases: only CASE_NO/SITE_ADDR, so enumerate `CASE_NO BEGINS WITH CC2026-0NN` (100 numbers per prefix) | Permits ~7 day-queries, about 15-25 requests, under 2 min. Cases: about 1-2 prefixes plus a detail postback for each new or open case to get status and date, about 50-150 requests, around 5-8 min. A per-parcel sweep would take ~11,223 x 2 x 3 s, about **19 h**, so it isn't needed | Every query is capped at 20 pages (100 case rows), sorted ascending, so slices must stay narrow. The case list shows no status or date (detail postback not yet built). Cases before about 2018 use the YY-NNNNN format | Clerk@cityofkeywest-fl.gov (Keri O'Brien, Records Custodian, 305-809-3832); online request form linked from cityofkeywest-fl.gov/386/Records-Management |
| Islamorada | Harris CityView Portal, cvportal.us/CityViewPortal (Permit + CodeEnforcement locators) | **WORKS** (no login/captcha; JSON `LocatorResults`, 20 per page, newest first) | Substring search on number/address/RE#. Searching `2026` pages through all 2026 permits or code cases (case numbers like CEWST20260000381) and returns status, type, address and RE# | Weekly: first 5-10 pages per module, about 20 requests, under 1 min. Full-year refresh for status changes: about 150-200 pages, around 10 min. Per-parcel would take ~6,805 x 2 x 3 s, about **11 h**, and isn't needed | List has no issue/open dates (the year comes from the number). COVERAGE.md says "complaint intake only", but a public code-case locator does exist | Clerk@islamorada.fl.us (Marne McGrath, Village Clerk, 305-664-6412); JustFOIA portal https://islamorada.justfoia.com/publicportal (the site names it as the request channel) |
| Key Colony Beach | Citizenserve (installation 326) | **BLOCKED**: search form requires reCAPTCHA v3 token (`g-recaptcha-response`, sitekey 6LeKdrMZ...) | None found | n/a (per-parcel would be ~1,533 x 2 x 5 s, about 4 h, if it were allowed) | Captcha; not bypassed. Use a records request | cityclerk@keycolonybeach.net (Silvia Roussin, City Clerk, 305-289-1212 x2); optional form keycolonybeach.net/wp-content/uploads/2021/11/Public-Record-Request-Form.pdf |
| Layton | none (no online permit/code portal found) | **N/A** | None | n/a (197 parcels) | Nothing published | cityhall@cityoflayton.com (Mimi Young, City Clerk / Public Records Custodian, 305-664-4667; the site also lists myoung@cityoflayton.com) |

## Proofs of concept (not wired)
- `scripts/poc_monroe_keywest.py permit 10/15/2026` returned 22 permits (number, issue date, type, subtype, status, RE#, address). `... case CC2026-009` returned 100 cases (number, address).
- `scripts/poc_monroe_islamorada.py permit 2026 2` and `... code 2026 2` each returned 40 rows (number, type, status, address, RE#).
Both scripts use a 3 s delay and an identifying User-Agent.

## Next steps
1. Key West: add the per-case detail postback (status/open date), then wire it with a weekly window plus a monthly re-check of open cases.
2. Islamorada: wire a weekly first-N-pages pull plus a monthly full-year pull for status changes, and fix the COVERAGE.md row.
3. Key Colony Beach: request sent 10/22/2026 from Branden@prop-hunters.com; the City answered 10/27/2026 with two Excel exports (1,717 permits issued 1/3/2023-10/26/2026, 1,059 code records opened 1/3/2023-10/21/2026), now loaded (`load_kcb_records.py`). The clerk says reports are sent only upon request (no automatic monthly feed) - re-request to refresh. Layton: send the Chapter 119 request below (not sent yet).

## Draft Chapter 119 requests (NOT SENT)

Common body (city name varies):

> Dear Records Custodian,
>
> Under Chapter 119, Florida Statutes, I request an electronic export (CSV or Excel) of all building permits and all code-enforcement cases of the {CITY} from January 1, 2023 to the present. For each record, please include the permit/case number, type, open/closed status, property address, parcel (RE) number, issue or open date (and closed date if available), and description.
>
> A database export in its existing format is fine; no new records need to be created. If any fields are exempt, please redact only those fields and cite the exemption. If fees will exceed $25, please send me an estimate before proceeding.
>
> Could you also tell me whether you can provide the same export as an ongoing monthly update?
>
> Thank you,
> Branden
> Prop Hunters LLC
> Branden@prop-hunters.com
> (305) 812-9445

| City | To | Subject |
|---|---|---|
| Key West | Clerk@cityofkeywest-fl.gov | Public Records Request (Ch. 119) - Building Permits and Code Enforcement Cases Export, City of Key West |
| Islamorada | Clerk@islamorada.fl.us (or the JustFOIA portal) | Public Records Request (Ch. 119) - Building Permits and Code Enforcement Cases Export, Islamorada, Village of Islands |
| Key Colony Beach | cityclerk@keycolonybeach.net | Public Records Request (Ch. 119) - Building Permits and Code Enforcement Cases Export, City of Key Colony Beach |
| Layton | cityhall@cityoflayton.com | Public Records Request (Ch. 119) - Building Permits and Code Enforcement Cases Export, City of Layton |
