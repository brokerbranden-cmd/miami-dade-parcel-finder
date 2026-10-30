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


# ---- business-word layer: twin of ORG_BIZ_LIST ... orgBiz() in app.js (Oct 30, 2026; 'AMERICAN EXPRESS TRAVEL RELATE', 'SOUTHERN SHORES
# ACQUISITIONS L' and 'FLORIDA EASTERN ECCLESIASTICAL' were listed under Individuals). Same rules for every county; tests/unit_orgname.py
# runs both on every owner name of every county in counties.js and fails on any difference. See the comment block in app.js for the rules.
BIZ_LIST = [
    'ACQUISITIONS?', 'ACQUISTIONS?', 'ACQUISITON\\w*', 'ACQS', 'HOLDINGS', 'HLDGS', 'HLDG', 'HOLDCO', 'PROPCO', 'OPCO', 'ASSETS', 'SOLUTIONS',
    'CONSTRUCTION', 'CONSTRUCTORS', 'CONTRACTORS', 'CONTRACTING', 'DEVELOPERS?', 'DEVELOPMENTS?', 'DEVELOPMNT', 'DEVELOPEMENT', 'DEVLPMT',
    'PROPERTIES', 'PROPERTYS', 'PROPERTI', 'PROPS', 'PROPRTIES', 'RENTALS', 'EQUITIES', 'INVESTORS', 'INVESTMENTS?', 'INVEST', 'INVESTING', 'INVS',
    'LENDING', 'LENDERS', 'RESIDENTIAL', 'PORTFOLIO', 'PORTFOLIOS', 'OPPORTUNIT\\w*', 'SERVICES', 'SERVICING', 'SVCS', 'ENTERPRISES?', 'MANAGEMENT',
    'MANAGEMNT', 'MGMT', 'MNGMT', 'REALTY', 'REALTORS', 'REAL ESTATE', 'VENTURES?', 'PARTNERS', 'PARTNERSHIPS?', 'MORTGAGE', 'MTGE', 'FINANCIAL',
    'FUNDING', 'BUILDERS', 'INTERNATIONAL', 'INTERNATL', 'INTL', 'COMPANY', 'COMPANIES', 'ASSOCIATES', 'INDUSTRIES', 'TECHNOLOGIES', 'TECHNOLOGY',
    'LOGISTICS', 'CONSULTING', 'CONSULTANTS', 'TRADING', 'IMPORTS?', 'EXPORTS?', 'DISTRIBUTORS?', 'DISTRIBUTION', 'PRODUCTIONS', 'BANCORP',
    'BANCSHARES', 'SECURITIES', 'INSURANCE', 'ASSURANCE', 'LEASING', 'AUTOMOTIVE', 'RESTAURANTS?', 'HOTELS?', 'MOTELS?', 'RESORTS?', 'TOWNHOMES',
    'TOWNHOUSES', 'CONDOMINIUMS?', 'HOA', 'POA', 'CORPORATE', 'PLC', 'GMBH', 'SRL', 'LLLP', 'LTDA', 'S DE R ?L', 'SOCIEDAD', 'INVERSIONES',
    'INMOBILIARIA', 'PROPIEDADES', 'GRUPO', 'REIT', 'UNIVERSITY', 'ACADEMY', 'ECCLESIASTICAL', 'ECCLESIA', 'DIOCESAN', 'ARCHDIOCESAN', 'PRESBYTERY',
    'SYNOD', 'PARISHES', 'CONGREGATIONAL', 'EVANGELISTIC', 'BIBLE', 'GOSPEL', 'HOLINESS', 'ORATORY', 'MONASTERY', 'CONVENT', 'SHRINE', 'APARTMENT',
    'HOMEBUILDERS', 'HOMEBUILDER', 'STORAGE', 'WAREHOUSE', 'WAREHOUSES', 'PARKING', 'YACHT', 'PRTNSHP', 'PARTNSHP', 'PTNSHP', 'PRTSHP', 'LMTD',
    'LIMITADA', 'ANONIMA', 'TOWNHOME', 'TOWNHOUSES', 'AVIATION', 'AIRLINES?', 'AIRWAYS', 'RAILWAY', 'RAILROAD', 'TELEPHONE', 'TELECOM\\w*',
    'COMMUNICATIONS', 'UTILITIES', 'ELECTRIC', 'PETROLEUM', 'OIL', 'CHEVRON', 'EXXON', 'SHELL OIL', 'MOBIL', 'AMOCO', 'CITGO', 'SUNOCO',
    'WALGREEN\\w*', 'PUBLIX', 'WINN DIXIE', 'MCDONALDS', 'WALMART', 'WAL MART', 'TARGET CORP\\w*', 'HOME DEPOT', 'LOWES HOME', 'TRAVEL RELATE\\w*',
    'DST', 'PROPRIETORSHIP', 'PNTSHP', 'PTNRSHP', 'PRTNRSHP', 'PARTNRSHP', 'PRTNRS?', 'PTNRS?', 'PARTNR', 'LIMITED', 'LIMTED', 'RTLY', 'INVMTS?',
    'INVTS', 'CHAMBER OF', 'FRATERNITY', 'SORORITY', 'ORGANIZATION', 'CONFERENCE', 'FEDERATION', 'TRIBE OF', 'VOLUNTEERS?', 'AMBULANCE', 'RESCUE',
    'WASTEWATER', 'PLUMBING', 'CONSERVANCY', 'ENVIRONMENTAL', 'LANDSCAPING', 'LAUNDRY', 'REMODELING', 'ACCOUNTING', 'FUNERAL', 'CHEVROLET',
    'WORKSPACES', 'BUNGALOWS', 'MARKETING', 'SOROPTIMISTS?', 'RED CROSS', 'MOST REVEREND', 'SECRETARY OF', 'KINGDOM OF', 'REPUBLIC OF',
    'GOVERNMENT OF', 'CONSULATE', 'CONSULADO', 'EMBASSY', 'CITY HALL', 'FLOOD CON\\w*', 'HOME FOR THE',
    'HOUSE OF (?:THE|GOD|PRAYER|WORSHIP|FAITH|PRAISE|HOPE)', 'OWNERS', 'NEIGHBORHOOD', 'COMMERCE', 'VACATIONS?', 'TOURS', 'TROLLEY', 'SEAWALLS',
    'BOY SCOU\\w*', 'SCOUTS', 'COUNCIL OF', 'COUNCIL ON', 'PRESIDENTS COUNCIL', 'METHODI\\w*', 'AFFORDABLE', 'RELATED SERVICES', 'D ?B ?A', 'TR CO',
    'TRUST CO', 'TRUST COMPANY', 'CREDIT UNION',]
