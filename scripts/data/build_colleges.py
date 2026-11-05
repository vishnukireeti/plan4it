#!/usr/bin/env python3
"""
Build the India-wide college directory used by the Colleges page.

Sources (public, cloned into .cache/sources/ on first run, pinned to a commit):
  - AISHE institution list (Ministry of Education) ...... name, AISHE code, state, district
  - AISHE affiliation list .............................. affiliating university, college type
  - AICTE approved-institution snapshot (Oct 2025) ....... ownership, address, women-only,
                                                            minority, courses with seat intake
  - JoSAA 2018-2025 opening/closing ranks ............... cutoffs for IITs, NITs, IIITs, GFTIs
  - DataMeet district boundaries (2019 centroids) ....... district lat/long for "nearby" search

Output (data/colleges/):
  index.json            states, per-state counts and districts (with lat/long), field list
  <state-code>.json     one file per state/UT, compact rows, loaded only when needed
  links.json            AISHE code + district for colleges already curated in index.html
  josaa.json            JoSAA 2025 final-round closing ranks, keyed by college id

Tiers (shown to students as plain labels):
  1  Detailed profile  - official course list with seat intake (AICTE), or JoSAA cutoffs
  2  Verified listing  - AISHE record plus at least one official detail: affiliating
                         university, AICTE ownership, or AISHE university status
  3  Basic profile     - AISHE name and location only ("detailed information being updated")

Nothing is guessed: fees, placements, rankings and admission claims are never generated.
Course *fields* (Engineering, Nursing, ...) come from AICTE course lists when available,
otherwise from clear words in the official name; those are marked as name-derived.

Run:  python3 scripts/data/build_colleges.py
"""
import collections
import difflib
import json
import math
import os
import re
import subprocess
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = os.path.join(ROOT, '.cache', 'sources')
OUT = os.path.join(ROOT, 'data', 'colleges')

SOURCES = {
    'aishe': ('https://github.com/BrahmjotSingh0/aishe-institutions-list.git', '0fc395e'),
    'affil': ('https://github.com/tridev1004/Indian-Colleges.git', '97fe42d'),
    'aicte': ('https://github.com/anburocky3/indian-colleges-data.git', '12fe687'),
    'josaa': ('https://github.com/JIGGLEO/JOSAA-CUTOFF_DATASET.git', '978bbb5'),
    'geo': ('https://github.com/infenia/indian-district-coordinates.git', '9fa3ade'),
}


def fetch_sources():
    os.makedirs(CACHE, exist_ok=True)
    for key, (url, commit) in SOURCES.items():
        d = os.path.join(CACHE, key)
        if not os.path.isdir(d):
            print('cloning', url)
            subprocess.check_call(['git', 'clone', '-q', url, d])
        subprocess.call(['git', '-C', d, 'fetch', '-q', '--depth', '50'], stderr=subprocess.DEVNULL)
        rc = subprocess.call(['git', '-C', d, 'checkout', '-q', commit], stderr=subprocess.DEVNULL)
        if rc != 0:
            print('  warning: could not pin', key, 'to', commit, '- using whatever is checked out')


# ---------------------------------------------------------------- states
STATES = [
    # canonical name, code
    ('Andhra Pradesh', 'ap'), ('Arunachal Pradesh', 'ar'), ('Assam', 'as'), ('Bihar', 'br'),
    ('Chhattisgarh', 'cg'), ('Goa', 'ga'), ('Gujarat', 'gj'), ('Haryana', 'hr'),
    ('Himachal Pradesh', 'hp'), ('Jharkhand', 'jh'), ('Karnataka', 'ka'), ('Kerala', 'kl'),
    ('Madhya Pradesh', 'mp'), ('Maharashtra', 'mh'), ('Manipur', 'mn'), ('Meghalaya', 'ml'),
    ('Mizoram', 'mz'), ('Nagaland', 'nl'), ('Odisha', 'od'), ('Punjab', 'pb'), ('Rajasthan', 'rj'),
    ('Sikkim', 'sk'), ('Tamil Nadu', 'tn'), ('Telangana', 'ts'), ('Tripura', 'tr'),
    ('Uttar Pradesh', 'up'), ('Uttarakhand', 'uk'), ('West Bengal', 'wb'),
    ('Andaman & Nicobar Islands', 'an'), ('Chandigarh', 'ch'),
    ('Dadra & Nagar Haveli and Daman & Diu', 'dd'), ('Delhi', 'dl'), ('Jammu & Kashmir', 'jk'),
    ('Ladakh', 'la'), ('Lakshadweep', 'ld'), ('Puducherry', 'py'),
]
STATE_CODE = dict(STATES)
STATE_ALIASES = {
    'andaman and nicobar islands': 'Andaman & Nicobar Islands',
    'andaman & nicobar': 'Andaman & Nicobar Islands',
    'jammu and kashmir': 'Jammu & Kashmir',
    'the dadra and nagar haveli and daman and diu': 'Dadra & Nagar Haveli and Daman & Diu',
    'dadra and nagar haveli and daman and diu': 'Dadra & Nagar Haveli and Daman & Diu',
    'dadra and nagar haveli': 'Dadra & Nagar Haveli and Daman & Diu',
    'daman and diu': 'Dadra & Nagar Haveli and Daman & Diu',
    'orissa': 'Odisha', 'pondicherry': 'Puducherry', 'nct of delhi': 'Delhi', 'new delhi': 'Delhi',
    'uttaranchal': 'Uttarakhand', 'telengana': 'Telangana',
}


def fix_state(st, district):
    # colleges in Leh and Kargil were filed under J&K before Ladakh became a union territory
    if st == 'Jammu & Kashmir' and re.search(r'\b(leh|kargil)\b', str(district or ''), re.I):
        return 'Ladakh'
    return st


def canon_state(s):
    s = re.sub(r'\s+', ' ', str(s or '')).strip()
    low = s.lower()
    for name, _ in STATES:
        if name.lower() == low:
            return name
    return STATE_ALIASES.get(low, '')


