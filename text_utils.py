"""
Text normalization and search utilities for Agent Helper.
Provides text processing, fuzzy matching, and search ranking.
"""

import re
from typing import List, Tuple
from difflib import SequenceMatcher

# Try to import rapidfuzz; fall back to difflib if not available
try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False

def normalize_text(text: str) -> str:
    """Normalize text for comparison: lowercase, strip, remove extra spaces."""
    return re.sub(r'\s+', ' ', text.lower().strip())

def fuzzy_match(query: str, target: str, threshold: int = 70) -> int:
    """
    Fuzzy match score (0-100).
    Uses rapidfuzz if available (more accurate), falls back to difflib.
    """
    query = normalize_text(query)
    target = normalize_text(target)
    
    if not query or not target:
        return 0
    
    if HAS_RAPIDFUZZ:
        # rapidfuzz token_set_ratio is better for partial matches
        return int(fuzz.token_set_ratio(query, target))
    else:
        # fallback: simple sequence matching
        ratio = SequenceMatcher(None, query, target).ratio()
        return int(ratio * 100)

def search_issues(query: str, issues: List[dict], threshold: int = 70) -> List[Tuple[dict, int, str]]:
    """
    Search issues by keyword, synonym, or fuzzy match.
    Returns: list of (issue, confidence_score, match_reason)
    """
    query = normalize_text(query)
    results = []
    
    for issue in issues:
        max_score = 0
        match_reason = ""
        
        # Check exact keyword match (highest priority)
        for keyword in issue.get('keywords', []):
            if keyword.lower() == query:
                max_score = 100
                match_reason = "exact_keyword"
                break
        
        if max_score == 100:
            results.append((issue, max_score, match_reason))
            continue
        
        # Check partial keyword match
        if not match_reason:
            for keyword in issue.get('keywords', []):
                if query in keyword.lower():
                    max_score = 85
                    match_reason = "partial_keyword"
                    break
        
        # Check synonyms
        if not match_reason:
            for synonym in issue.get('synonyms', []):
                score = fuzzy_match(query, synonym, threshold)
                if score > max_score:
                    max_score = score
                    match_reason = "synonym"
        
        # Check issue name
        if not match_reason:
            score = fuzzy_match(query, issue.get('display_name', ''), threshold)
            if score > max_score:
                max_score = score
                match_reason = "name"
        
        if max_score >= threshold:
            results.append((issue, max_score, match_reason))
    
    # Sort by confidence (descending)
    results.sort(key=lambda x: x[1], reverse=True)
    return results

def search_snippets(query: str, snippets: List[dict], threshold: int = 70) -> List[Tuple[dict, int, str]]:
    """
    Search snippets by trigger, keyword, or text content.
    Returns: list of (snippet, confidence_score, match_reason)
    """
    query = normalize_text(query)
    results = []
    
    for snippet in snippets:
        max_score = 0
        match_reason = ""
        
        # Check trigger exact match (highest priority)
        trigger = snippet.get('trigger', '').lower()
        if trigger == query or trigger == f"{query}":
            max_score = 100
            match_reason = "trigger_exact"
        
        # Check trigger partial match (e.g., "simswap" matches "/simswap_failed")
        if not match_reason:
            if query in trigger:
                max_score = 90
                match_reason = "trigger_partial"
        
        # Check keywords
        if not match_reason:
            for keyword in snippet.get('keywords', []):
                score = fuzzy_match(query, keyword, threshold)
                if score > max_score:
                    max_score = score
                    match_reason = "keyword"
        
        # Check snippet text (lower weight)
        if not match_reason:
            score = fuzzy_match(query, snippet.get('text', ''), threshold)
            if score > max_score and score > 50:
                max_score = int(score * 0.8)  # Reduce weight for text match
                match_reason = "text"
        
        if max_score >= threshold:
            results.append((snippet, max_score, match_reason))
    
    # Sort by confidence (descending)
    results.sort(key=lambda x: x[1], reverse=True)
    return results

def _clean_money(raw: str) -> str:
    """Clean a money string: strip commas, whitespace, currency tags → whole number."""
    if not raw:
        return ''
    raw = re.sub(r'[,\s]', '', raw)          # 1,250.00 → 1250.00
    raw = re.sub(r'^[A-Za-z]{2,4}\.?', '', raw)  # KES500 → 500
    raw = raw.strip()
    # Must start with a digit
    m = re.match(r'(\d+)', raw)              # whole number only, drop decimals
    return m.group(1) if m else ''


def _extract_number(text: str) -> str:
    """Pull the first number (with optional decimals/commas) from a string."""
    m = re.search(r'[\d][\d,]*\.?\d*', text)
    if m:
        return _clean_money(m.group(0))
    return ''


