"""EnerGov portal list shared by fetch_energov.py and merge_permits.py: slug -> (city, PA municipality code, portal base URL)."""
import os, json
PORTALS = {
    'hialeah':       ('Hialeah', '04', 'https://hialeahfl-energovpub.tylerhost.net/apps/selfservice'),
    'miami_gardens': ('Miami Gardens', '34', 'https://miamigardensfl-energovpub.tylerhost.net/apps/selfservice'),
    'coral_gables':  ('Coral Gables', '03', 'https://coralgablesfl-energovpub.tylerhost.net/apps/selfservice'),
    'miami_beach':   ('Miami Beach', '02', 'https://energovcss.miamibeachfl.gov/EnerGovProd/SelfService'),
    'surfside':      ('Surfside', '14', 'https://surfsidefl-energovpub.tylerhost.net/apps/selfservice'),
    'north_bay':     ('North Bay Village', '23', 'https://northbayvillagefl-energovpub.tylerhost.net/apps/selfservice'),
    'miami_shores':  ('Miami Shores', '11', 'https://villageofmiamishoresfl-energovweb.tylerhost.net/apps/selfservice'),
    'doral':         ('Doral', '35', 'https://doralfl-energovweb.tylerhost.net/apps/selfservice'),
    'nmb':           ('North Miami Beach', '07', 'https://css.northmiamibeachfl.gov/energovprod/selfservice'),
    'homestead':     ('Homestead', '10', 'https://cityofhomesteadfl-energovweb.tylerhost.net/apps/selfservice'),
    'north_miami':   ('North Miami', '06', 'https://cityofnorthmiamifl-energovweb.tylerhost.net/apps/selfservice'),   # tenant live since 2026: ~9 permits / 3 cases
    'sweetwater':    ('Sweetwater', '25', 'https://cityofsweetwaterfl-energovweb.tylerhost.net/apps/selfservice'),    # live since 2026
    'cutler_bay':    ('Cutler Bay', '36', 'https://townofcutlerbayfl-energovweb.tylerhost.net/apps/selfservice'),     # live since 2026
    'opa_locka':     ('Opa-locka', '08', 'https://cityofopalockafl-energovweb.tylerhost.net/apps/selfservice'),       # live, essentially empty (0 permits, 1 case)
}