# ---------------------------------------------------------------- text helpers
SMALL = {'of', 'and', 'the', 'for', 'in', 'at', 'on', 'to', 'by', 'with', 'de', 'cum'}
KEEP_UPPER = {
    'IIT', 'NIT', 'IIIT', 'IIM', 'IISER', 'IISC', 'AIIMS', 'ITI', 'MBA', 'MCA', 'BCA', 'BBA', 'PGDM', 'DIET',
    'BHU', 'AMU', 'JNU', 'IGNOU', 'SRM', 'VIT', 'KIIT', 'BITS', 'NIFT', 'NID', 'ICAR', 'ICMR', 'CSIR', 'DRDO',
    'PG', 'UG', 'GNM', 'ANM', 'RV', 'BMS', 'PES', 'MS', 'KLE', 'SDM', 'NMAM', 'JSS', 'DAV', 'SD', 'MLA', 'MGM',
    'SVKM', 'NMIMS', 'MIT', 'COEP', 'VJTI', 'NSUT', 'DTU', 'IPU', 'GGSIPU', 'NBA', 'NAAC', 'UGC', 'AICTE', 'IT',
    'ICFAI', 'IES', 'IPS', 'RKDF', 'LNCT', 'SAGE', 'SGT', 'GLA', 'KCC', 'IMS', 'ABES', 'AKGEC', 'KIET', 'JIMS',
    'II', 'III', 'IV', 'KMC', 'SVS', 'SKR', 'KSR', 'PSG', 'PSNA', 'VSB', 'SNS', 'KPR', 'NGP', 'CMR', 'MLR',
    'GMR', 'GVP', 'VNR', 'CVR', 'BVRIT', 'JNTU', 'JNTUH', 'JNTUK', 'JNTUA', 'RVR', 'VRS', 'NBKR', 'SVU',
    'AU', 'SV', 'DY', 'YCM', 'BR', 'TKR', 'MVSR', 'CBIT', 'IARE', 'MREC', 'MRCET', 'HITAM', 'DIT', 'UIT',
    'UIET', 'SSN', 'MEPCO', 'ACE', 'AMC', 'BIT', 'BIET', 'NIE', 'KVG', 'KS', 'JSSATE', 'MSRIT', 'BNM', 'DSCE',
    'NHCE', 'CMRIT', 'BMSCE', 'RNSIT', 'GSSS', 'KLS', 'SJCE', 'MCE', 'SIT', 'SKIT', 'JECRC', 'MNIT', 'RTU',
    'BTU', 'CTAE', 'MBM', 'BM', 'GD', 'HMR', 'HR', 'JMIT', 'MMU', 'PEC', 'TIET', 'LPU', 'CGC', 'GNDEC', 'BBSBEC',
    'SLIET', 'NSIT', 'BPIT', 'MAIT', 'MSIT', 'GTBIT', 'BVCOE', 'HMRITM', 'GB', 'KR', 'DPG', 'MDU', 'GJU', 'CRSU',
    'KUK', 'PU', 'HPU', 'LLM', 'LLB', 'BED', 'MED', 'BSC', 'MSC', 'BA', 'MA', 'BCOM', 'MCOM', 'B.ED', 'M.ED',
}
ABBREV = [
    (r'\bgovt\b\.?', 'government'), (r'\bgovernmant\b', 'government'), (r'\bengg\b\.?', 'engineering'),
    (r'\binst\b\.?', 'institute'), (r'\btech\b\.?', 'technology'), (r'\bmgmt\b\.?', 'management'),
    (r'\bcoll\b\.?', 'college'), (r'\buniv\b\.?', 'university'), (r'\bsci\b\.?', 'science'),
    (r'\bpoly\b\.?', 'polytechnic'), (r'\bmahavidhyalaya\b', 'mahavidyalaya'), (r'\bmahavidalaya\b', 'mahavidyalaya'),
    (r'\bvidhyalaya\b', 'vidyalaya'), (r'\bsri\b', 'shri'), (r'\bshree\b', 'shri'), (r'\bsree\b', 'shri'),
    (r'\bst\b\.?', 'saint'), (r'\bdr\b\.?', 'dr'), (r'\bpvt\b\.?', 'private'), (r'\bltd\b\.?', 'limited'),
]


def clean_space(s):
    return re.sub(r'\s+', ' ', str(s or '').replace(' ', ' ')).strip(' ,.-')


def display_name(s):
    """Remove internal reference codes that leak into official names."""
    s = clean_space(s)
    s = re.sub(r'^\d{2,7}\s*[-:.]\s*', '', s)                  # "6444-Shriram Institute ..."
    s = re.sub(r'\s*\(\s*NIRF Code[^)]*\)+\s*', ' ', s, flags=re.I)  # "(NIRF Code (N-353))"
    s = re.sub(r'\s+\(?\d{3,6}\)?\s*$', '', s)                 # trailing "... 208" / "(626)"
    return smart_title(s)


def smart_title(s):
    """AISHE names arrive in ALL CAPS, all lower case, or Mixed. Only re-case the first two."""
    s = clean_space(s)
    letters = [ch for ch in s if ch.isalpha()]
    if not letters:
        return s
    upper_share = sum(1 for ch in letters if ch.isupper()) / len(letters)
    if 0.15 < upper_share < 0.85:
        return s  # already mixed case: trust it
    out = []
    for i, tok in enumerate(re.split(r'(\s+|-|/|\(|\))', s)):
        if not tok or re.fullmatch(r'\s+|-|/|\(|\)', tok):
            out.append(tok)
            continue
        bare = re.sub(r'[^A-Za-z.]', '', tok).upper()
        if bare in KEEP_UPPER or bare.replace('.', '') in KEEP_UPPER:
            out.append(tok.upper())
        elif re.fullmatch(r"([A-Za-z]\.)+[A-Za-z]?\.?,?", tok):  # initials like S.R.M. or B.Ed
            out.append(tok.upper() if len(tok) <= 4 or tok.count('.') >= 2 else tok.capitalize())
        elif tok.lower() in SMALL and i > 0:
            out.append(tok.lower())
        elif re.fullmatch(r"[A-Za-z]+'[sS]", tok):
            out.append(tok[0].upper() + tok[1:].lower())
        else:
            out.append(tok[:1].upper() + tok[1:].lower())
    res = ''.join(out)
    return re.sub(r'\bB\.ed\b', 'B.Ed', re.sub(r'\bD\.el\.ed\b', 'D.El.Ed', res, flags=re.I), flags=re.I)


STOP = {'the', 'of', 'and', 'for', 'in', 'at', 'a', 'an', 'to', 'by', 'with', 'cum', 'sfi', 'autonomous', 'aided', 'unaided',
        'po', 'post', 'dist', 'district', 'tal', 'taluka', 'tq', 'tehsil', 'via', 'near', 'opp'}


def norm_name(s):
    s = str(s or '').lower().replace('&', ' and ')
    s = re.sub(r'\(id:[^)]*\)', ' ', s)
    s = re.sub(r'\(([^)]{1,12})\)', ' ', s)  # drop short bracketed acronyms like (IIT) or (ANCOL)
    s = re.sub(r'^\s*\d{2,6}\s*[-:]\s*', ' ', s)  # leading internal codes like "2281-"
    s = re.sub(r'\bp\.?\s?o\b\.?', ' ', s)  # "P.O" post office
    for pat, rep in ABBREV:
        s = re.sub(pat, rep, s)
    s = re.sub(r"'s\b", '', s)
    s = re.sub(r"[^a-z0-9 ]", ' ', s)
    toks = [t for t in s.split() if t not in STOP]
    return toks


