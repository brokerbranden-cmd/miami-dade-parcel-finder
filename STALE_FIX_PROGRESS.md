# Stale-source fix progress (started 2026-10-21 21:30 EDT)
- permits: county ArcGIS groupBy returns HTTP 400 at offset ~26000 (after Oct 18 schema change); city ok.
- energov: many tenants fail "cannot read tenants" (tenant lookup) + Miami Beach read timeouts.
- clerk_clp: Turnstile; scrape disabled.
- [21:40] fetch_permits.py: keyset paging (FolioNumber > last) + backoff + page halving. Test pull running -> /tmp/pt.
- [21:42] fetch_energov.py: root cause = burst of 14 simultaneous GetTenants calls throttled by tylerhost WAF (4x5s retry too short) and any single portal error failed the whole source. Fix: staggered starts, exp. backoff, sequential second pass, partial errors -> summary.json; also cached windows in last 120 days are now re-pulled (before: never refreshed = silent staleness). Full pull running -> /tmp/energov.log
- [21:45] refresh_status.py: clerk / clerk_clp / probate last_good = newest filing date held, stale if > 3 days. LP through 2026-10-05, probate 2026-10-08 -> stale.
- weekly_launch.sh: detached launcher returning immediately.
- Clerk: logged-in Official Records account avoids Turnstile ("Registered Access"); only paid API ($0.20/req, CFN/folio lookup only - no doc-type/date search) or $110/mo FTP otherwise. Needs browser export step.
