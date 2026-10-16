"""Plain-language zoning for Monroe County + the four mapped municipalities.
ZINFO[(jurisdiction, CODE)] = (plain-language name, group). Groups: sf single-family, low low-density residential, mf multi-family / higher density, mh mobile home / RV,
cm commercial, mx mixed use, in industrial / maritime, cs conservation / native / no-build, pu public / institutional / park, mi military / airport, rs resort / tourist.
Descriptions follow the county / city land-use district names (Monroe County LDC ch.130, Key West / Marathon / Islamorada codes); they are labels for screening only."""
GROUP_LABEL = {'sf': 'Single-family residential', 'low': 'Low-density residential', 'mf': 'Multi-family / higher-density residential', 'mh': 'Mobile home / RV', 'cm': 'Commercial',
               'mx': 'Mixed use', 'in': 'Industrial / maritime', 'cs': 'Conservation / native area (no-build)', 'pu': 'Public / institutional / park', 'mi': 'Military / airport',
               'rs': 'Resort / tourist', 'na': 'Not mapped'}
RES = {'sf', 'low', 'mf', 'mh', 'mx', 'rs'}
COUNTY = {
 'IS': ('Improved Subdivision (platted single-family lots)', 'sf'), 'IS-D': ('Improved Subdivision (platted lots)', 'sf'), 'IS-DM': ('Improved Subdivision (platted lots)', 'sf'),
 'IS-M': ('Improved Subdivision (mobile homes allowed)', 'sf'), 'IS-V': ('Improved Subdivision (vacation rental)', 'sf'),
 'SR': ('Suburban Residential (low density)', 'low'), 'SR-L': ('Suburban Residential - Limited (low density)', 'low'), 'SS': ('Sparsely Settled Residential (very low density)', 'low'),
 'UR': ('Urban Residential (multi-family allowed)', 'mf'), 'URM': ('Urban Residential - Mobile Home', 'mh'), 'URM-L': ('Urban Residential - Mobile Home (Limited)', 'mh'),
 'RV': ('Recreational Vehicle District', 'mh'), 'SC': ('Suburban Commercial', 'cm'), 'UC': ('Urban Commercial', 'cm'), 'C1': ('Commercial 1', 'cm'), 'C2': ('Commercial 2', 'cm'),
 'MU': ('Mixed Use (residential + commercial)', 'mx'), 'I': ('Industrial', 'in'), 'MI': ('Maritime Industries', 'in'), 'CFA': ('Commercial Fishing Area', 'in'), 'CFV': ('Commercial Fishing Village', 'in'),
 'CFSD': ('Commercial Fishing Special District', 'in'), 'DR': ('Destination Resort', 'rs'), 'AD': ('Airport District', 'mi'), 'MF': ('Military Facilities', 'mi'),
 'NA': ('Native Area (development essentially prohibited)', 'cs'), 'MN': ('Mainland Native Area (development essentially prohibited)', 'cs'), 'OS': ('Offshore Island (very limited development)', 'cs'),
 'CD': ('Conservation District', 'cs'), 'PR': ('Park and Refuge', 'cs'), 'RESEARCH': ('Research district', 'pu'), 'ACCC': ('Area of Critical County Concern', 'pu')}
KEYWEST = {
 'SF': ('Single-family', 'sf'), 'LDR-C': ('Coastal low-density residential', 'low'), 'MDR': ('Medium-density residential', 'mf'), 'MDR-C': ('Coastal medium-density residential', 'mf'), 'MDR-1': ('Medium-density residential 1', 'mf'),
 'HMDR': ('Historic medium-density residential', 'mf'), 'HSMDR': ('Historic special medium-density residential', 'mf'), 'HDR': ('High-density residential', 'mf'), 'HHDR': ('Historic high-density residential', 'mf'),
 'HDR 1': ('High-density residential', 'mf'), 'RO': ('Residential / office', 'mx'), 'HRO': ('Historic residential / office', 'mx'), 'HRCC': ('Historic residential-commercial core', 'mx'),
 'HRCC-1': ('Historic residential-commercial core 1', 'mx'), 'HRCC-2': ('Historic residential-commercial core 2', 'mx'), 'HRCC-3': ('Historic residential-commercial core 3', 'mx'), 'HRCC-4': ('Historic residential-commercial core 4', 'mx'),
 'HNC-1': ('Historic neighborhood commercial 1', 'cm'), 'HNC-2': ('Historic neighborhood commercial 2', 'cm'), 'HNC-3': ('Historic neighborhood commercial 3', 'cm'), 'HNC-4': ('Historic neighborhood commercial 4', 'cm'),
 'CG': ('General commercial', 'cm'), 'CL': ('Limited commercial', 'cm'), 'CT': ('Commercial tourist', 'rs'), 'HCT': ('Historic commercial tourist', 'rs'), 'PS': ('Public services', 'pu'), 'HPS': ('Historic public / semi-public services', 'pu'),
 'HPS-1': ('Historic public services 1', 'pu'), 'HPS-2': ('Historic public services 2', 'pu'), 'PRD': ('Planned redevelopment and development', 'mx'), 'HPRD': ('Historic planned redevelopment', 'mx'),
 'M': ('Military', 'mi'), 'A': ('Airport', 'mi'), 'CM': ('Conservation - mangrove (no-build)', 'cs'), 'C-OW': ('Conservation - outstanding waters (no-build)', 'cs'), 'C-TW': ('Conservation - tidal wetlands (no-build)', 'cs'),
 'C-FW': ('Conservation - freshwater wetlands (no-build)', 'cs'), 'C-UH': ('Conservation - upland hammock (no-build)', 'cs')}