DISTRICT_RENAMES = {
    'faizabad': 'ayodhya', 'allahabad': 'prayagraj', 'gurgaon': 'gurugram', 'bangalore urban': 'bengaluru urban',
    'bangalore rural': 'bengaluru rural', 'bangalore': 'bengaluru urban', 'mysore': 'mysuru', 'tumkur': 'tumakuru',
    'belgaum': 'belagavi', 'bellary': 'ballari', 'shimoga': 'shivamogga', 'gulbarga': 'kalaburagi',
    'bijapur': 'vijayapura', 'chikmagalur': 'chikkamagaluru', 'mangalore': 'dakshina kannada', 'hubli': 'dharwad',
    'aurangabad maharashtra': 'chhatrapati sambhajinagar', 'osmanabad': 'dharashiv', 'ahmednagar': 'ahilyanagar',
    'nellore': 'sri potti sriramulu nellore', 'kadapa': 'ysr', 'cuddapah': 'ysr', 'ysr district': 'ysr',
    'mewat': 'nuh', 'hoshangabad': 'narmadapuram', 'calcutta': 'kolkata', 'bombay': 'mumbai', 'madras': 'chennai',
    'trivandrum': 'thiruvananthapuram', 'calicut': 'kozhikode', 'cochin': 'ernakulam', 'kanchipuram': 'kancheepuram',
    'tiruchirapalli': 'tiruchirappalli', 'trichy': 'tiruchirappalli', 'tuticorin': 'thoothukudi', 'nilgiris': 'the nilgiris',
    'sas nagar': 'sahibzada ajit singh nagar', 'mohali': 'sahibzada ajit singh nagar', 'nawanshahr': 'shahid bhagat singh nagar',
}


# Older or alternative names for the same district, per state -> the name students should see.
# Only true synonyms: districts created by a split stay separate because their colleges can't be
# re-assigned without an address.
STATE_DISTRICT_ALIASES = {
    'Andhra Pradesh': {'anantapur': 'Ananthapuramu', 'y s r kadapa': 'Y.S.R', 'ysr': 'Y.S.R'},
    'Assam': {'kamrup metropolitan': 'Kamrup Metro', 'sibsagar': 'Sivasagar'},
    'Bihar': {'kaimur': 'Kaimur (Bhabua)', 'west champaran': 'Pashchim Champaran', 'east champaran': 'Purbi Champaran'},
    'Chhattisgarh': {'kawardha': 'Kabeerdham', 'koriya': 'Korea'},
    'Gujarat': {'ahmadabad': 'Ahmedabad', 'dohad': 'Dahod', 'kutch': 'Kachchh', 'mehsana': 'Mahesana', 'the dangs': 'Dangs'},
    'Haryana': {'sonepat': 'Sonipat'},
    'Himachal Pradesh': {'kulu': 'Kullu'},
    'Jharkhand': {'kodarma': 'Koderma', 'east singhbum': 'East Singhbhum', 'purbi singhbhum': 'East Singhbhum',
                  'pashchimi singhbhum': 'West Singhbhum', 'sahibganj': 'Sahebganj', 'sareikela and kharsawan': 'Saraikela Kharsawan'},
    'Karnataka': {'coorg': 'Kodagu', 'd kannada dk': 'Dakshina Kannada'},
    'Madhya Pradesh': {'khandwa': 'Khandwa (East Nimar)', 'khargone': 'Khargone (West Nimar)'},
    'Maharashtra': {'ahmadnagar': 'Ahilyanagar', 'ahilyanagar': 'Ahilyanagar', 'aurangabad': 'Chhatrapati Sambhajinagar', 'bid': 'Beed', 'raigarh': 'Raigad'},
    'Odisha': {'balasore': 'Baleshwar', 'kendujhar keonjhar': 'Kendujhar', 'subarnapur sonepur': 'Sonepur'},
    'Punjab': {'ferozepur': 'Firozpur', 'mukatsar': 'Sri Muktsar Sahib', 's a s nagar': 'Sahibzada Ajit Singh Nagar'},
    'Rajasthan': {'chittaurgarh': 'Chittorgarh', 'dhaulpur': 'Dholpur'},
    'Sikkim': {'east district': 'Gangtok', 'east sikkim': 'Gangtok', 'south sikkim': 'Namchi', 'west sikkim': 'Gyalshing', 'north sikkim': 'Mangan'},
    'Uttar Pradesh': {'j p nagar': 'Amroha', 'jyotiba phule nagar': 'Amroha', 'kanshiram nagar': 'Kasganj', 'mahamaya nagar': 'Hathras',
                      'ramabai nagar kanpur dehat': 'Kanpur Dehat', 'sant ravidas nagar bhadohi': 'Bhadohi', 'sant ravidas nagar': 'Bhadohi', 'lakhimpur kheri': 'Kheri'},
    'West Bengal': {'darjiling': 'Darjeeling', 'haora': 'Howrah', 'hugli': 'Hooghly', 'koch bihar': 'Cooch Behar', 'north twenty four parganas': 'North 24 Parganas'},
    'Delhi': {'east': 'East Delhi', 'north': 'North Delhi', 'north west': 'North West Delhi', 'south': 'South Delhi', 'south west': 'South West Delhi',
              'central': 'Central Delhi', 'west': 'West Delhi', 'north east': 'North East Delhi', 'south east': 'South East Delhi'},
    'Jammu & Kashmir': {'bandipore': 'Bandipora', 'punch': 'Poonch', 'rajauri': 'Rajouri'},
    'Ladakh': {'leh ladakh': 'Leh'},
    'Lakshadweep': {'lakshadweep district': 'Lakshadweep'},
    'Puducherry': {'pondicherry': 'Puducherry'},
    'Andaman & Nicobar Islands': {'port blair': 'South Andamans'},
}


def norm_district(s):
    s = str(s or '').lower()
    s = re.sub(r'\b(district|dist|dt)\b\.?', ' ', s)
    s = re.sub(r'[^a-z ]', ' ', s)
    s = ' '.join(s.split())
    return DISTRICT_RENAMES.get(s, s)


def soft_tok_ratio(t, others):
    """1.0 for an exact word, otherwise similarity to the closest word (typos like gaja/gajja)."""
    if t in others:
        return 1.0
    if len(t) < 4:
        return 0.0
    best = 0.0
    for o in others:
        if abs(len(o) - len(t)) > 3 or o[:1] != t[:1]:
            continue
        r = difflib.SequenceMatcher(None, t, o).ratio()
        if r > best:
            best = r
    return best if best >= 0.8 else 0.0


