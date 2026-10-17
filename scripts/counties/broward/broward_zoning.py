"""Plain-language zoning type for Broward city / county zoning codes and for the Broward County Land Use Plan (FLU).
zt (zone type, same keys the app already uses for Monroe): sf single-family, duplex, mf multifamily, mixed, com commercial, ind industrial / marine, civic public / institutional / park, other conservation / agricultural / water.
Classification is by keywords in the published district description + code prefix: a SCREEN, never a determination (each city's code decides)."""
import re
FLU = {  # Broward County Land Use Plan, state land-use code (SLUC1) -> (label, zt, density du/ac)
 28: ('Rural Ranches (1 unit / 5 acres)', 'sf', 0.2), 29: ('Rural Estates (1 unit / 2.5 acres)', 'sf', 0.4), 30: ('Estate (1) Residential', 'sf', 1), 31: ('Low (2) Residential', 'sf', 2),
 32: ('Low (3) Residential', 'sf', 3), 33: ('Low (5) Residential', 'sf', 5), 34: ('Rural Residential (10 acre)', 'sf', 0.1), 36: ('Low-Medium (10) Residential', 'duplex', 10),
 37: ('Medium (16) Residential', 'mf', 16), 38: ('Medium-High (25) Residential', 'mf', 25), 39: ('High (50) Residential', 'mf', 50), 222: ('Irregular Residential', 'sf', 0),
 100: ('Activity Center (mixed use)', 'mixed', 0), 60: ('Commerce', 'com', 0), 20: ('Agricultural', 'other', 0), 5: ('Conservation - Natural Reservation', 'other', 0), 555: ('Conservation - Reserve Water Supply', 'other', 0),
 10: ('Recreation and Open Space', 'civic', 0), 15: ('Commercial Recreation', 'com', 0), 40: ('Community Facilities', 'civic', 0), 110: ('Electrical Generation Facility', 'civic', 0),
 444: ('Mining', 'ind', 0), 70: ('Transportation', 'civic', 0), 1: ('Water', 'other', 0), 0: ('Dashed-line area (see city plan)', 'other', 0)}
def zt_of(code, desc):
    c = (code or '').strip().upper(); t = ' ' + re.sub(r'[^a-z0-9 ]', ' ', (desc or '').lower()) + ' '
    if re.search(r'conserv|preserv|natural|wetland|everglades|agricult|water|canal|lake| row |right of way', t): return 'other'
    if re.search(r'\b(public|government|civic|institution|school|university|park|recreation|open space|utilit|cemetery|church|religious|community facilit|hospital|airport|transport|fire|police|library)', t): return 'civic'
    if re.search(r'industr|manufactur|warehouse|marine|boat|port |\bm-?\d|\bi-?\d|\bli\b', t) and not re.search(r'residential', t): return 'ind'
    if re.search(r'mixed|planned|\bpud\b|\bpd\b|downtown|transit|urban|redevelop|\bmu\b|live work|activity center|village|town center|\brac\b|nra|ncd|\bsra\b|overlay', t): return 'mixed'
    if re.search(r'duplex|two family|two-family|2 family|\bt-?r?\b|\brd\b|\brd-', t): return 'duplex'
    if re.search(r'multi|apartment|townhouse|town house|garden|high density|medium density|high-density|medium-density|condo|\brm\b|\brm-|\br-?m\d|\bmf\b|hotel|motel|resort|\brh\b', t): return 'mf'
    if re.search(r'commercial|business|office|retail|shopping|neighborhood|general|tourist|\bb-?\d|\bc-?\d|\bcb\b|\bcg\b|\bbp\b|\bo-?\d', t): return 'com'
    if re.search(r'single|one family|one-family|estate|ranch|\brs\b|\brs-|\br-?1|\br1|\bre\b|\bra\b|\bsf\b|\bsf-|\be-?\d|\bsd\b|residential', t): return 'sf'
    m = re.match(r'^(RS|R-?1|R1|RE|RA|SF|E|A|RM|RMF|MF|B|C|CB|CG|I|M|PUD|PD|RC|RD|DU|T)', c)
    if m: return {'RS': 'sf', 'R1': 'sf', 'R-1': 'sf', 'RE': 'sf', 'RA': 'sf', 'SF': 'sf', 'E': 'sf', 'A': 'other', 'RM': 'mf', 'RMF': 'mf', 'MF': 'mf', 'B': 'com', 'C': 'com', 'CB': 'com', 'CG': 'com', 'I': 'ind', 'M': 'ind', 'PUD': 'mixed', 'PD': 'mixed', 'RC': 'mixed', 'RD': 'duplex', 'DU': 'duplex', 'T': 'duplex'}[m.group(1)]
    return 'other'
