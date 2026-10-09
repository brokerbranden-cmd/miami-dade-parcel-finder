"""Owner-type classifier shared by build_data.py (owner filters / flags) and owners_lib.py (portfolio institution flags).

classify(name, given) -> (kind, sub)
  kind: 'person' | 'corp' | 'trust' | 'govt'          ('corp' = every non-government organization, so the app's
                                                         "LLCs & companies" filter hides all of them)
  sub : ''        person / trust
        'govt'    county, city, state, federal, special district, authority, board, agency, school board ...
        'bank'    bank / lender / mortgage / servicer / GSE
        'utility' electric, gas, water, telephone, cable, railroad
        'assoc'   condo / homeowners / property-owners association
        'inst'    church, school, university, hospital, foundation, non-profit
        'biz'     any other company (LLC, INC, CORP, CO, LP, PA, holdings, properties, management ...)

Matching is word-based on a normalized name (punctuation -> spaces, '&' kept as a token). Words that are also common surnames
or given names (BANK, POWER, LIGHT, GAS, WATER, CAPITAL, CHURCH, TEMPLE, CO, PA, ...) only count when something else backs them up:
the name has other organization words, or it does NOT look like "GIVEN-NAME [INITIAL] SURNAME" (first word is not a common given name).
`given` = set of common first words, from build_given(); pass None to disable that check.
"""
import re, collections

