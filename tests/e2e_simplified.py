"""Simplified UI (ui.js / ui.css), default mode: results-first layout (sidebar on desktop, bottom sheet on phones), collapsible
filter groups with active-filter badges that persist, 8 presets + More ideas, neutral chips (orange only when selected),
compact cards (3 badges + "+N", Call center / Door knock behind ⋯), Detailed cards toggle, drawer sections.
argv: URL [desktop|mobile] [SHOTS_DIR]"""
import sys, re
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/'
MOB = len(sys.argv) > 2 and sys.argv[2] == 'mobile'; TAG = 'mobile' if MOB else 'desktop'
SHOTS = sys.argv[3] if len(sys.argv) > 3 else '/workspace/parcel-finder/shots/simplified/'
errs = []
def ok(c, m):
    print(('PASS ' if c else 'FAIL ') + f'[{TAG}] ' + m, flush=True)
    if not c: errs.append(m)
cnt = lambda: int(pg.inner_text('#sCount').replace(',', ''))
with sync_playwright() as pw:
    b = pw.chromium.launch(); vp = {'width': 390, 'height': 844} if MOB else {'width': 1440, 'height': 900}
    ctx = b.new_context(viewport=vp, is_mobile=MOB, has_touch=MOB, accept_downloads=True); pg = ctx.new_page()
    pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
    pg.on('console', lambda m: m.type == 'error' and not re.search(r'arcgisonline|Failed to load resource|net::', m.text) and errs.append('console: ' + m.text))
    pg.goto(URL.split('#')[0] + ('?drive=0' if MOB else ''), timeout=180000)
    if MOB and pg.query_selector('#drive:not([hidden])'): pg.click('#dExit')
    pg.wait_for_selector('#results:not([hidden])', timeout=240000); pg.wait_for_function('window.PFUI', timeout=60000); pg.wait_for_timeout(1500)
    if not pg.is_disabled('#resetBtn'): pg.click('#resetBtn'); pg.wait_for_timeout(1200)
    total = cnt()
    top = pg.evaluate("document.getElementById('results').getBoundingClientRect().top")
    ok(top < 400, f'results start on the first screen ({top:.0f}px from the top)')
    ok(pg.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'no horizontal scroll')
    if MOB:
        ok(not pg.is_visible('#panel') and pg.is_visible('#filtersBtn'), 'phone: filters hidden behind the Filters button')
        pg.click('#filtersBtn'); pg.wait_for_timeout(400); ok(pg.is_visible('#panel') and pg.is_visible('#sheetDone'), 'Filters opens the bottom sheet')
        pg.screenshot(path=f'{SHOTS}after_mobile_sheet.png')
    else:
        ok(pg.is_visible('#panel') and pg.evaluate("getComputedStyle(document.getElementById('panel')).position") == 'sticky', 'desktop: filters in a sticky sidebar')
        bx = pg.query_selector('#q').bounding_box(); ok(bx['width'] > 250, f'search box is full width in the sidebar ({bx["width"]:.0f}px)')
        cb = pg.query_selector('#city').bounding_box(); ok(cb['width'] > 120, f'city box readable ({cb["width"]:.0f}px)')
    # groups
    closed = pg.eval_on_selector_all('.cgrp.closed', 'e=>e.map(x=>x.dataset.g)'); opened = pg.eval_on_selector_all('.cgrp:not(.closed)', 'e=>e.map(x=>x.dataset.g)')
    ok('distress signals' in opened and 'search' in opened and len(closed) >= 8, f'{len(opened)} groups open, {len(closed)} collapsed')
    ok(not pg.is_visible('#tierSeg'), 'Teardown controls hidden while the group is collapsed')
    pg.click('.cgrp[data-g="teardown"] .gtog'); pg.wait_for_timeout(200); ok(pg.is_visible('#tierSeg'), 'clicking the header expands Teardown')
    pg.click('#tierSeg button[data-tier="strong"]'); pg.wait_for_timeout(1500); n_strong = cnt()
    pg.click('.cgrp[data-g="teardown"] .gtog'); pg.wait_for_timeout(300)
    ok(pg.inner_text('.cgrp[data-g="teardown"] .gact') == '1', 'collapsed Teardown shows a "1" active badge')
    ok(pg.get_attribute('.cgrp[data-g="teardown"] .gtog', 'aria-expanded') == 'false', 'aria-expanded=false when collapsed')
    pg.click('.cgrp[data-g="who owns it"] .gtog'); pg.wait_for_timeout(200)
    # chips: neutral, orange when selected
    on_bg = pg.evaluate("getComputedStyle(document.querySelector('#tierSeg button.on')||document.querySelector('#panel .chip.on')).backgroundColor")
    sig = pg.query_selector('#dsigs .chip'); off_bg = pg.evaluate("e=>getComputedStyle(e).backgroundColor", sig)
    pg.click('#dsigs .chip[data-sig="LP"]'); pg.wait_for_timeout(1200); lp_bg = pg.evaluate("getComputedStyle(document.querySelector('#dsigs .chip[data-sig=\"LP\"]')).backgroundColor")
    ok(lp_bg == 'rgb(252, 76, 2)', f'selected chip is brand orange ({lp_bg})')
    ok(off_bg == pg.evaluate("getComputedStyle(document.querySelector('#types .chip:not(.on)')).backgroundColor"), 'unselected chips share one neutral style')
    pg.click('#dsigs .chip[data-sig="LP"]'); pg.wait_for_timeout(1000)
    # presets
    vis = [c for c in pg.query_selector_all('#ideas .chip[data-i]') if c.is_visible()]
    ok(len(vis) == 8, f'{len(vis)} presets shown up front'); ok(pg.is_visible('#moreIdeas') and 'More ideas' in pg.inner_text('#moreIdeas'), pg.inner_text('#moreIdeas'))
    pg.click('#moreIdeas'); pg.wait_for_timeout(200)
    cats = pg.eval_on_selector_all('#ideasMore .icat-h', 'e=>e.map(x=>x.textContent)'); allv = [c for c in pg.query_selector_all('#ideas .chip[data-i]') if c.is_visible()]
    ok(len(allv) == len(pg.query_selector_all('#ideas .chip[data-i]')) and len(cats) >= 2, f'More ideas shows all {len(allv)} presets in groups {cats}')
    sp = next(c for c in pg.query_selector_all('#ideasMore .chip[data-i]') if 'split' in c.inner_text().lower()); sp.click(); pg.wait_for_timeout(1500)
    ok(0 < cnt() < total, f'a preset from More ideas works ({cnt():,})')
    if MOB:
        pg.wait_for_timeout(300); ok(not pg.is_visible('#panel'), 'phone: choosing a preset closes the sheet to show results')
    # persistence of open groups / more ideas
    pg.reload(); pg.wait_for_selector('#results:not([hidden])', timeout=240000); pg.wait_for_function('window.PFUI', timeout=60000); pg.wait_for_timeout(1200)
    ok(pg.get_attribute('.cgrp[data-g="who owns it"]', 'class').find('closed') < 0, 'opened group stays open after reload')
    ok(pg.get_attribute('#ideasMore', 'hidden') is None, 'More ideas stays open after reload')
    if MOB: pg.click('#filtersBtn'); pg.wait_for_timeout(300)
    pg.click('#moreIdeas'); pg.wait_for_timeout(100)
    if MOB: pg.click('#sheetClose'); pg.wait_for_timeout(300)
    pg.click('#resetBtn'); pg.wait_for_timeout(1500); ok(cnt() == total, 'Clear all')
    # compact cards
    if MOB: pass
    cards = pg.query_selector_all('#cards .card')[:12]
    many = next((c for c in cards if c.query_selector('.obmore')), None)
    ok(many is not None, 'a card with more than 3 labels shows a "+N" button')
    if many:
        shown = len([x for x in many.query_selector_all('.ob > *:not(.obmore)') if x.is_visible()]); ok(shown == 3, f'only 3 labels shown ({shown})')
        many.query_selector('.obmore').click(); pg.wait_for_timeout(200)
        ok(len([x for x in many.query_selector_all('.ob > *') if x.is_visible()]) > 3 and pg.query_selector('.drawer') is None, '+N expands the labels without opening the drawer')
    c0 = pg.query_selector('#cards .card'); f0 = c0.get_attribute('data-folio')
    ok(not c0.query_selector('[data-sendtag="cc"]').is_visible(), 'Call center / Door knock hidden behind ⋯')
    c0.query_selector('.cmore').click(); pg.wait_for_timeout(200)
    ok(c0.query_selector('[data-sendtag="cc"]').is_visible() and pg.query_selector('.drawer') is None, '⋯ shows them (drawer stays closed)')
    c0.query_selector('[data-sendtag="cc"]').click(); pg.wait_for_timeout(400)
    ok('on' in (pg.query_selector(f'#cards .card[data-folio="{f0}"] [data-sendtag="cc"]').get_attribute('class') or ''), 'tagging from the ⋯ menu works')
    if not pg.query_selector(f'#cards .card[data-folio="{f0}"] [data-sendtag="cc"]').is_visible(): pg.click(f'#cards .card[data-folio="{f0}"] .cmore'); pg.wait_for_timeout(200)  # tagging re-renders the card, which may close ⋯
    pg.query_selector(f'#cards .card[data-folio="{f0}"] [data-sendtag="cc"]').click(); pg.wait_for_timeout(300)
    h = pg.evaluate("Math.round(document.querySelector('#cards .card').getBoundingClientRect().height)"); ok(h < 520, f'compact card height {h}px (was 540; includes the Skip trace line)')
    pg.screenshot(path=f'{SHOTS}after_{TAG}_cards_compact.png')
    pg.click('#detailBtn'); pg.wait_for_timeout(300)
    dv = pg.evaluate("[document.body.className, getComputedStyle(document.querySelector('#cards .card .sendtools')).display, document.querySelector('#detailBtn').textContent]")
    ok(dv[1] != 'none' and 'Compact' in dv[2], f'Detailed cards shows every label and button {dv}')
    pg.click('#detailBtn'); pg.wait_for_timeout(300)
    # drawer sections
    pg.click('#cards .card h3'); pg.wait_for_selector('.drawer .dsec', timeout=60000); pg.wait_for_timeout(800)
    secs = pg.eval_on_selector_all('.drawer .dsec', 'e=>e.map(x=>[x.querySelector("h3").innerText.trim(), x.classList.contains("closed")])')
    ok(secs[0][0].lower().startswith('the property') and not secs[0][1], f'drawer opens with the property facts first: {[s[0] for s in secs[:3]]}')
    ok(sum(1 for s in secs if s[1]) >= 3, f'{sum(1 for s in secs if s[1])} sections collapsed')
    ok(pg.is_visible('#savedBox') and pg.is_visible('.drawer .links'), 'overview (links, save) always visible')
    dist = next((k for k, s in enumerate(secs) if s[0].lower().startswith('distress')), None)
    if dist is not None:
        pg.click(f'.drawer .dsec:nth-of-type({dist + 1}) .dtog'); pg.wait_for_timeout(200)
        ok(pg.is_visible('.drawer .dbreak') or 'distress score' in pg.inner_text('.drawer').lower(), 'expanding Distress shows the breakdown')
    pg.screenshot(path=f'{SHOTS}after_{TAG}_drawer_sections.png'); pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
    # every feature still reachable: toolbar + header buttons visible
    for sel in ('#driveBtn', '#lendersBtn', '#savedBtn', '#resetBtn', '#vCards', '#vTable', '#vMap', '#exportBtn', '#copyBtn', '#linkBtn', '#sortSel', '#detailBtn'):
        ok(pg.is_visible(sel), f'{sel} visible')
    if MOB: pg.click('#filtersBtn'); pg.wait_for_timeout(300)
    for g in pg.eval_on_selector_all('.cgrp.closed', 'e=>e.map(x=>x.dataset.g)'):
        pg.click(f'.cgrp[data-g="{g}"] .gtog'); pg.wait_for_timeout(60)
    for sel in ('#q', '#city', '#zips', '#dsigs', '#pcsigs', '#vsigs', '#types', '#mzq', '#zones', '#lotz', '#asmOn', '#tierSeg', '#td_land', '#ownerKind', '#lotMin', '#mvMax', '#cnChips', '#apOnly', '#sendChips', '#moreBox'):
        ok(pg.is_visible(sel), f'{sel} reachable')
    b.close()
print('ERRORS', errs) if errs else print('ALL OK'); sys.exit(1 if errs else 0)