def extract_vetting_fields_from_text(text: str) -> dict:
    """
    Extract vetting fields from a pasted VIEW360 CRM page.

    Extraction strategy (matched to CRM layout):
      TYPE A – Label-pair (label line, value on next non-empty line):
        First Name / Middle Name / Last Name → combined Name
        ID Number → ID
        D.O.B → D.O.B (+ derived YOB)
      TYPE B – Keyword/pattern extraction (same line or next line):
        M-PESA balance (keyword: mpesa / m-pesa)
        Airtime balance (keyword: balance BUT NOT mpesa)
      Extra inline patterns for other fields.

    Returns dict of field label → value (only fields with data).
    """
    extracted = {}

    # Strip zero-width unicode chars that VIEW360 sometimes injects
    text_clean = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', text)
    lines = text_clean.splitlines()
    stripped = [l.strip() for l in lines]

    # ── Labels that use "label on one line, value on a nearby following line" ──
    LABEL_MAP = {
        'first name':      '_first_name',
        'middle name':     '_middle_name',
        'last name':       '_last_name',
        'd.o.b':           'D.O.B',
        'date of birth':   'D.O.B',
        'dob':             'D.O.B',
        'id number':       'ID',
        'national id':     'ID',
        'cbs status':      'CBS Status',
        'account no':      'Account No',
        'activation date': 'Activation Date',
        'kyc compliance':  'KYC Compliance',
        'fraud location':  'Fraud Location',
    }

    # Lines that should never be treated as a value
    SKIP_LINES = set(LABEL_MAP.keys()) | {
        'safaricom logo', 'view360', 'call_centre_agent', 'icon',
        'search', 'customer-subscriptions', 'info icon',
        'key comment', 'no key comment',
        'bio card', 'parent details', 'minor details',
        'quick actions', 'sim swap', 'get puk', 'send sms',
        'change of ownership', 'm-pesa services', 'pre-paid services',
        'hlr', 'supplementary services', 'subscriber identity',
        'subscriber identity and fdns', 'tariff', 'uwezo',
        'data manager', 'data and sms bundles', 'product name',
        'cost (kes)', 'action', 'document type', 'age on the network',
        'gender', 'status reason', 'data manager',
    }

    # ── PASS 1: Line-by-line scan ──
    mpesa_bal = None
    airtime_bal = None

    for i, line in enumerate(stripped):
        low = line.lower()

        # --- TYPE A: Label-pair extraction ---
        if low in LABEL_MAP:
            target_key = LABEL_MAP[low]
            # Look ahead up to 5 lines for the value
            for j in range(i + 1, min(i + 6, len(stripped))):
                candidate = stripped[j]
                if not candidate:
                    continue
                if candidate.lower() in SKIP_LINES:
                    continue
                # Don't overwrite if already captured
                if target_key not in extracted:
                    extracted[target_key] = candidate
                break
            continue

        # --- TYPE B: M-PESA balance (keyword on this line) ---
        if mpesa_bal is None and re.search(r'm[-\s]?pesa', low):
            # Try to extract number from same line
            num = _extract_number(line)
            if num:
                mpesa_bal = num
            else:
                # Check next line for the number
                for j in range(i + 1, min(i + 3, len(stripped))):
                    num = _extract_number(stripped[j])
                    if num:
                        mpesa_bal = num
                        break
            continue

        # --- TYPE B: Airtime balance ---
        #   Must contain "balance" but NOT "mpesa"/"m-pesa"/"fuliza"
        if airtime_bal is None and 'balance' in low:
            if not re.search(r'm[-\s]?pesa|fuliza|m[-\s]?shwari|kcb', low):
                num = _extract_number(line)
                if num:
                    airtime_bal = num
                else:
                    for j in range(i + 1, min(i + 3, len(stripped))):
                        num = _extract_number(stripped[j])
                        if num:
                            airtime_bal = num
                            break

    # Also catch inline "Airtime: 50" / "Main Balance: 10.00"
    if airtime_bal is None:
        m = re.search(r'(?:airtime|main\s+balance|balance\s*\(kes\))\s*[:\-]?\s*([\d,]+\.?\d*)', text_clean, re.I)
        if m and not re.search(r'm[-\s]?pesa', m.group(0), re.I):
            airtime_bal = _clean_money(m.group(1))

    # Also catch inline "M-PESA Balance: 1,250.00" / "MPESA: KES 500"
    if mpesa_bal is None:
        m = re.search(r'm[-\s]?pesa[\w\s]*[:\-]?\s*(?:KES\s*)?([\d,]+\.?\d*)', text_clean, re.I)
        if m:
            mpesa_bal = _clean_money(m.group(1))

    # Store balances
    if mpesa_bal:
        extracted['MPESA'] = mpesa_bal
    if airtime_bal:
        extracted['Airtime'] = airtime_bal

    # ── Combine First / Middle / Last → Name ──
    first = extracted.pop('_first_name', '')
    middle = extracted.pop('_middle_name', '')
    last = extracted.pop('_last_name', '')
    name = ' '.join(p for p in [first, middle, last] if p)
    if name:
        extracted['Name'] = name

    # ── Derive YOB from D.O.B ──
    dob = extracted.get('D.O.B', '')
    if dob:
        ym = re.search(r'(\d{4})', dob)
        if ym:
            extracted['YOB'] = ym.group(1)

    # ── Inline special patterns ──
    # MSISDN from "Search Results of : 74500957"
    m = re.search(r'Search\s+Results?\s+of\s*:\s*(\d+)', text_clean, re.I)
    if m and 'MSISDN' not in extracted:
        extracted['MSISDN'] = m.group(1)

    # Serial No is always entered manually — never extracted from CRM

    # ── Fallback inline "Label: Value" patterns (financial / other pages) ──
    inline_patterns = [
        ('Name',               r'(?:subscriber name|sub name)\s*:\s*(.+)'),
        ('ID',                 r'(?:national id|id no)\s*:\s*(\d[\d\s]*)'),
        ('YOB',                r'(?:yob|year of birth)\s*:\s*(\d{4})'),
        ('MSISDN',             r'(?:msisdn)\s*:\s*(\+?[\d\s-]+)'),
        ('Contact No',         r'(?:contact\s*(?:no|number))\s*:\s*(\+?[\d\s-]+)'),
        ('Amount',             r'(?:amount|topup\s*amount)\s*:\s*([\d,.\s]+)'),
        ('MPESA',              r'(?:m-?pesa\s*bal(?:ance)?)\s*:\s*([\d,.\s]+)'),
        ('Airtime',            r'(?:airtime\s*bal(?:ance)?)\s*:\s*([\d,.\s]+)'),
        ('Fuliza Limit',       r'(?:fuliza\s*(?:limit)?)\s*:\s*([\d,.\s]+)'),
        ('M-Shwari Limit',     r'(?:m-?shwari\s*(?:limit)?)\s*:\s*([\d,.\s]+)'),
        ('KCB M-PESA Limit',   r'(?:kcb\s*m-?pesa\s*(?:limit)?)\s*:\s*([\d,.\s]+)'),
        ('2FDNs',              r'(?:2\s*fdns?|frequently\s*dialed)\s*:\s*(.+)'),
        ('2Txn',               r'(?:2\s*txn|last\s*2\s*txn)\s*:\s*(.+)'),
        ('Registration Date',  r'(?:registration\s*date|reg\s*date)\s*:\s*(.+)'),
        ('Storo Target',       r'(?:storo\s*(?:target)?)\s*:\s*(.+)'),
        ('Last Bundle Purchase', r'(?:last\s*bundle\s*(?:purchase)?|bundle\s*purchase)\s*:\s*(.+)'),
    ]

    # Labels whose values should be cleaned as money (whole numbers, no commas/decimals)
    _MONEY_LABELS = {'MPESA', 'Airtime', 'Amount', 'Fuliza Limit', 'M-Shwari Limit', 'KCB M-PESA Limit'}

    for label, pattern in inline_patterns:
        if label not in extracted:
            m = re.search(pattern, text_clean, re.I)
            if m:
                val = m.group(1).strip()
                if val and val.lower() not in ('', '-', 'n/a', 'nil', 'none'):
                    if label in _MONEY_LABELS:
                        val = _clean_money(val)
                    if val:
                        extracted[label] = val

    # ── Filter out empty / useless values ──
    skip_vals = {'', '-', 'N/A', 'n/a', 'nil', 'none', 'No Data', 'no data'}
    extracted = {k: v for k, v in extracted.items()
                 if v and v.strip() and v.strip() not in skip_vals}

    return extracted


def extract_sdp_codes(text: str) -> List[str]:
    """
    Extract SDP service codes from a pasted CRM subscriptions screen.

    Looks for numeric codes (4-6 digits) at the start of product names, e.g.
      23882_GamesVille_Ksh15_PerDay  →  23882
      20851_Shupavu291 for Ksh 4 per day  →  20851

    Also picks up standalone codes on their own line.
    Returns a deduplicated list of code strings in order of appearance.
    """
    codes = []
    seen = set()
    for m in re.finditer(r'\b(\d{4,6})[_\s]', text):
        code = m.group(1)
        if code not in seen:
            seen.add(code)
            codes.append(code)
    return codes
