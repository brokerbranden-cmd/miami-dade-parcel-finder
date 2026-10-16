#!/usr/bin/env python3
"""City of Marathon Special Magistrate code-hearing agendas (public PDFs linked from ci.marathon.fl.us/codecompliance/page/code-compliance-hearing-N) -> $RAW/monroe/marathon_code.json
Each agenda lists Case No, Respondent(s), Location and 'Parcel ID: 00322100-000000' -> a code-violation signal per parcel (hearing date + violation text). Needs pdftotext."""
import os, re, json, subprocess, requests, time
RAW = os.path.join(os.environ.get('RAW', '/workspace/raw'), 'monroe'); D = os.path.join(RAW, 'marathon_agendas'); os.makedirs(D, exist_ok=True)
H = {'User-Agent': 'Mozilla/5.0 parcel-finder/1.0'}; B = 'https://www.ci.marathon.fl.us'
sm = requests.get(B + '/sitemap.xml', headers=H, timeout=60).text
pages = sorted(set(re.findall(r'<loc>(https://www\.ci\.marathon\.fl\.us/codecompliance/page/code-compliance-hearing(?:-\d+)?)</loc>', sm)))
print(len(pages), 'hearing pages'); rows = []
for u in pages:
    try:
        h = requests.get(u, headers=H, timeout=60).text
        pdfs = re.findall(r'href="([^"]+\.pdf)"', h)
        for p in pdfs:
            if 'agenda' not in p.lower(): continue
            fn = os.path.join(D, re.sub(r'\W', '_', p[-60:]) + '.pdf')
            if not os.path.exists(fn): open(fn, 'wb').write(requests.get(p if p.startswith('http') else B + p, headers=H, timeout=90).content); time.sleep(0.3)
            t = subprocess.run(['pdftotext', '-layout', fn, '-'], capture_output=True, text=True).stdout
            dm = re.search(r'(?:Monday|Tuesday|Wednesday|Thursday|Friday),\s+([A-Z][a-z]+ \d{1,2}, \d{4})', t); date = dm.group(1) if dm else ''
            for blk in re.split(r'\n\s*\d+\.\s+Case No:', t)[1:]:
                case = re.match(r'\s*([A-Z]-\d+-\d+)\s*(\([^)]*\))?', blk)
                pid = re.search(r'Parcel ID:\s*(\d{7,8}\s*-\s*\d{6})', blk)
                if not (case and pid): continue
                resp = re.search(r'Respondent\(s\):\s*(.+)', blk); loc = re.search(r'Location:\s*(.+?)\s*\(Parcel', blk, re.S); vio = re.search(r'Violation\(s\):\s*(.+?)(?:\n\s*Code Section|\n\s*\n)', blk, re.S)
                rows.append({'case': case.group(1), 'cat': (case.group(2) or '').strip('() '), 'date': date, 're': re.sub(r'\s', '', pid.group(1)), 'respondent': re.sub(r'\s+', ' ', resp.group(1)).strip() if resp else '',
                             'loc': re.sub(r'\s+', ' ', loc.group(1)).strip() if loc else '', 'violation': re.sub(r'\s+', ' ', vio.group(1)).strip()[:200] if vio else '', 'withdrawn': bool(re.search(r'Withdrawn|Dismissed', blk[:600]))})
    except Exception as e: print('ERR', u, str(e)[:80])
seen = {}
for r in rows: seen[(r['case'], r['re'])] = r
json.dump(list(seen.values()), open(os.path.join(RAW, 'marathon_code.json'), 'w')); print(len(seen), 'case rows')