# ---------------------------------------------------------------- fields (search tags)
# (field, regex on name/courses). Order matters only for display.
FIELD_RULES = [
    ('Technology', r'\b(engineering|technolog|polytechnic|b\.?\s?tech|m\.?\s?tech|b\.?e\.?\b|computer science|computer application|information technology|bca|mca)\b'),
    ('Management', r'\b(management|business|mba|bba|pgdm|commerce and management)\b'),
    ('Medical', r'\b(medical college|medical sciences|institute of medical|mbbs|dental|bds|ayurved|ayurvedic|homoeopath|homeopath|unani|siddha|naturopathy|yoga and naturopathy|aiims)\b'),
    ('Nursing & Paramedical', r'\b(nursing|paramedical|para medical|health science|allied health|physiotherapy|medical technology|medical lab|optometry|radiology|mlt)\b'),
    ('Pharmacy', r'\b(pharmacy|pharmaceutical|pharma|d\.?\s?pharm|b\.?\s?pharm)\b'),
    ('Law', r'\b(law|legal|llb|ll\.b|juridical)\b'),
    ('Education', r'\b(b\.?\s?ed|d\.?\s?el\.?\s?ed|m\.?\s?ed|college of education|institute of education|education college|teacher|teachers|training college|shikshan|shiksha|shikshak|d\.?\s?ed|diet|physical education|b\.?\s?p\.?\s?ed)\b'),
    ('Architecture', r'\b(architecture|planning|b\.?\s?arch)\b'),
    ('Agriculture', r'\b(agricultur|horticultur|forestry|veterinary|animal science|fisheries|dairy|sericulture)\w*'),
    ('Design', r'\b(design|fashion|fine arts|fine art|applied arts|visual arts|animation|nift|nid)\b'),
    ('Hospitality', r'\b(hotel management|hospitality|catering|culinary|tourism)\b'),
    ('Media', r'\b(journalism|mass communication|media|film)\b'),
    ('Commerce', r'\b(commerce|b\.?\s?com|accountancy)\b'),
    ('Science', r'(?<!medical )(?<!health )(?<!paramedical )(?<!nursing )(?<!pharmaceutical )(?<!computer )\bscience(s)?\b(?! and technology)|\bb\.?\s?sc\b'),
    ('Arts & Humanities', r'\b(arts|humanities|social science|oriental|sanskrit|music|vedic|languages)\b'),
]
FIELD_RX = [(f, re.compile(rx, re.I)) for f, rx in FIELD_RULES]
GENERAL_RX = re.compile(r'\b(mahavidyalaya|mahavidhyalaya|degree college|pg college|p\.?\s?g\.?\s?college|kanya|mahila|women.?s college|girls college|vidyapeeth|college)\b', re.I)
AICTE_FIELD = {
    'ENGINEERING AND TECHNOLOGY': 'Technology', 'COMPUTER APPLICATIONS': 'Technology', 'COMPUTER APPLICATION': 'Technology',
    'AI & DATA SCIENCE': 'Technology', 'MANAGEMENT': 'Management', 'MANAGEMENT/IT/ ITES': 'Management',
    'TRAVEL & TOURISM': 'Hospitality', 'LOGISTICS': 'Management', 'DESIGN': 'Design', 'APPLIED ARTS AND CRAFTS': 'Design',
    'HOTEL MANAGEMENT AND CATERING': 'Hospitality', 'PLANNING': 'Architecture', 'ARCHITECTURE': 'Architecture',
    'PHARMACY': 'Pharmacy',
}
FIELD_LIST = [f for f, _ in FIELD_RULES] + ['General degree (BA, BSc, BCom)']
FIELD_IDX = {f: i for i, f in enumerate(FIELD_LIST)}


def fields_from_name(name, kind):
    found = [f for f, rx in FIELD_RX if rx.search(name)]
    if 'Nursing & Paramedical' in found and 'Medical' in found and not re.search(r'medical college|mbbs|dental|aiims', name, re.I):
        found.remove('Medical')
    if not found and kind == 'C' and GENERAL_RX.search(name):
        found = ['General degree (BA, BSc, BCom)']
    return found


# ---------------------------------------------------------------- ownership
OWN_LABELS = ['', 'Government', 'Government-aided', 'Private', 'Central university', 'State university',
              'Deemed university (government)', 'Deemed university (private)', 'Private university']
OWN_FROM_AICTE = {
    'Government': 1, 'Govt aided': 2, 'Private-Self Financing': 3, 'Central University': 4,
    'State Government University': 5, 'Deemed to be University(Govt)': 6, 'Deemed to be University(Pvt)': 7,
    'State Private University': 8,
}
GOVT_NAME = re.compile(r'\b(government|govt|rajkiya|rajkeeya|rajakiya|sarkari|state institute|district institute of education)\b', re.I)


def own_from_name(name, kind):
    if GOVT_NAME.search(name):
        return 1
    if kind == 'U':
        if re.search(r'\bcentral university\b', name, re.I):
            return 4
        if re.search(r'\b(indian institute of technology|national institute of technology|indian institute of science|all india institute of medical)\b', name, re.I):
            return 1
    return 0


# ---------------------------------------------------------------- matching
# Words that say WHAT an institution is. Two names that share a family name but differ here
# are different institutions ("Ramdoot College of Education" vs "Ramdoot College of Pharmacy").
DISC_WORDS = [
    ('poly', r'polytechnic'), ('eng', r'engineering|engg|technolog'), ('comp', r'computer|information|\bbca\b|\bmca\b'),
    ('mgmt', r'management|business|\bmba\b|\bpgdm\b|\bbba\b'), ('pharm', r'pharma'),
    ('edu', r'\beducation\b|teacher|\btt\b|\bb\.?\s?ed\b|\bd\.?\s?el\.?\s?ed\b|shikshan|shiksha'),
    ('nurs', r'nursing|paramedical|para medical|allied health'), ('med', r'medical|medicine|dental|ayurved|homoeo|homeo|unani|siddha'),
    ('law', r'\blaw\b|\blegal\b'), ('arts', r'\barts?\b|humanities'), ('sci', r'\bsciences?\b'), ('com', r'commerce'),
    ('hotel', r'hotel|hospitality|catering'), ('arch', r'architecture|planning'),
    ('agri', r'agricultur|horticultur|veterinary|fisheries|dairy'), ('design', r'design|fashion|fine art'),
    ('univ', r'university|vishwavidyalaya|vishvavidyalaya'), ('degree', r'\bdegree\b'),
    ('pg', r'\bp\.?\s?g\.?\b|post ?graduate'), ('women', r'women|girls|mahila|kanya'),
    ('phys', r'physical education'), ('research', r'research'),
]
DISC_RX = [(k, re.compile(rx, re.I)) for k, rx in DISC_WORDS]
NONTECH = {'law', 'med', 'nurs', 'pharm', 'edu', 'arts', 'sci', 'com', 'agri', 'hotel', 'design', 'arch', 'phys'}