BIZ_PFX = [
    'ACQUISITION', 'HOLDINGS', 'PROPERTIES', 'MANAGEMENT', 'DEVELOPMENT', 'INVESTMENTS', 'ENTERPRISES', 'INTERNATIONAL', 'FOUNDATION', 'CORPORATION',
    'PARTNERSHIP', 'PARTNERS', 'COMPANY', 'SERVICES', 'REALTY', 'VENTURES', 'PORTFOLIO', 'OPPORTUNITY', 'SOLUTIONS', 'CONSTRUCTION', 'DEVELOPERS',
    'INCORPORATED', 'ASSOCIATES', 'ECCLESIASTICAL', 'CONDOMINIUM', 'APARTMENTS', 'RENTALS', 'EQUITIES', 'INVESTORS', 'LENDING', 'MORTGAGE',
    'FINANCIAL', 'INDUSTRIES', 'TECHNOLOGIES', 'HOSPITALITY', 'VACATION', 'ENVIRONMENTAL', 'PROFESSIONAL', 'COMMERCIAL', 'INDUSTRIAL', 'RECREATION',
    'MAINTENANCE', 'ASSOCIATION', 'CORPORATION', 'TOWNHOMES', 'TOWNHOUSES', 'NEIGHBORHOOD', 'HOMEOWNERS', 'COMMUNITY', 'EDUCATION', 'HEALTHCARE',
    'REHABILITATION', 'CONSERVATION', 'ENGINEERING', 'AUTOMOTIVE', 'LANDSCAPING', 'VOLUNTEER', 'RESCUE', 'EVANGELISTIC', 'INTERDENOMINATIONAL',
    'CONSTRUCTORS', 'DISTRIBUTORS',]