MARATHON = {
 'R-C': ('Residential Conservation (very low density)', 'low'), 'RL': ('Residential Low', 'low'), 'RM': ('Residential Medium', 'sf'), 'RM-1': ('Residential Medium 1', 'sf'), 'RM-2': ('Residential Medium 2', 'sf'),
 'R-MH': ('Residential - Mobile Home', 'mh'), 'RH': ('Residential High (multi-family)', 'mf'), 'MU': ('Mixed Use', 'mx'), 'MU-M': ('Mixed Use - Maritime', 'mx'), 'I-G': ('Industrial General', 'in'), 'I-M': ('Industrial Maritime', 'in'),
 'C-NA': ('Conservation - Native Area (no-build)', 'cs'), 'C-OI': ('Conservation - Offshore Island (no-build)', 'cs'), 'PR': ('Parks and Recreation', 'pu'), 'P': ('Public', 'pu'), 'A': ('Airport', 'mi')}
ISLAMORADA = {  # Village of Islamorada LDC ch.30 div. 30-V-2 (Sec 30-682..703)
 'NR': ('Native Residential (1 acre min, 1 unit per 4 acres)', 'low'), 'RE': ('Residential Estate (0.5 acre min, 1 unit per 2 acres)', 'low'),
 'R1': ('Residential Single-Family (4,500 sf min lot)', 'sf'), 'R1M': ('Residential Single-Family, masonry only (4,500 sf min lot)', 'sf'),
 'RMH': ('Residential Mobile Home (single-family or mobile home)', 'mh'), 'R2': ('Residential Duplex (up to 2 units, 5,000 sf min lot)', 'sf'),
 'R3': ('Residential Triplex (deed-restricted affordable, 12,000 sf min)', 'mf'), 'R4': ('Residential Fourplex (deed-restricted affordable, 16,000 sf min)', 'mf'),
 'MF': ('Multifamily (2-4 units by right, 6 units/acre)', 'mf'), 'MH': ('Mobile Home Park', 'mh'), 'SR': ('Settlers Residential (pre-FIRM neighborhoods)', 'sf'),
 'VC': ('Village Center (mixed business + residential)', 'mx'), 'TC': ('Tourist Commercial', 'rs'), 'CF': ('Commercial Fishing', 'in'), 'MR': ('Marine Use', 'in'),
 'HC': ('Highway Commercial', 'cm'), 'NC': ('Neighborhood Commercial', 'mx'), 'I': ('Industrial', 'in'), 'C': ('Conservation (no building; density transfer only)', 'cs'),
 'TA': ('Tavernaero Airstrip (single-family with aircraft parking)', 'sf'), 'PS': ('Public and Semi-Public Services', 'pu'), 'R': ('Recreation', 'pu'), 'M': ('Mariculture', 'in')}
TABLES = {'Unincorporated': COUNTY, 'Key West': KEYWEST, 'Marathon': MARATHON, 'Islamorada': ISLAMORADA}
def lookup(jur, code):
    t = TABLES.get(jur, {}); c = (code or '').strip().upper()
    if c in t: return t[c]
    if jur == 'Unincorporated' and c.startswith('CFSD'): return t['CFSD']
    if jur == 'Key West' and c.split('-')[0] in ('HNC', 'HRCC', 'HPS') and c in t: return t[c]
    if jur == 'Key West' and c.startswith('HNC'): return ('Historic neighborhood commercial', 'cm')
    if jur == 'Key West' and c.startswith('HRCC'): return ('Historic residential-commercial core', 'mx')
    return ((code or 'Unknown').strip() + ' (see local code)', 'na')
