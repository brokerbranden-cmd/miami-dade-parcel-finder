# Skip trace feature progress (resume-friendly)
Started 2026-10-16 ~16:15 ET. New files: skiptrace.js (logic+store), skiptrace-ui.js (UI), tests/unit_skiptrace.js, tests/e2e_skiptrace.py. README section added.
Don't commit data/*.gz, meta.json, shots/, tests/export_sample.csv. Never git clean / git add -A at top level (use explicit paths).
## Log (times are box clock, ET)
- built skiptrace.js (csv, owner split, address/mailing normalize, column detect, matcher, per-county store) + unit tests (node tests/unit_skiptrace.js, all pass)
- built skiptrace-ui.js (cards/drawer/table rendering, export modal, text list modal, import mapping modal + match report), index.html panel, app.js hooks (filters ph/trc, PF.skBridge, pending bar team/list), ui.css, counties.js nameOrder, sw.js shell v15
- e2e_skiptrace desktop green locally
- 16:47 started regression runner /workspace/tmp/full_st.sh -> test_runs/summary_st_*.txt (unit, skiptrace, export, sendmark, deterrents, outreach, monroe, scenarios, simplified, saved x desktop+mobile, county)
## TODO after runner is green
- add keydown (Enter/Space) on #stImportLbl; screenshots check; push; verify live (e2e_skiptrace + e2e_export/sendmark/deterrents vs live URL)
