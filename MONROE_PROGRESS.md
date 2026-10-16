# Monroe County enrichment progress (resume-friendly)
Started 2026-10-16. Raw inputs: /workspace/raw/monroe/. Scripts: scripts/counties/monroe/.
## Phases
- [ ] P1 zoning  - [ ] P2 ROGO/Tier  - [ ] P3 env layers  - [ ] P4 tax  - [ ] P5 clerk/permits  - [ ] P6 absentee/PA link/comps  - [ ] P7 buildability UI  - [ ] tests/push/live
## Log
- 10:40 Fetchers done & committed: county layers (mcgis4 APO_GIS via verify=False for that host only: zoning L19 6522 polys, tier L18, FLUM L20, ROGO dedication pts L1, CBRS, habitat, species focus), city layers (Key West Zoning_all_info w/ setbacks, Marathon Zoning+FLUM, Islamorada Zoning), FNAI cons lands(49), Florida Forever(38), NWI (running, 260 cells), ROGO PDFs (fetch_rogo.py -> raw/monroe/rogo.json 3,920 rows), clerk foreclosure+probate (fetch_clerk_monroe.py, public no login).
- Findings: LandmarkWeb (or.monroe-clerk.com) official records = reCAPTCHA gated (lis pendens not scraped); county-taxes.net / lienhub = Cloudflare challenge; monroe.realtaxdeed.com/realforeclose = 403 from box; Keys Weekly legal PDFs have tax-deed applications only Feb-Mar 2026 (28 parcels, sale 3/25/26).
- PA link bug: folio is 20 digits (3367 25 + 14-digit RE), paUrl needs last 14 digits as 8-6.
- ROGO final allocation period closed 7/13/2026; next opens ~7/13/2027 (657 new allocs pending ordinance) -> vacant lots w/o award can't get market-rate ROGO now.
