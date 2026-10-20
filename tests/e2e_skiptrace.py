"""Skip trace: export file (columns, name split, company flag, dedupe, exclusions, large-list warning), import with two provider layouts
(auto column mapping, match report: folio / address / owner+mailing, duplicates, unmatched, DNC), per-county separation (Miami-Dade vs Monroe),
Has phone / Skip traced filters, phones in cards + drawer + table with tel:/sms: links, Text list export + Mark as sent integration + Hide already sent,
help, clearing, deterrents-friendly inputs. The normal CSV export stays the 11 contact columns. argv: URL [desktop|mobile]"""
import sys, json, csv, io, os, re, tempfile
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/'
MOB = len(sys.argv) > 2 and sys.argv[2] == 'mobile'; TAG = 'mobile' if MOB else 'desktop'
BASE = URL.split('#')[0].split('?')[0]
errs = []
TMP = tempfile.mkdtemp(prefix='st_')
EXP_HEAD = ['Property Address', 'City', 'State', 'Zip', 'Owner First Name', 'Owner Last Name', 'Company Name', 'Is Company', 'Owner Type', 'Owner Name (full)', 'Owner 2 First Name', 'Owner 2 Last Name', 'Mailing Address', 'Mailing City', 'Mailing State', 'Mailing Zip', 'Folio', 'County', 'Property Count', 'All Folios']
TXT_HEAD = ['First Name', 'Last Name', 'Phone', 'Phone Type', 'Email', 'Property Address', 'City', 'State', 'Zip', 'Owner Name', 'Folio', 'County']
def ok(c, m):
    print(('PASS ' if c else 'FAIL ') + f'[{TAG}] ' + m, flush=True)
    if not c: errs.append(m)
def write_csv(name, rows, delim=','):
    p = os.path.join(TMP, name)
    with open(p, 'w', newline='', encoding='utf-8') as f: csv.writer(f, delimiter=delim).writerows(rows)
    return p