def norm(s):
    s = str(s or '').upper().replace('&', ' & ')
    s = re.sub(r"\bL\.?\s?L\.?\s?C\.?\b", 'LLC', s)
    s = re.sub(r"\bP\.\s?A\.", 'PA', s); s = re.sub(r"\bN\.\s?A\.", 'N A', s)
    s = s.replace("'", '')
    s = re.sub(r'\bCO[ -](TRS?|TRUSTEES?)\b', r'\1', s)
    s = re.sub(r'[^A-Z0-9&]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()

R = lambda p: re.compile(r'\b(?:' + p + r')\b')

# ---------- government ----------
MUNI = (r"MIAMI SHORES|BAL HARBOUR|BAY HARBOR ISLANDS?|SURFSIDE|KEY BISCAYNE|PINECREST|PALMETTO BAY|CUTLER BAY|EL PORTAL|BISCAYNE PARK|VIRGINIA GARDENS|"
        r"MIAMI SPRINGS|MEDLEY|ISLANDIA|INDIAN CREEK|GOLDEN BEACH|NORTH BAY|SWEETWATER|WEST MIAMI|SOUTH MIAMI|NORTH MIAMI BEACH|NORTH MIAMI|HIALEAH GARDENS|HIALEAH|"
        r"MIAMI GARDENS|MIAMI LAKES|MIAMI BEACH|DORAL|AVENTURA|SUNNY ISLES BEACH|HOMESTEAD|FLORIDA CITY|OPA LOCKA|CORAL GABLES|MIAMI|MIAMI DADE|DADE|FORT LAUDERDALE|HOLLYWOOD")
GOV_HARD = R(r"MIAMI DADE COUNT[YI]|MIAMI DADE CNTY|DADE COUNTY|DADE CNTY|COUNTY OF|COUNTY COMMISSIONERS?|BOARD OF COUNTY|[A-Z]+ COUNTY (?:SCHOOL|PUBLIC|HOUSING|HOSPITAL|PARK|TRANSIT|COMMISSION|WATER)|"
             r"CITY OF|TOWN OF|VILLAGE OF|STATE OF (?:FL|FLA|FLORIDA)|STATE OF|FLORIDA STATE|FLORIDA DEPT|FLORIDA DEPARTMENT|STATE ROAD DEPT|STATE BOARD|BOARD OF TRUSTEES|TRUSTEES OF (?:THE )?INTERNAL IMPROVEMENT|INTERNAL IMPROVEMENT|TIITF|"
             r"SCHOOL BOARD|SCHOOL DISTRICT|BOARD OF PUBLIC INSTRUCTION|PUBLIC SCHOOLS|U S GOVT?|US GOVT|U S GOVERNMENT|FEDERAL GOVT|UNITED STATES OF AMERICA|"
             r"U S ARMY|US ARMY|ARMY CORPS|CORPS OF ENG(?:INEERS?)?|U S NAVY|US NAVY|AIR FORCE|COAST GUARD|U S POSTAL|US POSTAL|POSTAL SERVICE|NATIONAL PARK SERVICE|NATL PARK|NATIONAL PARK|NATL PROJ|NATIONAL PRESERVE|NATL PRESERVE|"
             r"SECRETARY OF (?:HOUSING|HUD|VETERANS|THE (?:ARMY|NAVY|INTERIOR))|SEC OF HUD|US SEC HUD|HOUSING AND URBAN|VETERANS ADMIN(?:ISTRATION)?|"
             r"DEPT OF|DEPARTMENT OF|DIVISION OF|SFWMD|SO(?:UTH)? FL(?:ORID)?A? WATER|WATER MANAGEMENT|WATER MGT|WATER MGMT|WATER MNGM|WATER MANG|WATER MANGM|"
             r"EXPRESSWAY AUTHORITY|TRANSPORTATION AUTHORITY|HOUSING AUTHORITY|HOUSING AUTH|PORT AUTHORITY|PORT OF MIAMI|PUBLIC HEALTH TRUST|JACKSON MEMORIAL|"
             r"MIAMI DADE CO|DADE CO|MIAMI DADE COLLEGE|FLOOD CONTROL|NATL PRESERVE|EVERGLADES NATIONAL|EVERGLADES NATL|SOUTHEAST OVERTOWN PARK|(?:SOUTH|SO|S) FL(?:A|ORIDA)? (?:WATER|MNGM|MGMT|MGNT|MANAG\w*)|FLORIDA INTERNATIONAL UNIV\w*|FLA INTERNATIONAL UNIV\w*|FLORIDA ATLANTIC UNIV\w*|UNIVERSITY OF FLORIDA|UNIV OF FLORIDA|FLORIDA A & M UNIV\w*|WATER MAN\w*|WATER MN\w*|WATER MG\w*|"
             r"COMMUNITY REDEVELOPMENT|REDEVELOPMENT AGENCY|CRA|FISH AND WILDLIFE|FISH & WILDLIFE|GAME AND FRESH WATER|WATER AND SEWER|WASD|METROPOLITAN DADE|METRO DADE")
GOV_AMBIG = R(r"CDD|COMMUNITY DEVELOPMENT|COMM DEVELOPMENT|COMMUNITY DEV|COMM DEV|COMMUNITY DEV DIST|CMM DEV|USA|U S A|UNITED STATES|GSA|HUD|DEPT|CRA|MDC|M D C|AVIATION|SEAPORT|D O T|FDOT|MDX")
GOV_SOFT = R(r"DISTRICT|DIST|AUTHORITY|AUTH|BOARD OF|BD OF|COMMISSION|COMMISSIONERS|AGENCY|DEPARTMENT|COUNTY|TRANSIT|EXPRESSWAY|SEAPORT|AIRPORT|PUBLIC SCHOOL|SCHOOL BOARD|TRUSTEES OF INTERNAL")
GOV_MUNI = re.compile(r"^(?:THE )?(?:(?:CITY|TOWN|VILLAGE) )?(?:" + MUNI + r")(?: (?:CITY|TOWN|VILLAGE|CRA|BOARD|HOUSING|UTILITIES|DOWNTOWN DEV AUTH))?$")
GOV_MUNI_TAIL = re.compile(r"^(?:" + MUNI + r") (?:CITY|TOWN|VILLAGE)$")

LEGAL = R(r"LLC|LC|LLP|LLLP|LP|L P|LTD|INC|INCORPORATED|CORP|CORPORATION|COMPANY|PLLC|PA|P A")
# ---------- organizations ----------
STRONG = R(r"LLC|LC|LLP|LLLP|LP|L P|LTD|LIMITED|PLLC|PLC|INC|INCORPORATED|CORP|CORPORATION|COMPANY|COMPANIES|ASSOCIATES|PARTNERSHIP|JOINT VENTURE|REIT|NV|BV|GMBH|SRL|S DE RL|SAS|SARL|LLP|FSB|FSA|"
           r"BANK OF|BANCORP|MORTGAGE|MTG|MTGE|LENDING|FINANCIAL|FINANCE|FUNDING|SAVINGS|CREDIT UNION|SERVICING|FANNIE MAE|FREDDIE MAC|FNMA|FHLMC|FEDERAL NATIONAL|FEDERAL HOME LOAN|NATIONAL ASSOCIATION|NATIONAL ASSN|NATL ASSN|NATL ASSOC|"
           r"ASSN|ASSOC|ASSOCIATION|ASSOCIATIONS|CONDOMINIUM|CONDO|HOMEOWNERS|HOA|POA|COOPERATIVE|"
           r"FPL|CSX|RAILWAY|RAILROAD|RAIL ROAD|TELEPHONE|TELEPHONES|COMMUNICATIONS|TELECOM|TELECOMMUNICATIONS|BELLSOUTH|AT&T|VERIZON|COMCAST|AMTRAK|FLORIDA EAST COAST|SEABOARD COASTLINE|PIPELINE|UTILITIES|UTILITY|"
           r"MINISTRIES|MINISTRY|DIOCESE|ARCHDIOCESE|ARCHBISHOP|CONGREGATION|MOSQUE|SYNAGOGUE|TABERNACLE|FOUNDATION|UNIVERSITY|HOSPITAL|SCHOOL|SCHOOLS|ACADEMY|CEMETERY|"
           r"HOLDING|HOLDINGS|ENTERPRISE|ENTERPRISES|INVESTMENT|INVESTMENTS|INVESTORS|INVESTMENT|PROPERTIES|DEVELOPMENT|DEVELOPMENTS|DEVELOPERS|REALTY|REAL ESTATE|MANAGEMENT|MGMT|MGT|MNGM|MNGMT|MANG|MANGM|MANAGE|SERVICES|SERVICE|SVC|SVCS|"
           r"ANNUAL CONFERENCE|INSURANCE|ASSURANCE|BAPTIST|METHODIST|CATHOLIC|PRESBYTERIAN|LUTHERAN|EPISCOPAL|PENTECOSTAL|MISSIONARY|ORTHODOX|ASSEMBLY OF GOD|COLLEGE|COUNTRY CLUB|YACHT CLUB|GOLF CLUB|PROPERTY|PORTFOLIO|BORROWER|OWNER|"
           r"INTERNATIONAL|INTL|VENTURES?|EQUITY|EQUITIES|INDUSTRIES|RESIDENTIAL|PARTNERS|PARTNERSHIPS|PARTNERS|AUTO PARTS|CONSTRUCTION|BUILDERS|CONTRACTORS|COMPANYS|COMPANY S|CORPS|FUND|FUNDS|TRADING|DISTRIBUTORS|SOLUTIONS|CONSULTING|HOMES|REALTORS|BROKERS|MOTORS")
# strong words that are also plausible surnames / given names: need backing
WEAKSET = {'CORPS', 'MANG', 'MANAGE', 'SAS', 'HOMES', 'FUND', 'FUNDS', 'SERVICE', 'MOTORS', 'FINANCE', 'EQUITY', 'ASSOCIATES', 'INTL', 'UTILITY', 'SCHOOL', 'CONDO', 'ACADEMY', 'MGT', 'COOPERATIVE'}
# words that mean organization only when backed up (surnames / ordinary words)
WEAK = R(r"CO|PA|P A|PC|P C|NA|N A|SA|S A|BANK|BK|BANKING|POWER|LIGHT|GAS|WATER|ELECTRIC|ELEC|TELEPHONE|CABLE|RAILWAY|CAPITAL|CHURCH|TEMPLE|CHAPEL|MISSION|LODGE|BISHOP|SOCIETY|CLUB|PLAZA|CENTER|CENTRE|TOWERS?|MARKET|PARK|PARKS|GROUP|HOTEL|MOTEL|RESTAURANT|STORAGE|PARKING|MARINA|AUTO|COMMUNITY|TRUST CO|TR CO|ENTERTAINMENT|SYSTEMS|TECHNOLOGIES|PRODUCTS|SUPPLY|RENTALS|LEASING|IMPORTS|EXPORTS|APARTMENTS|HOUSING|FARM|FARMS|RANCH|NURSERY|GROVES?|SEWER|WASTE|WIRELESS|RR|RY|RY CO|CLINIC|MEDICAL|SCHOOL|SCHOOLS")
SUB_BANK = R(r"BANK|BANCORP|BANKING|BK|MORTGAGE|MTG|MTGE|LENDING|LOAN|LOANS|FINANCIAL|FINANCE|FUNDING|SAVINGS|CREDIT UNION|SERVICING|FANNIE MAE|FREDDIE MAC|FNMA|FHLMC|FEDERAL NATIONAL|FEDERAL HOME LOAN|NATIONAL ASSOCIATION|NATIONAL ASSN|NATL ASSN|NATL ASSOC|N A|"
             r"TRUST COMPANY|TRUST CO|TR CO|DEUTSCHE|WILMINGTON|WELLS FARGO|JPMORGAN|JP MORGAN|CITIBANK|CITIMORTGAGE|OCWEN|NATIONSTAR|MR COOPER|PNC|SUNTRUST|TRUIST|BANKUNITED|FREEDOM MORTGAGE|NEWREZ|SECURITIZATION|BANK OF|U S BANK|US BANK|HSBC|SANTANDER|BBVA|SECURITY NATIONAL|SERVICER")
SUB_UTIL = R(r"POWER|LIGHT|FPL|ELECTRIC|ELEC|GAS|WATER|SEWER|TELEPHONE|TELEPHONES|COMMUNICATIONS|TELECOM|TELECOMMUNICATIONS|BELLSOUTH|AT&T|VERIZON|COMCAST|CABLE|WIRELESS|RAILWAY|RAILROAD|RAIL ROAD|RR|RY|CSX|AMTRAK|FLORIDA EAST COAST|F E C|FEC|SEABOARD COASTLINE|PIPELINE|UTILITIES|UTILITY|WASTE|TECO|FLORIDA CITY GAS")
SUB_ASSOC = R(r"ASSN|ASSOC|ASSOCIATION|ASSOCIATIONS|CONDOMINIUM|CONDO|HOMEOWNERS|HOMEOWNER|HOA|POA|COOPERATIVE|COOP|PROPERTY OWNERS|OWNERS ASSN|COMMUNITY|MASTER ASSN|CLUB|RESIDENTS")
SUB_INST = R(r"CHURCH|CHURCHES|MINISTRIES|MINISTRY|MINISTR|DIOCESE|ARCHDIOCESE|ARCHBISHOP|BISHOP|CONGREGATION|TEMPLE|MOSQUE|SYNAGOGUE|TABERNACLE|CHAPEL|MISSION|LODGE|FOUNDATION|SOCIETY|UNIVERSITY|COLLEGE|SCHOOL|SCHOOLS|ACADEMY|HOSPITAL|CLINIC|CEMETERY|CHARITIES|YMCA|YWCA|MASONIC|VETERANS|"
             r"JEHOVAHS? WITNESSES|KINGDOM HALL|BAPTIST|METHODIST|CATHOLIC|PRESBYTERIAN|LUTHERAN|EPISCOPAL|PENTECOSTAL|ASSEMBLY OF GOD|ORTHODOX|HABITAT FOR HUMANITY|BOYS AND GIRLS|BOY SCOUTS|SALVATION ARMY|NON PROFIT|NONPROFIT")
TRUST = R(r"TRUST|TR|TRS|TRSTEE|TRUSTEE|TRUSTEES|REVOCABLE|REV TR|LIV TR|LIVING TR|LAND TR|IRREVOCABLE|REV LIV")
# first words that look like organizations rather than people
ORG_FIRST = {'FIRST', 'UNITED', 'AMERICAN', 'NATIONAL', 'NATL', 'FLORIDA', 'MIAMI', 'DADE', 'SOUTH', 'NORTH', 'EAST', 'WEST', 'CENTRAL', 'ATLANTIC', 'PACIFIC', 'SUNSHINE', 'COASTAL', 'GOLDEN', 'ROYAL', 'GRAND', 'GLOBAL',
             'INTERNATIONAL', 'PUBLIC', 'THE', 'NEW', 'OLD', 'CITY', 'COUNTY', 'STATE', 'FEDERAL', 'METRO', 'METROPOLITAN', 'GREATER', 'UNIVERSAL', 'PREMIER', 'PRIME', 'ADVANCE', 'ALLIED', 'GENERAL', 'ST', 'SAINT', 'HOLY', 'FAITH', 'CHRIST', 'GOD', 'MT'}

def tokens(s): return s.split()

def build_given(names, min_count=12):
    """Common given names in the data: words that sit next to '&' in couples' names ('JOSE & MARIA RODRIGUEZ') or start
    '... LE' / '... JR' / '&W' names, in names with no organization word. Used only to tell 'MARIA POWER' (person) from 'OCEAN BANK'."""
    c = collections.Counter()
    for s in names:
        t = norm(s).split()
        if len(t) < 2 or STRONG.search(' '.join(t)) or GOV_HARD.search(' '.join(t)): continue
        for i, w in enumerate(t):
            if w == '&':
                if i > 0: c[t[i - 1]] += 1
                if i + 1 < len(t): c[t[i + 1]] += 1
        if t[-1] in ('LE', 'JR', 'SR', 'W', 'H', 'HW', 'ETAL', 'ETUX'): c[t[0]] += 1
    bad = set(ORG_FIRST) | {'&', 'W', 'H', 'LE', 'JR', 'SR', 'C', 'O', 'A', 'B', 'E', 'D', 'F', 'G', 'J', 'K', 'L', 'M', 'N', 'P', 'R', 'S', 'T', 'V'}
    return {w for w, k in c.items() if k >= min_count and w not in bad and len(w) > 1}

def looks_like_person(t, given):
    """2-4 words, first word a common given name (optionally a middle initial) -> 'JOSE A RODRIGUEZ', 'MARIA BANK'."""
    if given is None or not (2 <= len(t) <= 4): return False
    return t[0] in given

def person_marker(t):
    return bool(set(t) & {'LE', 'JR', 'SR', 'II', 'III', 'ETAL', 'ETUX', 'H', 'W', 'HW', 'JTRS', 'MARRIED', 'SINGLE', 'UNMARRIED'}) or '&' in t and len(t) <= 5 and not (set(t) & {'CO', 'SONS', 'ASSOCIATES', 'PARTNERS'})

def classify_one(raw, given=None):
    s = norm(raw)
    if not s: return ('person', '')
    t = s.split(); n = len(t)
    strong = STRONG.search(s)
    # strong markers that are surname-like need backing
    strong_hits = [m.group(0) for m in STRONG.finditer(s)]
    strong_real = [w for w in strong_hits if w not in WEAKSET]
    legal = bool(LEGAL.search(s)) or bool(re.search(r'\b(?:CREDIT UNION|CO|BANK|ASSN|ASSOC|ASSOCIATION|HOA|CHURCH)\b', s))
    if not legal and (re.match(r'(?:THE )?(?:USA|U S A|UNITED STATES)\b', s) or re.match(r'MIAMI DADE\b', s)): return ('govt', 'govt')
    if GOV_HARD.search(s) and not legal: return ('govt', 'govt')
    if GOV_AMBIG.search(s) and not strong_real and n <= 4: return ('govt', 'govt')
    if GOV_MUNI.match(s) and n >= 2 and (t[0] in ('CITY', 'TOWN', 'VILLAGE', 'THE') or t[-1] in ('CITY', 'TOWN', 'VILLAGE', 'CRA', 'BOARD', 'HOUSING', 'UTILITIES') or GOV_MUNI_TAIL.match(s)): return ('govt', 'govt')
    if GOV_MUNI_TAIL.match(s): return ('govt', 'govt')
    if GOV_SOFT.search(s) and not strong_real and not SUB_INST.search(s) and not SUB_ASSOC.search(s): 
        # "WATER DISTRICT", "SCHOOL BOARD", "HOUSING AUTHORITY", "FOO DEVELOPMENT AUTHORITY", but not a person named "COUNTY"
        if not (n <= 2 and looks_like_person(t, given)): return ('govt', 'govt')
    def sub_for():
        if SUB_BANK.search(s) and (len([1 for m in SUB_BANK.finditer(s)]) and not (n <= 3 and looks_like_person(t, given) and t[-1] in ('BANK', 'BK', 'NA', 'N'))): 
            if not (SUB_BANK.findall(s) == ['N A'] and not re.search(r'\bN A\b$', s)): return 'bank'
        if SUB_UTIL.search(s): return 'utility'
        if SUB_ASSOC.search(s): return 'assoc'
        if SUB_INST.search(s): return 'inst'
        return 'biz'
    # strong organization
    if strong_real:
        # CO / PA ... handled in WEAK. other strong words always count, except they can't be a person-shaped name made only of weak words
        if TRUST.search(s) and not legal and sub_for() == 'biz': return ('trust', '')
        return ('corp', sub_for())
    # weak-only words: need backing or a non-person shape
    if t[-1] in ('PA', 'PC', 'SA', 'CO') or ' '.join(t[-2:]) in ('P A', 'P C', 'S A', 'N A'):
        if not (n == 2 and looks_like_person(t, given) and t[-1] == 'CO'):
            if not (t[-1] == 'CO' and n == 2 and looks_like_person(t, given)): return ('corp', sub_for())
    if TRUST.search(s) and looks_like_person(t, given): return ('trust', '')
    if t[-1] == 'COMMUNITY' and n >= 2 and not person_marker(t): return ('corp', 'assoc')
    wk = [m.group(0) for m in WEAK.finditer(s)] + [w for w in strong_hits if w in WEAKSET]
    if wk:
        last_is_weak = t[-1] in {x for w in wk for x in w.split()} or ' '.join(t[-2:]) in wk
        person_shape = looks_like_person(t, given) or person_marker(t)
        backed = len(set(wk)) >= 2 or (n >= 5) or (n >= 2 and t[0] in ORG_FIRST) or not last_is_weak and n >= 3
        if backed and not (person_shape and last_is_weak and len(set(wk)) < 2):
            return ('corp', sub_for())
        if not person_shape and n >= 2 and (last_is_weak or not last_is_weak) and not person_marker(t):
            return ('corp', sub_for())
    if TRUST.search(s): return ('trust', '')
    return ('person', '')

CAREOF = re.compile(r"^\s*(?:C\s?/\s?O|%|ATTN|ATT|ATTENTION|CARE OF|C O )\b|^\s*%|^\s*ATTN")
_RANK = {'govt': 3, 'corp': 2, 'trust': 1, 'person': 0}
def classify(owners, given=None):
    """owners: the (up to 3) owner-name strings of one parcel -> (kind, sub). Lines from the first 'C/O', 'ATTN', '%' on are mailing
    contacts, not owners, and are ignored. The remaining lines are read as one name ('SOUTH FLORIDA WATER' + 'MANAGEMENT DISTRICT',
    'CEMEX CONSTRUCTION MATERIALS' + 'FLORIDA LLC'); the first line alone is also tried, and the more organization-like result wins."""
    lines = []; carelines = []
    for o in owners:
        o = str(o or '').strip()
        if not o: continue
        if CAREOF.match(o.upper()):
            carelines.append(o); break
        lines.append(o)
    if not lines: return ('person', '')
    a = classify_one(lines[0], given)
    if len(lines) > 1:
        b = classify_one(' '.join(lines), given)
        if b[0] != 'person' or a[0] == 'person': a = b
    if a[0] == 'person' and carelines:
        # "VIZCAYA IN KENDALL" c/o "GOVER MGMT SERV S FL LLC": a name that is not person-shaped, managed by a company -> an entity
        t1 = norm(lines[0]).split()
        if t1 and not looks_like_person(t1, given) and not person_marker([w for w in t1 if w not in ('II', 'III')]) and not TRUST.search(' '.join(t1)) and len(t1) >= 3:
            c = classify_one(re.sub(r"^\s*(?:C\s?/\s?O|%|ATTN:?|ATT:?|ATTENTION:?|CARE OF)\s*", '', carelines[0].upper()), given)
            if c[0] in ('corp', 'govt'): return ('corp', 'biz')
    return a