SOFT_B_LIST = [
    'TRAVEL', 'EXPRESS', 'CAPITAL', 'EQUITY', 'HOMES', 'GROUP', 'FUND', 'FUNDS', 'BANK', 'BK', 'BANKING', 'SERVICE', 'SVC', 'SVS', 'SERV',
    'PROPERTY', 'PROP', 'ASSET', 'REO', 'ACQ', 'HOLDING', 'CO', 'CORPS', 'ESTATES', 'TOWERS', 'CENTER', 'CENTRE', 'CTR', 'DISTRICT', 'AUTHORITY',
    'COUNTY', 'SCHOOL', 'MEDICAL', 'CLINIC', 'MOTORS', 'AUTO', 'FARMS', 'RANCH', 'NURSERY', 'GROVES', 'MARKET', 'LANDS', 'HOUSING', 'DEVELOPMENT',
    'INVESTMENT', 'INV', 'MGT', 'RENTAL', 'FINANCE', 'ESCROW', 'LOANS', 'SAVINGS', 'VENTURE', 'TRADERS', 'SUPPLY', 'SUPPLIES', 'PRODUCTS', 'SYSTEMS',
    'IMPORT', 'EXPORT', 'ACRES', 'GARDENS', 'POINTE', 'OFFICE', 'OFFICES', 'PROFESSIONAL', 'DENTAL', 'HEALTH', 'HEALTHCARE', 'COMMUNITY',
    'COMMUNITIES', 'PROJECTS', 'CONSOLIDATED', 'TOWNHOUSE', 'SHORES', 'SUITES', 'RESORT', 'CLUB', 'CHAPEL', 'MISSION', 'ASSEMBLY', 'BUSINESS',
    'COMMERCIAL', 'INDUSTRIAL', 'RETAIL', 'SHOPPING', 'MULTIFAMILY', 'LOGISTIC', 'MAINTENANCE', 'MAINT', 'RECREATION', 'RECREATIONAL', 'EDUCATION',
    'EDUCATIONAL', 'TECH', 'MEDIA', 'ENGINEERING', 'PHARMACY', 'PHARMACEUTICAL', 'HOSPITALITY', 'REHABILITATION', 'ASSISTED', 'MEMORIAL', 'PRAYER',
    'WORSHIP', 'DELIVERANCE', 'OWNER', 'LOFTS', 'MANORS', 'COURTS', 'PRESERVE', 'PRESERV', 'PROJ', 'MOBILE', 'UNITS',]
SOFT_2 = set([
    'ACQ', 'ASSET', 'BUSINESS', 'CAPITAL', 'CENTER', 'CENTRE', 'CLINIC', 'COMMERCIAL', 'COMMUNITIES', 'COMMUNITY', 'CONSOLIDATED', 'CTR',
    'ENGINEERING', 'EQUITY', 'ESCROW', 'ESTATES', 'GARDENS', 'GROUP', 'HEALTHCARE', 'HOLDING', 'HOSPITALITY', 'INDUSTRIAL', 'LOANS', 'MAINTENANCE',
    'MOTORS', 'MULTIFAMILY', 'NURSERY', 'PHARMACY', 'POINTE', 'PRODUCTS', 'PROFESSIONAL', 'PROP', 'PROPERTY', 'RESORT', 'SAVINGS', 'SHOPPING',
    'SUITES', 'SUPPLIES', 'SUPPLY', 'SYSTEMS', 'TOWERS', 'TOWNHOUSE',])
SOFT_N_LIST = [
    'TEMPLE', 'CHURCH', 'PARISH', 'VILLA', 'VILLAS', 'PARK', 'SENIOR', 'ROYAL', 'HOUSE', 'BEACH', 'LOAN', 'PRIME', 'ISLAND', 'ISLANDS', 'HARBOR',
    'HARBOUR', 'LODGE', 'INN', 'CARE', 'UNITED', 'ALLIED', 'GENERAL', 'UNIVERSAL', 'PREMIER', 'ELITE', 'IMPERIAL', 'CHRISTIAN', 'DEV', 'PARTNER',
    'TRADE', 'GROVE', 'FARM', 'TOWER', 'MANAGE', 'LIVING', 'MARINA', 'MARINE', 'ABBEY', 'TITLE', 'LAND', 'HOME', 'STAR', 'SUN', 'GOLD', 'GOLDEN',
    'SILVER', 'DIAMOND', 'CROWN', 'EAGLE', 'PALM', 'PALMS', 'LAKE', 'LAKES', 'OAK', 'OAKS', 'PINE', 'RIVER', 'CHAPTER', 'COUNCIL', 'PLAZA', 'REAL',
    'SQUARE', 'PLACE', 'TERRACE', 'PATIO', 'NORTH', 'SOUTH', 'EAST', 'WEST',]
