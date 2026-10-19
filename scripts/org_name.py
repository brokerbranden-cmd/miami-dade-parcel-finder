"""Owner-name safety net, the Python twin of orgName() in app.js (keep the two in sync; tests/e2e_filter_audit.py checks the app side).
owner_kind.classify() runs it on every name it would call a 'person': churches and religious organizations (IGLESIA, FELLOWSHIP, CATHEDRAL,
CH OF GOD ...), clubs, posts, lodges, 'SALVATION ARMY', 'HABITAT FOR HUMANITY', legal suffixes in any spelling (L.L.C., L L C, INC.),
and Monroe/Broward names cut at 30 characters ('... ASSOCIATIO', '... HMOWNRS', '... INVEST LL') are organizations, not individuals."""
import re
HARD = re.compile(r'\b(?:' + '|'.join(["L ?L ?C", "L ?L ?L ?P", "L ?L ?P", "P ?L ?L ?C", "INC", "INCORPORATED", "CORP", "CORPORATION", "LTD", "LIMITED PARTNERSHIP", "MINISTRY", "MINISTRIES", "MINISTERIO\\w*", "MINISTERIAL", "CONGREGATION\\w*", "SYNAGOGUE", "MOSQUE", "TABERNACLE", "DIOCESE", "ARCHDIOCESE", "ARCHBISHOP", "CATHEDRAL", "EVANGELIC\\w*", "EVANGICAL", "ASSEMBLY OF", "ASAMBLEA", "IGLESIA (?:DE|DEL|BAUTISTA|EVANGELICA|CRISTIANA|CRISTO|NAZARENO|PENTECOSTAL|ADVENTISTA|METODISTA|CATOLICA|ALIANZA|C)", "PRIMERA IGLESIA", "EGLISE", "CHABAD", "LUBAVITCH", "ISLAMIC", "BUDDHIST", "JEHOVAH?S? WITNESSES", "KINGDOM HALL", "WATCHTOWER", "SEVENTH DAY", "ADVENTISTS?", "NAZARENE", "APOSTOLIC", "PENTECOSTAL", "BAPTIST", "METHODIST", "EPISCOPAL", "LUTHERAN", "PRESBYTERIAN", "CATHOLIC", "CATOLIC[OA]", "FELLOWSHIP", "OF GOD", "HOUSE OF GOD", "(?:BAPT|BAP|LUTH|EPIS|METH|MB|AME|CME|ADVENTIST|MIS|MISS|COGIC|BAPTIST) CH", "CHU? OF", "CHRUCH", "CHURCHES", "SALVATION ARMY", "HABITAT FOR? HUMANITY", "BOY SCOUTS?", "GIRL SCOUTS?", "SCOUTS OF", "YMCA", "YWCA", "MASONIC", "FRATERNAL", "ORDER OF", "AMERICAN LEGION", "POST NO \\d+", "VFW", "FOUNDATION", "FUNDACION", "ASSOCIATION\\w*", "ASSOCIATIO\\w*", "ASSN", "ASSCN", "SOCIETY", "SOCIE", "CLUB", "CHARITIES", "INSTITUTE", "MUSEUM", "CONDOMINI\\w*", "HOMEOWNERS?", "HMOWN\\w*", "HMEOWN\\w*", "HOMEOWN\\w*", "(?:COMM|PROP|PROPERTY|OWNERS|HOMEOWNERS|CONDO) ASS\\w*", "INVESTMEN\\w*", "INVESTM", "INVESTMNT", "INVESTMENT", "INVESTMENTS", "INVESTORS?", "ENTRPRISES", "APTS", "APARTMENTS", "HOSP", "HOSPITAL", "JEWISH (?:FED\\w*|CENTER|CTR|COMM\\w*|HOME|DAY|FAMILY)", "(?:CREDIT|LOCAL|TEACHERS) UNION", "UNION LO?CA?L", "(?:URBAN|CIVIC) LEAGUE", "LEAGUE OF", "(?:ZETA|ALUMNI|ALPHA|BETA|DELTA|KAPPA|OMEGA|SIGMA|THETA) CHAPTER", "TRUSTEES OF", "BANK OF", "(?:NATL|NATIONAL|SAVINGS|FED|STATE|TRUST|COMMUNITY|FIRST) BANK", "BANK (?:N ?A|FSB)", "NATL BNK", "FED SAV\\w*", "SAV & LOAN", "SAVINGS & LOAN"]) + r')\b')
CAREOF = re.compile('^\\s*(?:C\\s?/\\s?O\\b|%|ATTN\\b|ATTENTION\\b|CARE OF\\b)')
LEGAL_END = re.compile('\\s(?:LC|LL|LP|COMPANY)$')
LC_SP = re.compile('\\sL C$')
TRUNC = re.compile('\\s(?:BAPTIS|MINISTRI|CONDOMI|CONDOM|HOMEOWNE|ASSOCIA\\w*)$')
LEGAL = re.compile('\\b(?:L ?L ?C|INC|CORP|CORPORATION|LTD|L ?L ?P|P ?L ?L ?C)\\b')
CHURCH = re.compile('\\b(?:CHURC?H?|TEMPLE|PARISH|MISSION|MISION|CHAPEL|IGLESIA)\\b')
CHURCH_BACK = re.compile('\\b(?:OF|THE|GOD|DIOS|CHRIST\\w*|CRISTO|CRISTIANA|JESUS|HOLY|MEMORIAL|BAPT\\w*|AME|CME|ST|SAINT|SANTA|SAN|LIFE|VIDA|COMMUNITY|NEW|NUEVA|FIRST|BIBLE|GOSPEL|APOSTOLIC|MISSIONARY|ASSEMBLY|UNITED|ALLIANCE|LUTH\\w*|PRESBYTERIAN|EPISCOPAL|CATHOLIC|ADVENTIST|NAZARENE|FAITH|GRACE|VICTORY|TRINITY|CALVARY|HOPE|PRAISE|WORD|KINGDOM|ZION|BETHEL|SHILOH|MT|MOUNT|TEMPLE|TESTAMENT|INTERNATIONAL|FULL|REAL|RESCUE|DE|DEL|LA|EL|EVANGELICA|PENTECOSTAL|MISIONERA|HISPANA|SPANISH|HAITIAN|KOREAN|CHINESE|GREEK|BAPTIST|METHODIST|HWY|BAY|CHURCH|SHORE)\\b')
PERSON = re.compile('(?:&\\s?[WH]\\b|\\bH\\s?/\\s?E\\b|\\bH/E\\b|\\bLE\\b|\\bL E\\b|\\bETAL\\b|\\bETUX\\b|\\bJTRS\\b|\\bJR\\b|\\bSR\\b|\\bIII?\\b)')
IGLESIA_OK = re.compile('\\bIGLESIA (?:DE|DEL|LA|EL|BAUTISTA|EVANGELICA|CRISTIANA|CRISTO|PENTECOSTAL|ADVENTISTA|METODISTA|CATOLICA|NUEVA|HISPANA|MISIONERA|DIOS)\\b')

def org_name(raw):
    keep = []
    for l in str(raw or '').upper().split('|'):
        l = l.strip()
        if CAREOF.match(l): break
        if re.match(r'\s*REM\b', l): continue
        keep.append(l)
    for l0 in keep:
        l = re.sub(r'\s+', ' ', re.sub(r"[^A-Z0-9&/]+", ' ', re.sub(r"['\u2019.]", '', l0))).strip()
        if not l: continue
        w = l.split(' '); pers = bool(PERSON.search(l))
        if LEGAL.search(l): return True
        if not pers and HARD.search(l): return True
        if not pers and len(w) >= 2 and (LEGAL_END.search(l) or (LC_SP.search(l) and '&' not in l) or (len(l0) >= 28 and TRUNC.search(l))): return True
        m = CHURCH.search(l)
        if m and not pers and len(w) >= 2:
            rest = l.replace(m.group(0), ' ', 1)
            if CHURCH_BACK.search(rest) and (m.group(0) != 'IGLESIA' or IGLESIA_OK.search(l) or re.match(r'^IGLESIA \w+ \w+', l)): return True
    return False