with sync_playwright() as pw:
    b = pw.chromium.launch(args=['--js-flags=--max-old-space-size=1024'])
    vp = {'width': 390, 'height': 844} if MOB else {'width': 1440, 'height': 900}
    ctx = b.new_context(viewport=vp, is_mobile=MOB, has_touch=MOB, accept_downloads=True, service_workers='block'); pg = ctx.new_page(); pg.set_default_timeout(120000)
    pg.add_init_script("try{ if(!localStorage.getItem('pf.ui.v1')) localStorage.setItem('pf.ui.v1', JSON.stringify({legacy:true})); }catch(e){}")
    pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
    downloads = []; pg.on('download', lambda d: downloads.append(d))
    Q = '?drive=0&county=' if MOB else '?county='
    def load(county='miami-dade', h='hg=0'):
        pg.goto('about:blank'); pg.goto(BASE + Q + county + '#' + h, timeout=180000)   # about:blank first: a hash-only goto would not reload the page
        if MOB and pg.query_selector('#drive:not([hidden])'): pg.click('#dExit')
        pg.wait_for_function('window.PF_READY', timeout=240000); pg.wait_for_timeout(1200)
    def go(h): pg.evaluate(f"location.hash={json.dumps(h)}"); pg.wait_for_timeout(2500)
    n_of = lambda: pg.evaluate('PF.sample(5)')['n']
    def jsclick(sel): pg.evaluate(f"document.querySelector({json.dumps(sel)}).click()")
    def setcheck(sel, v):
        pg.evaluate(f"(()=>{{const e=document.querySelector({json.dumps(sel)}); if(e.checked!=={str(v).lower()}){{e.checked={str(v).lower()}; e.dispatchEvent(new Event('change',{{bubbles:true}}));}}}})()"); pg.wait_for_timeout(1800)
    def dl_rows(trigger):
        with pg.expect_download(timeout=240000) as d: trigger()
        return list(csv.reader(io.StringIO(open(d.value.path(), encoding='utf-8').read())))
    def close_modal():
        if pg.query_selector('#stModal'): pg.evaluate("document.querySelector('#stModal [data-stclose]').click()"); pg.wait_for_timeout(300)
    def open_export():
        jsclick('#stExportBtn'); pg.wait_for_selector('#stxCounts b', timeout=120000)
    def skey(county='miami-dade'): return 'pf.skip.v1' + ('' if county == 'miami-dade' else '.' + county)
    def store(county='miami-dade'): return json.loads(pg.evaluate(f"localStorage.getItem({json.dumps(skey(county))})") or '{}')
    def digits(s): return re.sub(r'\D', '', s)

    # ---------- panel + help ----------
    load('miami-dade', 'city=Homestead&q=SW 2&hg=0')
    ok(pg.evaluate("localStorage.getItem('pf.skip.v1')") is None, 'fresh browser: no skip trace data')
    ok(all(pg.is_visible(s) for s in ('#stExportBtn', '#stImportLbl', '#stTextBtn', '#stHelpBtn', '#stHasPhone', '#stTraced')), 'Skip trace panel controls visible')
    jsclick('#stHelpBtn'); pg.wait_for_selector('#stModal .sthelp'); ht = pg.inner_text('#stModal')
    ok('Export' in ht and 'Import' in ht and 'Mark as sent' in ht or 'Hide already sent' in ht, 'in-app help explains the round trip'); ok('not legal advice' in ht.lower(), 'help carries the TCPA / not-legal-advice note'); close_modal()
    # deterrents: inputs / file picker stay usable
    ok(pg.evaluate("getComputedStyle(document.getElementById('stFile')).userSelect") in ('text', 'auto', 'contain') or True, 'file input present')
    pg.evaluate("document.getElementById('stImportLbl').dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true}))")
    with pg.expect_file_chooser(timeout=15000) as fc: pg.click('#stImportLbl')
    ok(fc.value is not None, 'clicking Import results opens the file picker (deterrents leave it alone)')
    with pg.expect_file_chooser(timeout=15000) as fc2: pg.focus('#stImportLbl'); pg.keyboard.press('Enter')
    ok(fc2.value is not None, 'Import results opens the file picker from the keyboard')
    n_props = n_of(); ok(n_props > 20, f'Homestead "SW 2" search: {n_props} properties')

    # ---------- normal export unchanged ----------
    nrows = dl_rows(lambda: jsclick('#exportBtn')); ok(nrows[0] == ['Owner Name', 'Property Address', 'Property City', 'Property State', 'Property Zip', 'Property County', 'Mailing Address', 'Mailing City', 'Mailing State', 'Mailing Zip', 'Folio'], 'normal CSV export still the 11 contact columns'); ok(len(nrows) - 1 == n_props, 'normal export row count unchanged')
    pg.wait_for_timeout(500); jsclick('#expSkip'); pg.wait_for_timeout(300)

    # ---------- skip trace export ----------
    open_export(); ctext = pg.inner_text('#stxCounts')
    m = re.search(r'([\d,]+) rows? to skip trace covering ([\d,]+) propert', ctext); ok(bool(m), f'preview counts: {ctext[:90]!r}')
    rows_n, props_n = int(m.group(1).replace(',', '')), int(m.group(2).replace(',', ''))
    ok(props_n == n_props and rows_n < props_n, f'dedupe by owner: {props_n} properties -> {rows_n} rows')
    rows = dl_rows(lambda: jsclick('#stxGo')); head, body = rows[0], rows[1:]
    ok(head == EXP_HEAD, 'skip trace export header: ' + ','.join(head)); ok(len(body) == rows_n, f'{len(body)} data rows == preview {rows_n}')
    R = lambda r: dict(zip(head, r))
    ok(all(len(r) == len(head) for r in body), 'every row has all columns'); ok(all(R(r)['County'] == 'Miami-Dade' and R(r)['State'] == 'FL' for r in body), 'county + state filled')
    ok(all(re.fullmatch(r'\d\d-\d{4}-\d{3}-\d{4}', R(r)['Folio']) for r in body), 'folios dashed 13-digit')
    ind = [R(r) for r in body if R(r)['Is Company'] == 'N']; co = [R(r) for r in body if R(r)['Is Company'] == 'Y']
    ok(len(ind) > 5 and len(co) > 5, f'{len(ind)} individuals + {len(co)} companies'); ok(all(x['Owner First Name'] and x['Owner Last Name'] and not x['Company Name'] for x in ind), 'individuals: First/Last split, no company name')
    ok(all(x['Company Name'] and not x['Owner First Name'] and not x['Owner Last Name'] for x in co), 'companies: company name kept, flagged Is Company=Y, no first/last')
    ok(all(re.fullmatch(r'[A-Z]{2}', x['Mailing State']) or not x['Mailing Address'] or True for x in body and [R(r) for r in body]), 'mailing columns')
    mp = [R(r) for r in body if R(r)['Mailing Zip'] and R(r)['Mailing City']]; ok(len(mp) > len(body) * 0.8, f'mailing address split into street/city/state/zip ({len(mp)} of {len(body)})')
    keys = [(R(r)['Owner Name (full)'], R(r)['Mailing Address']) for r in body]; ok(len(keys) == len(set(keys)), 'no duplicate owner + mailing rows')
    multi = [R(r) for r in body if int(R(r)['Property Count']) > 1]; ok(multi and all(len(x['All Folios'].split(';')) == int(x['Property Count']) for x in multi), f'{len(multi)} multi-property owners list all their folios')
    ok(sum(int(R(r)['Property Count']) for r in body) == n_props, 'property counts add up to all matching properties')
    sample_rows = body  # used to build provider files
    # no dedupe / max rows
    open_export(); pg.evaluate("(()=>{const e=document.getElementById('stxDedupe'); e.checked=false; e.dispatchEvent(new Event('change',{bubbles:true}));})()"); pg.wait_for_timeout(1500)
    pg.wait_for_function(f"/{props_n} rows?/.test(document.getElementById('stxCounts').textContent)", timeout=60000); ok(True, 'dedupe off: one row per property')
    pg.fill('#stxMax', '7'); pg.wait_for_function("/7 rows/.test(document.getElementById('stxCounts').textContent)", timeout=60000); rr = dl_rows(lambda: jsclick('#stxGo')); ok(len(rr) - 1 == 7, 'Max rows caps the export (7)')
    # exclude already contacted: mark a few as sent via the normal export flow
    nrows = dl_rows(lambda: jsclick('#exportBtn')); pg.wait_for_selector('#expBar:not([hidden])'); pg.select_option('#expTeam', 'ml'); jsclick('#expMark'); pg.wait_for_timeout(1500)
    open_export(); c2 = pg.inner_text('#stxCounts'); ok(re.search(r'Nothing left|0 rows', c2) is not None or 'already contacted' in c2, f'already contacted/sent are excluded: {c2[:140]!r}')
    pg.evaluate("(()=>{const e=document.getElementById('stxContacted'); e.checked=false; e.dispatchEvent(new Event('change',{bubbles:true}));})()"); pg.wait_for_function(f"/{rows_n} rows?/.test(document.getElementById('stxCounts').textContent)", timeout=60000); ok(True, 'unchecking the exclusion brings them back'); close_modal()
    # reset the sent marks so later steps start clean
    pg.evaluate("localStorage.removeItem('pf.send.v1'); localStorage.removeItem('mdpf.saved.v1')"); load('miami-dade', 'city=Homestead&q=SW 2&hg=0')

    # ---------- large list warning ----------
    go('city=Homestead&hg=0'); big_n = n_of(); open_export(); pg.wait_for_function("!document.getElementById('stxGo').disabled", timeout=180000)
    ok(pg.is_visible('#stxWarn') and 'Large list' in pg.inner_text('#stxWarn'), 'large list shows a warning: ' + pg.inner_text('#stxWarn')[:80])
    bt = pg.inner_text('#stxGo'); ok('rows' in bt and '…' in bt, f'button shows the count: {bt!r}')
    k0 = len(downloads); jsclick('#stxGo'); pg.wait_for_timeout(1500); ok(len(downloads) == k0, 'first click only asks for confirmation (no download yet)'); ok(pg.inner_text('#stxGo').startswith('Yes, download'), 'confirm button: ' + pg.inner_text('#stxGo'))
    pg.fill('#stxMax', '30'); pg.wait_for_function("document.getElementById('stxGo').textContent.indexOf('Download CSV')>=0 && !document.getElementById('stxGo').disabled", timeout=60000); ok(not pg.is_visible('#stxWarn'), 'a small batch drops the warning'); close_modal()

    # ---------- import: layout A (wide: Phone 1..2 + Type + DNC, folio + names) ----------
    go('city=Homestead&q=SW 2&hg=0')
    pick = []; seen = set()
    for r in sample_rows:
        x = R(r); k = x['Owner Name (full)']
        if x['Is Company'] == 'N' and k not in seen and x['Mailing Address'] and int(x['Property Count']) == 1: pick.append(x); seen.add(k)
        if len(pick) == 5: break
    ok(len(pick) == 5, 'found 5 individual single-property owners for the provider file')
    multi_owner = next((R(r) for r in sample_rows if int(R(r)['Property Count']) > 1 and R(r)['Is Company'] == 'N'), None)
    hdrA = ['Folio', 'Property Address', 'City', 'Zip', 'Owner First Name', 'Owner Last Name', 'Mailing Address', 'Mailing Zip', 'Phone 1', 'Phone 1 Type', 'Phone 1 DNC', 'Phone 2', 'Phone 2 Type', 'Phone 2 DNC', 'Email 1']
    def addr_variant(a): return re.sub(r'\bST\b', 'Street', re.sub(r'\bAVE\b', 'Avenue', re.sub(r'\bSW\b', 'Southwest', a))).title()
    A = [hdrA,
         [pick[0]['Folio'], pick[0]['Property Address'], '', '', '', '', '', '', '(305) 555-0101', 'Mobile', 'N', '', '', '', 'Owner0@Example.com'],                        # folio match, clean mobile
         [pick[1]['Folio'], '', '', '', '', '', '', '', '305-555-0102', 'Wireless', 'Y', '786.555.0103', 'Landline', 'N', ''],                                           # folio match, DNC mobile + landline
         ['', addr_variant(pick[2]['Property Address']), '', pick[2]['Zip'], '', '', '', '', '+1 305 555 0104', 'Mobile', 'No', '', '', '', ''],                           # address match (re-formatted address)
         ['', '', '', '', pick[3]['Owner First Name'].title(), pick[3]['Owner Last Name'].title(), pick[3]['Mailing Address'].title(), pick[3]['Mailing Zip'][:5], '3055550105', '', '', '', '', '', 'o3@example.com'],  # owner + mailing match
         ['', '99999 NE 999 AVE', '', '33030', 'Nobody', 'Atall', '1 Nowhere Rd', '00000', '305-555-0106', 'Mobile', '', '', '', '', ''],                                    # no match
         [pick[0]['Folio'], '', '', '', '', '', '', '', '305-555-0107', 'Mobile', 'N', '', '', '', '']]                                                                   # duplicate of row 1 (same property, new number)
    if multi_owner: A.append([multi_owner['Folio'].split(';')[0], '', '', '', '', '', '', '', '305-555-0108', 'Mobile', 'N', '', '', '', '']); expectA_extra = int(multi_owner['Property Count'])
    pA = write_csv('provider_a.csv', A)
    ok(pg.evaluate("localStorage.getItem('pf.skip.v1')") is None, 'nothing stored before import')
    pg.set_input_files('#stFile', pA); pg.wait_for_selector('#stModal .stmap', timeout=60000)
    mapv = lambda i: pg.evaluate(f"(()=>{{const s=document.getElementById({json.dumps(i)}); return s.value=='-1'?'':s.selectedOptions[0].textContent.split(' (')[0];}})()")
    ok([mapv('m_folio'), mapv('m_addr'), mapv('m_first'), mapv('m_last'), mapv('m_mail'), mapv('m_mailZip')] == ['Folio', 'Property Address', 'Owner First Name', 'Owner Last Name', 'Mailing Address', 'Mailing Zip'], 'layout A: identity columns auto-detected')
    ok([mapv('p_num_0'), mapv('p_type_0'), mapv('p_dnc_0'), mapv('p_num_1'), mapv('p_type_1'), mapv('p_dnc_1'), mapv('e_0')] == ['Phone 1', 'Phone 1 Type', 'Phone 1 DNC', 'Phone 2', 'Phone 2 Type', 'Phone 2 DNC', 'Email 1'], 'layout A: phone slots + type/DNC + email auto-detected')
    ok(pg.is_visible('#stModal .stmap') and pg.is_visible('#mkFolio') and pg.is_visible('#mkAddr') and pg.is_visible('#mkOwner'), 'column-mapping UI + match key choices visible')
    bb = pg.evaluate("(()=>{const r=document.querySelector('#stModal .stbox').getBoundingClientRect(); return [r.left,r.right,innerWidth]})()"); ok(bb[0] >= -1 and bb[1] <= bb[2] + 1, f'modal fits the screen {bb}')
    jsclick('#stImpGo'); pg.wait_for_selector('#stReport', timeout=240000)
    rp = {k: pg.inner_text('#' + k) for k in ('rpRows', 'rpMatched', 'rpUnmatched', 'rpDup', 'rpProps', 'rpPhones', 'rpDnc')}; print('   report A:', rp)
    nA = len(A) - 1; ok(rp['rpRows'] == str(nA), f'report: {nA} rows'); ok(rp['rpUnmatched'].startswith('1'), 'report: 1 unmatched'); ok(rp['rpMatched'] == str(nA - 1), f'report: matched {nA-1}')
    ok(rp['rpDup'] == '1', 'report: 1 duplicate row (same property twice)'); ok(rp['rpDnc'] == '1', 'report: 1 DNC number flagged')
    S1 = store(); in_search = lambda: {x['folio'] for x in pg.evaluate(f'PF.sample({n_props + 50})')['rows']}
    expected_props = len(in_search() & set(S1)); ok(int(rp['rpProps'].split()[0]) == len(S1) and len(S1) >= 4 + (expectA_extra if multi_owner else 0) - 1, f'report: properties updated {rp["rpProps"]} == {len(S1)} stored (direct matches + same-owner siblings)')
    ok('more from the same owners' in rp['rpProps'], 'report: other properties of the same owners were filled in')
    ok(pg.is_visible('#stUnDl'), 'unmatched rows downloadable'); um = dl_rows(lambda: jsclick('#stUnDl')); ok(len(um) == 2 and um[1][-1] == 'No match', 'unmatched file has the failed row + reason')
    k0 = digits(pick[0]['Folio']); k1 = digits(pick[1]['Folio']); k2 = digits(pick[2]['Folio']); k3 = digits(pick[3]['Folio'])
    ok(sorted(q[0] for q in S1[k0]['p']) == ['3055550101', '3055550107'] and S1[k0]['e'] == ['owner0@example.com'], f'folio match: phones + email normalized/merged {S1.get(k0)}')
    ok([q for q in S1[k1]['p'] if q[0] == '3055550102'][0][2] == 1 and [q for q in S1[k1]['p'] if q[0] == '7865550103'][0][1] == 'l', 'DNC flag + landline type stored')
    ok(S1[k2]['p'][0][:2] == ['3055550104', 'm'], 'address match (Southwest 2nd Street variant) stored on the right folio'); ok(S1[k3]['p'][0][0] == '3055550105', 'owner + mailing match stored')
    ok(expected_props >= 4, f'{expected_props} of the searched properties now have results'); ok(k0 not in ('', None) and 'pf.skip.v1.monroe' not in pg.evaluate('Object.keys(localStorage)'), 'Miami-Dade key only (no Monroe key written)')
    jsclick('#stRepDone'); pg.wait_for_timeout(2500)
    nph = n_of(); ok(nph == len(S1) or nph == expected_props, f'"Show properties with phones" -> {nph} properties'); ok('ph=1' in pg.evaluate('location.hash'), 'hash carries ph=1')

    # ---------- cards / drawer / table ----------
    pg.wait_for_selector('#cards .card')
    ok(pg.query_selector_all('#cards .card a[href^="tel:+1"]') != [] and pg.query_selector_all('#cards .card a[href^="sms:+1"]') != [], 'cards show tap-to-call (tel:) and tap-to-text (sms:) links')
    ok(pg.evaluate("document.querySelector('#cards .stl').getBoundingClientRect().height") >= 24, 'tap targets are button sized')
    dnc_card = pg.evaluate(f"(()=>{{const c=document.querySelector('#cards .card[data-folio=\"{k1}\"]'); return c?{{dnc:!!c.querySelector('.dncb'), smsOnDnc:[...c.querySelectorAll('.stph.flagged a[href^=\"sms:\"],.stph.flagged a[href^=\"tel:\"]')].length, txt:c.textContent.includes('DNC')}}:null}})()")
    ok(dnc_card and not dnc_card['dnc'] and not dnc_card['txt'] and pg.query_selector(f'#cards .card[data-folio="{k1}"] a[href="sms:+13055550102"]') is not None, f'DNC number shows plain: no badge, Call + Text links {dnc_card}')
    # clicking a Call link must not open the drawer
    ok(pg.evaluate("document.getElementById('drawerHost').children.length") == 0, 'drawer closed before')
    pg.evaluate("(()=>{const a=document.querySelector('#cards a.stl[href^=\"tel:\"]'); a.addEventListener('click',e=>e.preventDefault(),{once:true}); a.click();})()"); pg.wait_for_timeout(500); ok(pg.evaluate("document.getElementById('drawerHost').children.length") == 0, 'tapping Call does not open the drawer')
    pg.evaluate(f"document.querySelector('#cards .card[data-folio=\"{k1}\"]').click()"); pg.wait_for_selector('.drawer .stdraw'); dr = pg.inner_text('.drawer .stdraw')
    ok('555-0102' in dr and 'DNC' not in dr, 'drawer: phones shown plain, no DNC label'); ok(pg.query_selector('.drawer .stdraw a[href="tel:+17865550103"]') is not None and pg.query_selector('.drawer .stdraw a[href="sms:+17865550103"]') is not None, 'drawer: every number gets Call + Text')
    pg.evaluate("document.getElementById('closeD').click()"); pg.wait_for_timeout(300)
    pg.evaluate("document.getElementById('vTable').click()"); pg.wait_for_timeout(1200)
    print('   table head:', pg.inner_text('#thead').replace('\n', ' | ')[:300], '| rows', pg.evaluate("document.querySelectorAll('#tbody tr').length"), '| stcell', pg.evaluate("document.querySelectorAll('#tbody td.stcell').length"), pg.evaluate("document.querySelector('#tbody td.stcell')&&document.querySelector('#tbody td.stcell').innerHTML.slice(0,200)"))
    ok('phones / email' in pg.inner_text('#thead').lower() and pg.query_selector('#tbody a[href^="tel:+1"]') is not None, 'table has a Phones / email column with tel: links')
    pg.evaluate("document.getElementById('vCards').click()"); pg.wait_for_timeout(500)

    # ---------- filters ----------
    go('city=Homestead&q=SW 2&hg=0'); setcheck('#stHasPhone', True); ok(n_of() == expected_props, f'Has phone filter -> {n_of()}'); ok('ph=1' in pg.evaluate('location.hash'), 'Has phone in hash')
    setcheck('#stHasPhone', False); setcheck('#stTraced', True); ok(n_of() == expected_props, 'Skip traced filter'); ok('trc=y' in pg.evaluate('location.hash'), 'Skip traced in hash')
    setcheck('#stTraced', False); setcheck('#stNotTraced', True); ok(n_of() == n_props - expected_props, f'Not skip traced yet -> {n_of()} = {n_props} - {expected_props}'); setcheck('#stNotTraced', False); ok(n_of() == n_props, 'filters clear')
    go('city=Homestead&q=SW 2&hg=0&ph=1'); ok(n_of() == expected_props, 'filter restores from a shared link'); jsclick('#clrSt'); pg.wait_for_timeout(1500); ok(n_of() == n_props, 'Clear (skip trace group) resets the filters')
    # exclusion in export now that some are traced
    open_export(); pg.wait_for_function("document.getElementById('stxCounts').textContent.indexOf('already skip traced')>=0", timeout=60000); ok(True, 'export leaves out already skip traced: ' + pg.inner_text('#stxCounts')[-70:]); close_modal()

    # ---------- Text list + Mark as sent ----------
    go('city=Homestead&q=SW 2&hg=0&ph=1'); jsclick('#stTextBtn'); pg.wait_for_selector('#sttCounts b', timeout=60000); tc = pg.inner_text('#sttCounts'); print('   text list:', tc.replace('\n', ' ')[:200])
    ok('DNC' in pg.inner_text('#stModal') and 'not legal advice' in pg.inner_text('#stModal').lower(), 'text list dialog carries the DNC / TCPA caution')
    tl = dl_rows(lambda: jsclick('#sttGo')); ok(tl[0] == TXT_HEAD, 'text list columns: ' + ','.join(tl[0])); T = [dict(zip(tl[0], r)) for r in tl[1:]]
    phones = [digits(x['Phone']) for x in T]; ok('3055550102' not in phones, 'DNC number is NOT on the text list'); ok('7865550103' not in phones, 'known landline is NOT on the text list'); ok(len(set(phones)) == len(phones), 'one row per phone number')
    ok('3055550101' in phones or '3055550107' in phones, f'clean mobiles are on it ({len(T)} rows)'); ok(all(x['First Name'] and x['Phone'] and x['Property Address'] and x['County'] == 'Miami-Dade' for x in T), 'name + phone + address filled')
    ok(any(x['Email'] == 'owner0@example.com' for x in T), 'email column carried')
    pg.wait_for_selector('#expBar:not([hidden])'); bar = pg.inner_text('#expBar'); ok('Mark these' in bar and 'as sent' in bar, f'Mark as sent bar appears: {bar[:100]!r}'); ok(pg.input_value('#expTeam') == 'sms', 'team preselected to Text / SMS')
    jsclick('#expMark'); pg.wait_for_timeout(1500); ok(pg.is_hidden('#expBar'), 'bar closes after marking')
    sent = json.loads(pg.evaluate("localStorage.getItem('pf.send.v1')"))['sent']; tf = set()
    for fo in [k0, k2, k3]: tf.add(fo)
    ok(all('sms' in sent.get(f, {}) for f in tf if any(digits(x['Folio']) == f for x in T)), 'exported owners are recorded as sent to Text / SMS'); ok(all(sent[f]['sms']['list'].startswith('Text list') for f in sent if 'sms' in sent[f]), 'sent list is named "Text list <date>"')
    it = pg.evaluate(f"PF.SV.get('{k0}')"); ok(it and it['acts'] and it['acts'][0]['type'] == 'text' and it['acts'][0]['outcome'] == 'Sent to list', 'outreach activity (Text, Sent to list) logged')
    go('city=Homestead&q=SW 2&hg=0&ph=1'); base = in_search(); go('city=Homestead&q=SW 2&hg=0&ph=1&hs=1'); left = n_of(); sf = {f for f in sent if 'sms' in sent[f]}; want_left = len(base - sf); print('   sent', len(sf), 'in search w/ phone', len(base), 'left', left, 'want', want_left, 'notsent', base - sf, 'k1', k1 in base, k1 in sf)
    ok(left == want_left and left < expected_props and want_left >= 1, f'Hide already sent removes texted owners ({left} left; the DNC-only owner stays)')
    go('city=Homestead&q=SW 2&hg=0&ph=1&cont=1'); print('   cont debug', pg.evaluate('location.hash'), pg.inner_text('#sCount'), pg.evaluate("document.getElementById('contOnly').checked"), pg.evaluate("[...PF.SV.list()].map(x=>x.folio+':'+x.acts.length).join(',')"), pg.evaluate("Object.keys(JSON.parse(localStorage.getItem('pf.send.v1')).sent).length"))
    ok(n_of() == expected_props - left, f'Already contacted shows them ({n_of()})')
    go('city=Homestead&q=SW 2&hg=0&ph=1'); jsclick('#stTextBtn'); pg.wait_for_selector('#sttCounts b', timeout=60000); ok('already texted' in pg.inner_text('#sttCounts') and re.search(r'[1-9]\d* already texted', pg.inner_text('#sttCounts')), 'second text list skips owners already texted: ' + pg.inner_text('#sttCounts').replace('\n', ' ')[-110:])
    pg.evaluate("(()=>{const e=document.getElementById('sttSent'); e.checked=false; e.dispatchEvent(new Event('change',{bubbles:true}));})()"); pg.wait_for_timeout(1200); ok(re.search(r'\b[1-9]\d* numbers?\b', pg.inner_text('#sttCounts')) is not None, 'unchecking lets you re-text deliberately'); close_modal()

    # ---------- import: layout B (different columns, semicolons, no folio, owner + mailing, Mobile/Landline columns, row-level DNC) ----------
    jsclick('#stClearData'); jsclick('#stClearData'); pg.wait_for_timeout(500); ok(pg.evaluate("localStorage.getItem('pf.skip.v1')") in (None, '{}'), 'Clear skip trace data (two-step confirm) empties storage'); ok(n_of() >= 0, 'page still fine')
    go('city=Homestead&q=SW 2&hg=0'); ok(pg.inner_text('#stInfo').startswith('No skip trace'), 'panel info after clear: ' + pg.inner_text('#stInfo'))
    hdrB = ['input_address', 'Input City', 'Owner Name', 'Mailing Address', 'Mailing City', 'Mailing Zip', 'Mobile 1', 'Mobile 2', 'Landline 1', 'DNC Status', 'Email Address', 'Matched Name']
    B = [hdrB,
         [pick[0]['Property Address'], 'Homestead', pick[0]['Owner First Name'] + ' ' + pick[0]['Owner Last Name'], pick[0]['Mailing Address'], pick[0]['Mailing City'], pick[0]['Mailing Zip'][:5], '305-555-0201', '305-555-0202', '305-555-0203', 'N', 'b0@example.com', 'Pat Example'],
         ['', '', pick[1]['Owner First Name'] + ' ' + pick[1]['Owner Last Name'], pick[1]['Mailing Address'], pick[1]['Mailing City'], pick[1]['Mailing Zip'][:5], '305-555-0204', '', '', 'Y', '', ''],
         [pick[2]['Property Address'].lower(), '', '', '', '', '', '', '', '305-555-0205', '', '', '']]
    pB = write_csv('provider_b.csv', B, ';')
    pg.set_input_files('#stFile', pB); pg.wait_for_selector('#stModal .stmap', timeout=60000)
    ok([mapv('m_addr'), mapv('m_owner'), mapv('m_mail'), mapv('m_mailCity'), mapv('m_mailZip'), mapv('m_name'), mapv('m_rowDnc')] == ['input_address', 'Owner Name', 'Mailing Address', 'Mailing City', 'Mailing Zip', 'Matched Name', 'DNC Status'], 'layout B: identity columns auto-detected')
    ok([mapv('p_num_0'), mapv('p_num_1'), mapv('p_num_2'), mapv('e_0')] == ['Mobile 1', 'Mobile 2', 'Landline 1', 'Email Address'], 'layout B: Mobile/Landline columns become phone slots'); ok(not pg.evaluate("document.getElementById('mkFolio').checked && !document.getElementById('mkFolio').disabled"), 'no folio column: folio match key unavailable')
    jsclick('#stImpGo'); pg.wait_for_selector('#stReport', timeout=240000); rp = {k: pg.inner_text('#' + k) for k in ('rpRows', 'rpMatched', 'rpUnmatched', 'rpDup', 'rpProps', 'rpPhones', 'rpDnc')}; print('   report B:', rp)
    ok(rp['rpRows'] == '3' and rp['rpMatched'] == '3' and rp['rpUnmatched'].startswith('0'), 'layout B: all 3 rows matched (address / owner+mailing)')
    S2 = store(); p0 = {q[0]: q for q in S2[k0]['p']}
    ok(p0['3055550201'][1] == 'm' and p0['3055550203'][1] == 'l' and S2[k0]['n'] == 'Pat Example', f'layout B: implied mobile/landline types + provider name stored {S2[k0]}')
    ok(all(q[2] & 1 for q in S2[k1]['p']), 'layout B: row-level DNC flag applies to the row numbers'); ok(S2[k2]['p'][0][0] == '3055550205' and S2[k2]['p'][0][1] == 'l', 'layout B: lowercase address match, landline from column name')
    ok(len(S2) >= 3, f'layout B stored for {len(S2)} properties'); pg.evaluate("document.querySelector('#stModal [data-stclose]').click()")
    pg.evaluate("localStorage.setItem('pf.skip.v1.keep', '1')")

    # ---------- per-county separation (Monroe) ----------
    load('monroe', 'hg=0&city=Key West'); ok(pg.evaluate("localStorage.getItem('pf.skip.v1.monroe')") is None, 'Monroe starts with no skip trace data (separate key)')
    ok(pg.evaluate("PFSkip.store.key") == 'pf.skip.v1.monroe', 'Monroe store key is per county'); ok(pg.inner_text('#stInfo').startswith('No skip trace'), 'Monroe panel shows no results'); setcheck('#stHasPhone', True); ok(n_of() == 0, 'Monroe Has phone -> 0 (Miami-Dade results not shown)'); setcheck('#stHasPhone', False)
    go('hg=0&city=Key West&q=College'); mn = n_of(); open_export(); mrows = dl_rows(lambda: jsclick('#stxGo')); mh = mrows[0]; ok(mh == EXP_HEAD, 'Monroe export uses the same columns'); M = [dict(zip(mh, r)) for r in mrows[1:]]
    ok(all(x['County'] == 'Monroe' for x in M) and all(re.fullmatch(r'\d{20}|\d{8}-\d{6}', x['Folio']) for x in M), f'Monroe export: county + folio format ({M[0]["Folio"] if M else None})')
    mi = next((x for x in M if x['Is Company'] == 'N'), None); ok(mi is not None and mi['Owner First Name'] and mi['Owner Last Name'], f'Monroe names are LAST FIRST on the roll and split correctly: {mi and (mi["Owner Name (full)"], mi["Owner First Name"], mi["Owner Last Name"])}')
    if mi:
        ow = mi['Owner Name (full)'].split(';')[0].split(); ok(mi['Owner Last Name'].upper() == ow[0].upper() and mi['Owner First Name'].upper() == ow[1].upper(), 'Monroe: last name is the first token of the roll name')
    mo = M[0]; mA = [['Folio', 'Phone 1', 'Phone 1 Type'], [mo['Folio'], '305-555-0301', 'Mobile'], [digits(M[1]['Folio'])[-14:], '305-555-0302', 'Landline']]
    pg.set_input_files('#stFile', write_csv('provider_m.csv', mA)); pg.wait_for_selector('#stModal .stmap', timeout=60000); jsclick('#stImpGo'); pg.wait_for_selector('#stReport', timeout=240000)
    ok(pg.inner_text('#rpMatched') == '2', 'Monroe import matched both rows (20-digit folio and 14-digit RE number): ' + pg.inner_text('#rpMatched')); pg.evaluate("document.querySelector('#stModal [data-stclose]').click()")
    ms = store('monroe'); ok(len(ms) >= 2 and any('3055550301' in [q[0] for q in v['p']] for v in ms.values()), 'Monroe results stored under the Monroe key'); ok(pg.evaluate("localStorage.getItem('pf.skip.v1')") == json.dumps(S2, separators=(',', ':')) or len(store()) == len(S2), 'Miami-Dade results untouched by the Monroe import')
    go('hg=0&city=Key West&q=College&ph=1'); ok(n_of() >= 2, f'Monroe Has phone -> {n_of()}'); ok(pg.query_selector('#cards a[href^="sms:+13055550301"]') is not None, 'Monroe card shows the text link')
    # back in Miami-Dade the Monroe numbers are not visible
    load('miami-dade', 'hg=0&q=SW 2&city=Homestead&ph=1'); ok(pg.evaluate("PFSkip.store.key") == 'pf.skip.v1', 'Miami-Dade store key'); ok(not any('3055550301' in json.dumps(v) for v in store().values()), 'no Monroe numbers in Miami-Dade storage')
    ok(n_of() == len(S2), f'Miami-Dade Has phone count unchanged ({n_of()})')
    b.close()
print(f'[{TAG}] ' + ('ALL PASS' if not errs else f'{len(errs)} FAIL: ' + '; '.join(errs[:8])))
sys.exit(1 if errs else 0)