GEO_LIST = [
    'FLORIDA', 'FLA', 'SOUTHERN', 'NORTHERN', 'EASTERN', 'WESTERN', 'SOUTHEAST', 'SOUTHEASTERN', 'SOUTHWEST', 'SOUTHWESTERN', 'NORTHEAST',
    'NORTHEASTERN', 'NORTHWEST', 'NORTHWESTERN', 'MIDWEST', 'CENTRAL', 'ATLANTIC', 'PACIFIC', 'COASTAL', 'GULF', 'CARIBBEAN', 'SUNCOAST', 'AMERICAN',
    'AMERICAS', 'USA', 'U S A', 'NATIONAL', 'NATL', 'FEDERAL', 'INTERSTATE', 'GLOBAL', 'WORLD', 'WORLDWIDE', 'CONTINENTAL', 'METRO', 'METROPOLITAN',
    'MIAMI', 'DADE', 'BROWARD', 'BISCAYNE', 'EVERGLADES', 'TROPICAL', 'TROPICS', 'LATIN', 'EURO', 'EUROPEAN', 'TRANSATLANTIC', 'OCEAN', 'OCEANFRONT',
    'BAYFRONT', 'DOWNTOWN', 'KEYS', 'KEY WEST', 'LAUDERDALE', 'HIALEAH', 'POMPANO', 'DEERFIELD', 'PLANTATION', 'SAWGRASS', 'INTRACOASTAL', 'GREATER',]
GIVEN_SKIP = set([
    'ALL', 'AND', 'AT', 'BAY', 'BUILDING', 'BY', 'CASA', 'CITY', 'DA', 'DE', 'DEL', 'DI', 'DOS', 'EL', 'EST', 'ESTATE', 'ETAL', 'FAMILY', 'FIVE',
    'FOR', 'FOUR', 'II', 'III', 'IN', 'IV', 'JR', 'JTRS', 'LA', 'LAS', 'LE', 'LIFE', 'LOS', 'MI', 'MY', 'NEW', 'OF', 'OLD', 'ON', 'ONE', 'OUR',
    'REM', 'SIX', 'SR', 'SU', 'SUNRISE', 'SUNSET', 'THE', 'THREE', 'TO', 'TOWN', 'TR', 'TRS', 'TWO', 'VAN', 'VILLAGE', 'VON', 'WATER',])
NA_END = re.compile('\\b(?:BANK|BK|TRUST|ASSOCIATION|ASSN) N ?A$')
AMP = re.compile('&\\s?(?:SONS|BROS|BROTHERS|CO|COMPANY|ASSOCIATES|ASSOC|ASSOCS|PARTNERS|PARTNER)\\b')
GLUED = re.compile('[A-Z0-9]{2}L{2,3}C$|\\bL L C$|\\bI N C$|\\bLCC$|\\bCLLC$|\\bLLLC\\b')
FOREIGN_END = re.compile(' (?:SRO|S R O|S L U|SLU|B V|BV|N V|NV|LTDA|SARL|S A R L|S DE R ?L(?: DE C ?V)?|S A DE C ?V|SA DE CV|PTY LTD|BHD|KFT|EIRL)$')
FOREIGN_WEAK = re.compile(' (?:AG|SAS|S A S|SPA|S P A|S L|SL)$')
TRUSTISH = re.compile('\\b(?:TR|TRS|TRU|TRUS|TRUST|TRUSTS|TRUSTE|TRUSTEE|TRUSTEES|REV|IRREV|IRR|REVOC\\w*|IRREVOC\\w*|IRA|SEPARATE|SEP|QPRT|GRAT|LIV|LIVING TRU?S?T?|LAND T|LD T|LND T|PROP T|LANDTRUST\\w*)$|\\b(?:TRUST|TRUSTEE|TRUSTEES|REVOCABLE|IRREVOCABLE|REV TR|LIVING TRUST|SEPARATE PROP\\w*|SEP PROP\\w*|LAND TRUST|LANDTRUST|IRA|QPRT|GRAT|REV INTER\\w*|INTER VIVOS)\\b')
STREET = re.compile('\\b(?:ST|STREET|AVE|AVENUE|AVENU|RD|ROAD|BLVD|BOULEVARD|DR|DRIVE|CT|COURT|TER|TERR|TERRACE|PL|PLACE|WAY|LN|LANE|HWY|HIGHWAY|CIR|CIRCLE|TRL|TRAIL|PKWY|PARKWAY|NW|NE|SW|SE|UNIT|APT|STE|SUITE|BLDG)\\b')
BIZ = re.compile(r'\b(?:' + '|'.join(BIZ_LIST) + r')\b')
_rx = lambda a: re.compile(r'\b(?:' + '|'.join(a) + r')\b')
SOFT_B, SOFT_N, GEO = _rx(SOFT_B_LIST), _rx(SOFT_N_LIST), _rx(GEO_LIST)
SIG_WORDS = set(' '.join(SOFT_B_LIST + SOFT_N_LIST + GEO_LIST).split(' '))