def disc_tags(name):
    return frozenset(k for k, rx in DISC_RX if rx.search(str(name or '')))


def disc_compatible(a, b, mode, extra=frozenset()):
    """strict: same set of discipline words. loose: one set contains the other (AICTE names are
    often shortened), plus the course list must not contradict a clearly non-technical name."""
    a2 = set(a) - {'research'}
    b2 = set(b) - {'research'}
    if ('women' in a2) != ('women' in b2):
        return False
    if mode == 'strict':
        return a2 == b2
    if a2 and b2 and not (a2 <= b2 or b2 <= a2):
        return False
    if extra and not a2 - {'women'}:
        # the AICTE name carries no discipline word: use its courses as the discipline
        bb = b2 - {'women', 'univ', 'degree', 'pg'}
        if bb & NONTECH and not bb - NONTECH and not (extra & bb):
            return False
    return True


AICTE_DISC = {'ENGINEERING AND TECHNOLOGY': 'eng', 'COMPUTER APPLICATIONS': 'comp', 'COMPUTER APPLICATION': 'comp',
              'MANAGEMENT': 'mgmt', 'DESIGN': 'design', 'APPLIED ARTS AND CRAFTS': 'design', 'PLANNING': 'arch',
              'ARCHITECTURE': 'arch', 'HOTEL MANAGEMENT AND CATERING': 'hotel', 'PHARMACY': 'pharm'}


class Matcher:
    """Find the best record for a name inside one state, using rare shared words first."""

    def __init__(self, records, key=lambda r: r['name']):
        self.recs = records
        self.key = key
        self._disc = [None] * len(records)
        self.toks = [set(norm_name(key(r))) for r in records]
        self.sorted = [' '.join(sorted(t)) for t in self.toks]
        df = collections.Counter(t for ts in self.toks for t in ts)
        n = max(len(records), 1)
        self.idf = {t: math.log((n + 1) / (c + 0.5)) for t, c in df.items()}
        self.inv = collections.defaultdict(list)
        for i, ts in enumerate(self.toks):
            for t in ts:
                self.inv[t].append(i)

    def jac(self, a, i):
        b = self.toks[i]
        idf = lambda t: self.idf.get(t, 3.0)
        inter = sum(idf(t) for t in a & b)
        union = sum(idf(t) for t in a | b)
        return inter / union if union else 0

    def score(self, qt, i, jac=None):
        """Both names must account for each other's distinctive words (weighted by rarity),
        allowing small typos per word. A name that adds an unmatched rare word
        ("Mahisagar BCA College" vs "Mahisagar Arts College") scores low on that side."""
        b = self.toks[i]
        idf = lambda t: self.idf.get(t, 3.0) ** 1.5  # rare words (family names) dominate
        def cover(x, y):
            tot = sum(idf(t) for t in x)
            return sum(idf(t) * soft_tok_ratio(t, y) for t in x) / tot if tot else 0
        ca, cb = cover(qt, b), cover(b, qt)
        if min(ca, cb) < 0.6:
            return min(ca, cb) * 0.8
        sr = difflib.SequenceMatcher(None, ' '.join(sorted(qt)), self.sorted[i]).ratio()
        return 0.75 * (ca + cb) / 2 + 0.25 * sr

    def disc(self, i):
        if self._disc[i] is None:
            self._disc[i] = disc_tags(self.key(self.recs[i]))
        return self._disc[i]

    def best(self, name, district=None, district_of=None, min_score=0.8, need_district=False,
             mode='loose', extra_disc=frozenset(), women=False):
        qt = set(norm_name(name))
        if not qt:
            return None, 0
        qd = disc_tags(name) | ({'women'} if women else set())
        # candidates must share at least one of the query's two rarest words
        rare = sorted(qt, key=lambda t: -self.idf.get(t, 3.0))[:2]
        cand = set()
        for t in rare:
            lst = self.inv.get(t, ())
            if len(lst) <= 3000:
                cand.update(lst)
        if not cand:
            return None, 0
        # cheap word-overlap first; the slower string comparison only for the top few
        pre = sorted(((self.jac(qt, i), i) for i in cand), reverse=True)[:15]
        scored = []
        nd = norm_district(district) if district else ''
        for jv, i in pre:
            if jv < 0.2:
                continue
            s = self.score(qt, i, jv)
            same = False
            if nd and district_of:
                od = norm_district(district_of(self.recs[i]))
                same = bool(od) and (od == nd or od in nd or nd in od or difflib.SequenceMatcher(None, od, nd).ratio() > 0.8)
                if same:
                    s += 0.06
                elif od:
                    s -= 0.1
            if need_district and not same:
                continue
            if not disc_compatible(qd, self.disc(i), mode, extra_disc):
                continue
            scored.append((s, i))
        if not scored:
            return None, 0
        scored.sort(reverse=True)
        s1, i1 = scored[0]
        s2 = 0
        for s, i in scored[1:]:
            if self.sorted[i] != self.sorted[i1]:  # an identical-name runner-up is a duplicate, not a rival
                s2 = s
                break
        if s1 >= min_score and s1 - s2 >= 0.03:
            return self.recs[i1], s1
        return None, s1


# ---------------------------------------------------------------- load sources
def load_json(*parts):
    with open(os.path.join(CACHE, *parts), encoding='utf-8') as f:
        return json.load(f)


AUDIT = []  # every fuzzy match made, written to .cache/match_audit.tsv for review


