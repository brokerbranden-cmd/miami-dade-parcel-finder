"""Imported by the older e2e suites: runs the simplified UI in 'legacy' mode (every filter group, preset and drawer section
open, detailed cards, phone filters inline) so their selectors keep working. The simplified defaults (collapsed groups,
More ideas, compact cards, phone bottom sheet) are covered by tests/scenarios.py and tests/e2e_simplified.py."""
from playwright.sync_api import Browser, BrowserContext
JS = "try{ localStorage.setItem('pf.ui.v1', JSON.stringify({legacy:true, detail:true})); }catch(e){}"
_nc, _np = Browser.new_context, Browser.new_page
def new_context(self, *a, **k):
    c = _nc(self, *a, **k); c.add_init_script(JS); return c
def new_page(self, *a, **k):
    p = _np(self, *a, **k); p.context.add_init_script(JS); return p
Browser.new_context, Browser.new_page = new_context, new_page