def _norm(l0):
    return re.sub(r'\s+', ' ', re.sub(r"[^A-Z0-9&/]+", ' ', re.sub(r"['\u2019.]", '', l0))).strip()

def org_given(names, flags=None):
    """Given names, data-driven per pack (twin of orgGiven): words in the first or second place of 2-4 word owner lines of rows not flagged
    company / government (flags & (8|32)), with no business word and no digit, seen >= lim times."""
    c = {}
    for r, raw in enumerate(names):
        if not raw or (flags is not None and flags[r] & (8 | 32)): continue
        for l0 in str(raw).upper().split('|'):
            if CAREOF.match(l0): break
            l = _norm(l0)
            if not l or re.search(r'\d', l): continue
            t = l.split(' ')
            if len(t) < 2 or len(t) > 4: continue
            if LEGAL.search(l) or BIZ.search(l) or AMP.search(l): continue
            for x in t[:2]:
                if len(x) > 1 and x != '&': c[x] = c.get(x, 0) + 1
    lim = max(8, min(15, int(len(names) / 20000 + 0.5)))
    return {w for w, k in c.items() if k >= lim and w not in SIG_WORDS and w not in GIVEN_SKIP}

def org_biz(l, l0, w, pers, given, first, after_rem):
    """Twin of orgBiz(). given=None (a build that has no per-pack given-name set) runs only the hard rules; the app adds the soft ones."""
    if pers or after_rem: return ''
    if GLUED.search(l) and not TRUSTISH.search(l): return 'llc'
    if len(w) < 2: return ''
    if first and re.match(r'\d', w[0]) and STREET.search(l): return 'addr'
    if TRUSTISH.search(l): return ''
    if BIZ.search(l): return 'biz'
    if FOREIGN_END.search(l): return 'foreign'
    if NA_END.search(l): return 'na'
    if AMP.search(l): return 'amp'
    last = w[-1]; g = given
    def nb(i): return [y for y in (w[i - 1] if i > 0 else None, w[i + 1] if i + 1 < len(w) else None) if y]
    couple = len(w) <= 6 and any((x == '&' and any(y not in SIG_WORDS for y in nb(i))) or (x == 'AND' and g is not None and any(y in g for y in nb(i))) for i, x in enumerate(w))
    if couple: return ''
    if len(l0) >= 28 and len(last) >= 5 and not (g and last in g) and any(x.startswith(last) for x in BIZ_PFX): return 'cut'
    if not g or len(g) < 200: return ''   # too few given names to tell people apart (tiny pack / no names): hard rules only
    weak = bool(FOREIGN_WEAK.search(l))
    personish = any(i > 0 and len(x) == 1 and 'A' <= x <= 'Z' and len(w) <= 5 and not (weak and i >= len(w) - 2) for i, x in enumerate(w)) \
        or any(x in g and x not in SIG_WORDS for x in w)
    if personish: return ''
    if weak: return 'foreign'
    sb, sn, geo = SOFT_B.findall(l), SOFT_N.findall(l), GEO.findall(l)
    if not sb and not geo: return ''
    if len(set(sb + sn + geo)) >= 2: return 'two'
    if sb and (len(w) >= 3 or sb[0] in SOFT_2): return 'soft'
    return 'geo' if len(w) >= 3 and w[0] in GEO_LIST else ''

def org_name(raw, given=None):
    """given: org_given() of the pack the name comes from (enables the soft business-word rules, as the app does); None: hard rules only."""
    keep = []; rem = False   # lines after a 'REM ...' line name the remaindermen, not the owner
    for l in str(raw or '').upper().split('|'):
        l = l.strip()
        if CAREOF.match(l): break
        if re.match(r'\s*REM\b', l): rem = True; continue
        keep.append((l, rem))
    for k, (l0, after_rem) in enumerate(keep):
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
        if org_biz(l, l0, w, pers, given, k == 0, after_rem): return True
    return False