def build():
    fetch_sources()
    os.makedirs(OUT, exist_ok=True)
    report = collections.Counter()

    # --- AISHE master
    recs = {}
    for x in load_json('aishe', 'data', 'institutions.json'):
        code = clean_space(x.get('aishe_code')).upper()
        kind = code[:1]
        if kind not in ('U', 'C', 'S'):
            report['skipped research / other'] += 1
            continue
        st = canon_state(x.get('state'))
        if not st:
            report['skipped unknown state'] += 1
            continue
        recs[code] = {'code': code, 'kind': kind, 'name': clean_space(x.get('name')), 'state': fix_state(st, x.get('district')),
                      'district': smart_title(x.get('district') or ''), 'src': ['AISHE']}
    report['AISHE institutions'] = len(recs)

    # --- AISHE affiliation (adds colleges missing from the master list too)
    uni_names = {}
    for x in load_json('affil', 'colleges.json'):
        m = re.search(r'^(.*)\(Id:\s*([A-Z]-\d+)\)\s*$', x.get('college', ''))
        if not m:
            continue
        name, code = clean_space(m.group(1)), m.group(2).upper()
        um = re.search(r'^(.*)\(Id:\s*([A-Z]-\d+)\)\s*$', x.get('university', ''))
        uni, ucode = (clean_space(um.group(1)), um.group(2).upper()) if um else (clean_space(x.get('university')), '')
        if ucode:
            uni_names[ucode] = uni
        r = recs.get(code)
        if r is None:
            st = canon_state(x.get('state'))
            if not st:
                continue
            r = recs[code] = {'code': code, 'kind': code[:1], 'name': name, 'state': fix_state(st, x.get('district')),
                              'district': smart_title(x.get('district') or ''), 'src': ['AISHE']}
            report['added from AISHE affiliation list'] += 1
        r['uni'] = uni
        r['ucode'] = ucode
        r['ctype'] = clean_space(x.get('college_type'))
        if not r['district'] and x.get('district'):
            r['district'] = smart_title(x['district'])
    report['with affiliating university'] = sum(1 for r in recs.values() if r.get('uni'))

    by_state = collections.defaultdict(list)
    for r in recs.values():
        r['state'] = fix_state(r['state'], r['district'])
        by_state[r['state']].append(r)

    # --- district -> state lookup (for AICTE rows that only carry a district)
    dist_states = collections.defaultdict(set)
    for r in recs.values():
        if r['district']:
            dist_states[norm_district(r['district'])].add(r['state'])

    # --- AICTE: with programmes (has state), then the wider list for ownership/address only
    aicte_prog = load_json('aicte', 'data', 'institutions-with-programmes.json')
    aicte_all = [x for x in load_json('aicte', 'data', 'institutions.json') if x.get('aicte_id')]
    prog_ids = set(x['aicte_id'] for x in aicte_prog)
    matchers = {st: Matcher(rs) for st, rs in by_state.items()}
    aicte_only = []

    def attach_aicte(x, st, with_prog, min_score=0.82, need_district=False):
        m = matchers.get(st)
        extra = frozenset(AICTE_DISC[p['programme'].upper()] for p in (x.get('programmes') or [])
                          if (p.get('programme') or '').upper() in AICTE_DISC)
        hit, sc = (m.best(x['institute_name'], x.get('district'), lambda r: r['district'], min_score, need_district,
                          'loose', extra, x.get('women') == 'Y') if m else (None, 0))
        if hit is None:
            return None
        AUDIT.append(('aicte', st, round(sc, 3), x['institute_name'], x.get('district', ''), hit['name'], hit['district']))
        # One campus can have several AICTE records (one per programme). Merge them onto the
        # same AISHE college; keep the first AICTE id as the reference.
        hit.setdefault('aicte', x['aicte_id'])
        if x.get('institution_type') in OWN_FROM_AICTE:
            hit['own'] = OWN_FROM_AICTE[x['institution_type']]
        hit['women'] = hit.get('women') or x.get('women') == 'Y'
        hit['minority'] = hit.get('minority') or x.get('minority') == 'Y'
        if not hit.get('address'):
            hit['address'] = clean_space(x.get('address'))
        if 'AICTE' not in hit['src']:
            hit['src'].append('AICTE')
        if with_prog:
            hit['progs'] = (hit.get('progs') or []) + (x.get('programmes') or [])
            if x.get('university') and not hit.get('uni'):
                hit['uni'] = clean_space(x['university'])
        return hit

    # Merge AICTE records that are the same campus listed once per programme
    # ("Jyoti Nivas College (MBA)" + "Jyoti Nivas College (MCA)").
    merged_prog = collections.OrderedDict()
    for x in aicte_prog:
        st = canon_state(x.get('state'))
        if not st:
            continue
        k = (st, ' '.join(sorted(norm_name(x['institute_name']))), norm_district(x.get('district')))
        if k in merged_prog:
            merged_prog[k]['programmes'] = (merged_prog[k].get('programmes') or []) + (x.get('programmes') or [])
            report['AICTE per-programme records merged'] += 1
        else:
            merged_prog[k] = dict(x)
    aicte_prog = list(merged_prog.values())

    for x in aicte_prog:
        st = canon_state(x.get('state'))
        if not st:
            continue
        if attach_aicte(x, st, True):
            report['AICTE (with courses) matched to AISHE'] += 1
        elif attach_aicte(x, st, True, 0.78, need_district=True):
            report['AICTE (with courses) matched to AISHE, same district'] += 1
        else:
            aicte_only.append((x, st))
    for x in aicte_all:
        if x['aicte_id'] in prog_ids:
            continue
        sts = dist_states.get(norm_district(x.get('district')))
        if not sts or len(sts) != 1:
            continue
        if attach_aicte(x, next(iter(sts)), False):
            report['AICTE (ownership only) matched to AISHE'] += 1

    # AICTE institutes with a current course list but no AISHE match are still real, approved
    # institutes: list them on their own so a student can find them.
    for x, st in aicte_only:
        st = fix_state(st, x.get('district'))
        code = 'A' + re.sub(r'\D', '', x['aicte_id'])
        recs[code] = {'code': '', 'aicte': x['aicte_id'], 'kind': 'S', 'name': clean_space(x['institute_name']),
                      'state': st, 'district': smart_title(x.get('district') or ''), 'src': ['AICTE'],
                      'own': OWN_FROM_AICTE.get(x.get('institution_type'), 0), 'women': x.get('women') == 'Y',
                      'minority': x.get('minority') == 'Y', 'address': clean_space(x.get('address')),
                      'progs': x.get('programmes') or [], 'uni': clean_space(x.get('university') or ''), '_aicte_only': True}
        by_state[st].append(recs[code])
        report['AICTE institutes added (not in AISHE list)'] += 1

    # --- colleges already curated in index.html: link, do not duplicate
    existing = json.load(open(os.path.join(ROOT, '.cache', 'existing_colleges.json')))
    links = {}
    for c in existing:
        st = canon_state(c.get('state')) or canon_state(str(c.get('location', '')).split(',')[-1])
        m = matchers.get(st)
        if not m:
            continue
        best = None
        city = str(c.get('location', '')).split(',')[0]
        for nm in filter(None, [c.get('nirfName'), c.get('name'), re.sub(r'\s*\([^)]*\)', '', c.get('name', ''))]):
            hit, sc = m.best(nm, city, lambda r: r['district'], 0.82, False, 'strict')
            if hit is None:
                hit, sc = m.best(nm, city, lambda r: r['district'], 0.78, True, 'strict')
            if hit is not None and (best is None or sc > best[1]):
                best = (hit, sc)
        if best and not best[0].get('linked'):
            hit = best[0]
            AUDIT.append(('curated', st, round(best[1], 3), c.get('name', ''), city, hit['name'], hit['district']))
            hit['linked'] = c['id']
            links[c['id']] = {'aishe': hit.get('code', ''), 'district': hit.get('district', ''), 'state': hit['state']}
            if hit.get('uni'):
                links[c['id']]['uni'] = hit['uni']
    report['existing app colleges linked to AISHE'] = len(links)

    # --- JoSAA 2025 final round closing ranks (OPEN, gender-neutral)
    import csv
    jrows = collections.defaultdict(list)
    last_round = collections.Counter()
    with open(os.path.join(CACHE, 'josaa', 'cutoffsfinal.csv'), encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row['year'] != '2025' or not row['institute']:
                continue
            r = int(row['round'] or 0)
            last_round[row['institute']] = max(last_round[row['institute']], r)
            if row['seat type'] == 'OPEN' and row['gender'] == 'Gender-Neutral':
                jrows[row['institute']].append((r, row['academic program name'], row['quota'], row['opening rank'], row['closing rank']))
    josaa = {}
    ex_by_state = collections.defaultdict(list)
    for c in existing:
        ex_by_state[canon_state(c.get('state'))].append(c)
    ex_all = Matcher(existing)
    for inst, rows in jrows.items():
        fr = last_round[inst]
        final = [x for x in rows if x[0] == fr]
        if not final:
            continue
        target = None
        hit, sc = ex_all.best(inst, None, None, 0.78, False, 'strict')
        if hit is not None:
            target = hit['id']
        else:
            for st, m in sorted(matchers.items(), key=lambda kv: -int(kv[0].lower() in inst.lower())):
                h, s2 = m.best(inst, None, None, 0.86, False, 'strict')
                if h is not None:
                    target = 'd-' + STATE_CODE[h['state']] + '-' + (h['code'] or h['aicte']).lower()
                    h['josaa'] = True
                    break
        if not target:
            report['JoSAA institutes not matched'] += 1
            continue
        progs = []
        for _, prog, quota, op, cl in sorted(final, key=lambda x: (x[1], x[2])):
            try:
                progs.append([re.sub(r'\s+', ' ', prog), quota, int(float(op)), int(float(cl))])
            except ValueError:
                continue
        josaa[target] = {'name': inst, 'round': fr, 'year': 2025, 'rows': progs}
    report['JoSAA institutes with 2025 cutoffs'] = len(josaa)

    # --- district centroids
    cent = load_json('geo', 'json', 'centroids', 'india-districts-centroids-2019.json')
    cent_by_state = collections.defaultdict(list)
    for d in cent:
        st = canon_state(d.get('st_nm'))
        if st:
            cent_by_state[fix_state(st, d.get('district'))].append(d)

    def district_ll(st, dname):
        # try the name shown to students and any older names that map onto it
        names = [dname] + [k for k, v in STATE_DISTRICT_ALIASES.get(st, {}).items() if v == dname]
        best, bs = None, 0
        for nm in names:
            nd = norm_district(nm)
            for d in cent_by_state.get(st, []):
                cd = norm_district(d['district'])
                s = difflib.SequenceMatcher(None, nd, cd).ratio()
                if cd == nd or (len(cd) > 3 and (cd in nd.split() or nd in cd.split())):
                    s = max(s, 0.9)
                if s > bs:
                    best, bs = d, s
        if best and bs >= 0.75:
            return round(best['latitude'], 3), round(best['longitude'], 3)
        return None

    # --- one spelling per district. AISHE records use several ("Bellary" and "Ballari",
    # "Banaskantha" and "Banas Kantha"); students should see one district, with all its colleges.
    for st, rs in by_state.items():
        groups = collections.defaultdict(collections.Counter)
        for r in rs:
            if r['district']:
                groups[norm_district(r['district'])][r['district']] += 1
        keys = sorted(groups, key=lambda k: -sum(groups[k].values()))
        target = {}
        for k in keys:
            if k in target:
                continue
            target[k] = k
            ks = k.replace(' ', '')
            for k2 in keys:
                if k2 in target:
                    continue
                k2s = k2.replace(' ', '')
                if ks == k2s or difflib.SequenceMatcher(None, ks, k2s).ratio() >= 0.9:
                    target[k2] = k
        display = {}
        renamed_to = set(DISTRICT_RENAMES.values())
        for k in keys:
            if target[k] != k:
                continue
            spellings = collections.Counter()
            for k2 in keys:
                if target[k2] == k:
                    spellings.update(groups[k2])
            # prefer the current official name when a rename applies (Ballari over Bellary)
            official = [sp for sp in spellings if k in renamed_to and norm_district(sp) == k and
                        re.sub(r'[^a-z ]', ' ', sp.lower()).split() == k.split()]
            display[k] = official[0] if official else (smart_title(k) if k in renamed_to else spellings.most_common(1)[0][0])
        aliases = STATE_DISTRICT_ALIASES.get(st, {})
        for r in rs:
            if r['district']:
                k = target.get(norm_district(r['district']))
                if k and display.get(k) and display[k] != r['district']:
                    r['district'] = display[k]
                    report['district spellings unified'] += 1
                a = aliases.get(re.sub(r'[^a-z ]', ' ', r['district'].lower()).split() and ' '.join(re.sub(r'[^a-z ]', ' ', r['district'].lower()).split()))
                if a and a != r['district']:
                    r.setdefault('old_district', r['district'])
                    r['district'] = a
                    report['district old names mapped'] += 1

    # --- merge exact duplicates: same words in the name, same district, same state.
    # AISHE sometimes registers one college twice; AICTE-only rows can repeat an AISHE row.
    def richness(r):
        return (bool(r.get('linked')), bool(r.get('progs')), bool(r.get('uni')), bool(r.get('aicte')), bool(r.get('code')), -len(r['name']))
    for st in list(by_state):
        groups = collections.defaultdict(list)
        for r in by_state[st]:
            groups[(' '.join(sorted(norm_name(r['name']))), norm_district(r['district']))].append(r)
        keep = []
        for k, g in groups.items():
            if len(g) == 1 or not k[0]:
                keep.extend(g)
                continue
            g.sort(key=richness, reverse=True)
            main = g[0]
            for o in g[1:]:
                for f in ('uni', 'ucode', 'ctype', 'aicte', 'own', 'address', 'code', 'linked'):
                    if not main.get(f) and o.get(f):
                        main[f] = o[f]
                main['women'] = main.get('women') or o.get('women')
                main['minority'] = main.get('minority') or o.get('minority')
                if o.get('progs'):
                    main['progs'] = (main.get('progs') or []) + o['progs']
                main.setdefault('alt', []).append(o.get('code') or o.get('aicte'))
                report['duplicates merged'] += 1
            keep.append(main)
        by_state[st] = keep
    # an existing curated college may also match a second, differently-coded AISHE row
    linked_keys = set()
    for st, rs in by_state.items():
        for r in rs:
            if r.get('linked'):
                linked_keys.add((st, ' '.join(sorted(norm_name(r['name'])))))
    for st, rs in by_state.items():
        for r in rs:
            if not r.get('linked') and (st, ' '.join(sorted(norm_name(r['name'])))) in linked_keys and r['kind'] != 'C':
                r['linked'] = 'dup'
                report['rows hidden: same as a curated college'] += 1

    # --- write one compact file per state
    index_states, total = [], collections.Counter()
    for st, code in STATES:
        rows_out, unis, uni_idx = [], [], {}
        dists = collections.Counter()
        for r in sorted(by_state.get(st, []), key=lambda r: r['name'].lower()):
            if r.get('linked'):
                continue
            name = display_name(r['name'])
            kind = r['kind']
            progs = r.get('progs') or []
            courses = []
            fset = []
            levels = set()
            for p in progs:
                lv = (p.get('level') or '').upper()
                lvc = 'D' if 'DIPLOMA' in lv and 'POST GRADUATE' not in lv else 'P' if 'POST' in lv or lv == 'FELLOWSHIP' else 'U'
                levels.add(lvc)
                f = AICTE_FIELD.get((p.get('programme') or '').upper())
                if f and f not in fset:
                    fset.append(f)
                try:
                    intake = int(p.get('intake') or 0)
                except ValueError:
                    intake = 0
                course = smart_title(p.get('course') or '')
                if course:
                    courses.append([lvc, course, intake])
            # merge duplicate course rows (shifts) by adding their seats
            merged = collections.OrderedDict()
            for lvc, course, intake in courses:
                k = (lvc, course)
                merged[k] = merged.get(k, 0) + intake
            courses = [[k[0], k[1], v] for k, v in merged.items()]
            name_fields = fields_from_name(r['name'], kind)
            fsrc = 'a' if fset else ('n' if name_fields else '')
            for f in name_fields:
                if f not in fset:
                    fset.append(f)
            if not levels:
                if re.search(r'\bpolytechnic\b|school of nursing|\bd\.?\s?el\.?\s?ed\b|\bd\.?\s?pharm', r['name'], re.I):
                    levels.add('D')
                if kind == 'U' or re.search(r'\b(p\.?\s?g\.?|post ?graduate)\b', r['name'], re.I):
                    levels.update('UP')
            own = r.get('own') or own_from_name(r['name'], kind)
            own_src = 'a' if r.get('own') else ('n' if own else '')
            uni = r.get('uni', '')
            ui = -1
            if uni:
                if uni not in uni_idx:
                    uni_idx[uni] = len(unis)
                    unis.append(uni)
                ui = uni_idx[uni]
            if courses or r.get('josaa'):
                tier = 1
            elif uni or r.get('aicte') or kind == 'U' or r.get('_aicte_only'):
                tier = 2
            else:
                tier = 3
            pin = ''
            pm = re.search(r'\b(\d{6})\b', (r.get('address') or '') + ' ' + r['name'])
            if pm:
                pin = pm.group(1)
            rid = 'd-' + code + '-' + (r['code'] or ('a' + re.sub(r'\D', '', r.get('aicte', '')))).lower()
            flags = (1 if r.get('women') else 0) | (2 if r.get('minority') else 0) | (4 if fsrc == 'n' else 0) | (8 if own_src == 'n' else 0)
            ctype = {'Affiliated College': 1, 'Constituent / University College': 2, 'Recognized Center': 3,
                     'PG Center / Off-Campus Center': 4}.get(r.get('ctype', ''), 0)
            rows_out.append([
                rid, name, r['district'], kind, ctype, own, tier, r['code'], ui, flags,
                ''.join(chr(97 + FIELD_IDX[f]) for f in fset), ''.join(sorted(levels)),
                courses, smart_title(r.get('address', '')), pin, r.get('aicte', ''),
            ])
            dists[r['district']] += 1
            total['tier%d' % tier] += 1
        dlist = []
        for dn, n in sorted(dists.items(), key=lambda z: z[0]):
            if not dn:
                continue
            ll = district_ll(st, dn)
            dlist.append([dn, n] + (list(ll) if ll else []))
        payload = {
            'v': 1, 'state': st, 'code': code,
            'cols': ['id', 'name', 'district', 'kind', 'ctype', 'own', 'tier', 'aishe', 'uni', 'flags', 'fields', 'levels', 'courses', 'address', 'pin', 'aicte'],
            'unis': unis, 'rows': rows_out,
        }
        path = os.path.join(OUT, code + '.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
        tiers = collections.Counter(r[6] for r in rows_out)
        index_states.append({'name': st, 'code': code, 'count': len(rows_out), 't1': tiers[1], 't2': tiers[2], 't3': tiers[3],
                             'bytes': os.path.getsize(path), 'districts': dlist})

    index = {
        'v': 1, 'built': date.today().isoformat(),
        'fields': FIELD_LIST, 'own': OWN_LABELS,
        'kinds': {'U': 'University', 'C': 'College', 'S': 'Standalone institution'},
        'ctypes': ['', 'Affiliated college', 'Constituent / university college', 'Recognised centre', 'PG / off-campus centre'],
        'tiers': {'1': 'Detailed profile', '2': 'Verified listing', '3': 'Basic profile'},
        'sources': [
            {'name': 'AISHE institution directory (Ministry of Education)', 'url': 'https://dashboard.aishe.gov.in/hedirectory/', 'via': SOURCES['aishe'][0]},
            {'name': 'AISHE college affiliations', 'url': 'https://dashboard.aishe.gov.in/hedirectory/', 'via': SOURCES['affil'][0]},
            {'name': 'AICTE approved institutions and courses (snapshot Oct 2025)', 'url': 'https://facilities.aicte-india.org/dashboard/pages/angulardashboard.php', 'via': SOURCES['aicte'][0]},
            {'name': 'JoSAA opening and closing ranks 2025', 'url': 'https://josaa.nic.in/', 'via': SOURCES['josaa'][0]},
            {'name': 'District boundaries (DataMeet, 2019)', 'url': 'https://github.com/datameet/indian-district-boundaries', 'via': SOURCES['geo'][0]},
        ],
        'total': sum(s['count'] for s in index_states),
        'states': index_states,
    }
    with open(os.path.join(OUT, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, separators=(',', ':'))
    with open(os.path.join(OUT, 'links.json'), 'w', encoding='utf-8') as f:
        json.dump(links, f, ensure_ascii=False, separators=(',', ':'))
    with open(os.path.join(OUT, 'josaa.json'), 'w', encoding='utf-8') as f:
        json.dump(josaa, f, ensure_ascii=False, separators=(',', ':'))

    with open(os.path.join(ROOT, '.cache', 'match_audit.tsv'), 'w', encoding='utf-8') as f:
        for a in AUDIT:
            f.write('\t'.join(str(v) for v in a) + '\n')
    print('\n'.join('%-48s %s' % (k, v) for k, v in report.items()))
    print('directory rows:', index['total'], dict(total))
    print('bytes total:', sum(s['bytes'] for s in index_states))


if __name__ == '__main__':
    build()
