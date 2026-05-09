"""
Agent Helper — Text Utilities
==============================
Provides text normalisation, fuzzy matching, issue/snippet search ranking,
and structured extraction of vetting fields from raw CRM screen text.

Security note
-------------
None of the functions in this module write PII to logs.  Extraction
results are returned to callers; logging is limited to structural events
(e.g. parse errors, missing optional dependencies).
"""

import logging
import re
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

_log = logging.getLogger(__name__)

try:
    from rapidfuzz import fuzz as _fuzz
    _HAS_RAPIDFUZZ = True
except ImportError:
    _HAS_RAPIDFUZZ = False
    _log.warning(
        "text_utils: rapidfuzz not installed — falling back to difflib. "
        "Install with: pip install rapidfuzz"
    )

# ---------------------------------------------------------------------------
# Text normalisation
# ---------------------------------------------------------------------------


def normalize_text(text: str) -> str:
    """
    Normalise *text* for comparison: lowercase, strip, collapse whitespace.

    Args:
        text: Raw input string.

    Returns:
        Lowercase, single-space-separated string.
    """
    return re.sub(r"\s+", " ", text.lower().strip())


# ---------------------------------------------------------------------------
# Fuzzy matching
# ---------------------------------------------------------------------------


def fuzzy_match(query: str, target: str, threshold: int = 70) -> int:
    """
    Return a similarity score (0–100) between *query* and *target*.

    Uses ``rapidfuzz.fuzz.token_set_ratio`` when available for superior
    partial-match accuracy; falls back to ``difflib.SequenceMatcher``.

    Args:
        query:     Search term (normalised internally).
        target:    Comparison string (normalised internally).
        threshold: Minimum score considered a match (informational only here).

    Returns:
        Integer similarity score in the range [0, 100].
    """
    query = normalize_text(query)
    target = normalize_text(target)

    if not query or not target:
        return 0

    if _HAS_RAPIDFUZZ:
        return int(_fuzz.token_set_ratio(query, target))

    ratio = SequenceMatcher(None, query, target).ratio()
    return int(ratio * 100)


# ---------------------------------------------------------------------------
# Search helpers
# ---------------------------------------------------------------------------


def search_issues(
    query: str,
    issues: List[Dict],
    threshold: int = 70,
) -> List[Tuple[Dict, int, str]]:
    """
    Rank *issues* against *query* using keyword, synonym, and fuzzy matching.

    Matching priority (highest → lowest):
      1. Exact keyword match          → score 100
      2. Partial keyword match        → score 85
      3. Fuzzy synonym match          → score from fuzzy_match()
      4. Fuzzy display-name match     → score from fuzzy_match()

    Args:
        query:     Agent's free-text search input.
        issues:    List of issue dicts (each with ``keywords``, ``synonyms``,
                   ``display_name`` keys).
        threshold: Minimum score for inclusion in results.

    Returns:
        List of ``(issue_dict, score, match_reason)`` tuples, sorted by score
        descending.
    """
    query = normalize_text(query)
    results: List[Tuple[Dict, int, str]] = []

    for issue in issues:
        max_score = 0
        match_reason = ""

        for keyword in issue.get("keywords", []):
            if keyword.lower() == query:
                max_score = 100
                match_reason = "exact_keyword"
                break

        if max_score == 100:
            results.append((issue, max_score, match_reason))
            continue

        if not match_reason:
            for keyword in issue.get("keywords", []):
                if query in keyword.lower():
                    max_score = 85
                    match_reason = "partial_keyword"
                    break

        if not match_reason:
            for synonym in issue.get("synonyms", []):
                score = fuzzy_match(query, synonym, threshold)
                if score > max_score:
                    max_score = score
                    match_reason = "synonym"

        if not match_reason:
            score = fuzzy_match(query, issue.get("display_name", ""), threshold)
            if score > max_score:
                max_score = score
                match_reason = "name"

        if max_score >= threshold:
            results.append((issue, max_score, match_reason))

    results.sort(key=lambda x: x[1], reverse=True)
    return results


def search_snippets(
    query: str,
    snippets: List[Dict],
    threshold: int = 70,
) -> List[Tuple[Dict, int, str]]:
    """
    Rank *snippets* against *query* using trigger, keyword, and text matching.

    Matching priority (highest → lowest):
      1. Exact trigger match          → score 100
      2. Partial trigger match        → score 90
      3. Fuzzy keyword match          → score from fuzzy_match()
      4. Fuzzy text-body match        → score × 0.8 (down-weighted)

    Args:
        query:     Agent's free-text or trigger input.
        snippets:  List of snippet dicts (each with ``trigger``, ``keywords``,
                   ``text`` keys).
        threshold: Minimum score for inclusion in results.

    Returns:
        List of ``(snippet_dict, score, match_reason)`` tuples, sorted by
        score descending.
    """
    query = normalize_text(query)
    results: List[Tuple[Dict, int, str]] = []

    for snippet in snippets:
        max_score = 0
        match_reason = ""

        trigger = snippet.get("trigger", "").lower()
        if trigger == query:
            max_score = 100
            match_reason = "trigger_exact"

        if not match_reason and query in trigger:
            max_score = 90
            match_reason = "trigger_partial"

        if not match_reason:
            for keyword in snippet.get("keywords", []):
                score = fuzzy_match(query, keyword, threshold)
                if score > max_score:
                    max_score = score
                    match_reason = "keyword"

        if not match_reason:
            score = fuzzy_match(query, snippet.get("text", ""), threshold)
            if score > max_score and score > 50:
                max_score = int(score * 0.8)
                match_reason = "text"

        if max_score >= threshold:
            results.append((snippet, max_score, match_reason))

    results.sort(key=lambda x: x[1], reverse=True)
    return results


# ---------------------------------------------------------------------------
# Strict-typing helpers (Sprint 2)
# ---------------------------------------------------------------------------


def _validate_name(raw: str) -> str:
    """
    Validate and clean a customer name string.

    Acceptance criteria:
      - 2–4 space-separated words.
      - Letters only.
    """
    if not raw:
        return ""
    # Only allow letters and spaces
    cleaned = re.sub(r"[^A-Za-z\s]", " ", raw).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    
    # Remove 'NA' or 'na' used as fillers
    words = [w for w in cleaned.split() if w.upper() != 'NA']
    
    if len(words) < 2 or len(words) > 4:
        return ""
    
    return " ".join(words)


def _validate_numeric_field(raw: str) -> str:
    """
    Strip all non-digit characters from *raw* and return the result.

    Args:
        raw: Candidate numeric string (may contain commas, spaces, etc.).

    Returns:
        Digits-only string, or empty string if no digits are found.
    """
    if not raw:
        return ""
    digits = re.sub(r"[^\d]", "", raw)
    return digits if digits else ""


def _clean_money(raw: str) -> str:
    """
    Normalise a monetary string to a whole-number digit string.

    Removes commas, whitespace, currency prefixes (e.g. ``KES``), and
    decimal fractions.

    Args:
        raw: Raw monetary string, e.g. ``"KES 1,250.50"``.

    Returns:
        Whole-number string, e.g. ``"1250"``, or empty string on failure.
    """
    if not raw:
        return ""
    raw = re.sub(r"[,\s]", "", raw)
    raw = re.sub(r"^[A-Za-z]{2,4}\.?", "", raw)
    raw = raw.strip()
    match = re.match(r"(\d+)", raw)
    return match.group(1) if match else ""


def _extract_number(text: str) -> str:
    """
    Pull the first number (with optional commas/decimals) from *text*.

    Args:
        text: Input string that may contain a number.

    Returns:
        Cleaned whole-number string, or empty string if none found.
    """
    match = re.search(r"[\d][\d,]*\.?\d*", text)
    if match:
        return _clean_money(match.group(0))
    return ""


# ---------------------------------------------------------------------------
# Primary extraction function
# ---------------------------------------------------------------------------

# Labels whose raw values must be cleaned as money (whole numbers, no commas)
_MONEY_LABELS: frozenset = frozenset(
    {"MPESA", "Airtime", "Amount", "Fuliza Limit", "M-Shwari Limit", "KCB M-PESA Limit"}
)

# Numeric-only fields that must survive the strict-typing pass
_NUMERIC_FIELDS: frozenset = frozenset(
    {"MPESA", "Airtime", "Amount", "Fuliza Limit", "M-Shwari Limit", "KCB M-PESA Limit"}
)

# Label → internal VettingEngine key mapping for line-pair extraction
_LABEL_MAP: Dict[str, str] = {
    "first name":      "_first_name",
    "middle name":     "_middle_name",
    "last name":       "_last_name",
    "d.o.b":           "D.O.B",
    "date of birth":   "D.O.B",
    "dob":             "D.O.B",
    "id number":       "ID",
    "national id":     "ID",
    "cbs status":      "CBS Status",
    "account no":      "Account No",
    "activation date": "Activation Date",
    "kyc compliance":  "KYC Compliance",
    "fraud location":  "Fraud Location",
}

# Lines that must never be treated as a field value
_SKIP_LINES: frozenset = frozenset(_LABEL_MAP.keys()) | frozenset({
    "safaricom logo", "view360", "call_centre_agent", "icon",
    "search", "customer-subscriptions", "info icon",
    "key comment", "no key comment",
    "bio card", "parent details", "minor details",
    "quick actions", "sim swap", "get puk", "send sms",
    "change of ownership", "m-pesa services", "pre-paid services",
    "hlr", "supplementary services", "subscriber identity",
    "subscriber identity and fdns", "tariff", "uwezo",
    "data manager", "data and sms bundles", "product name",
    "cost (kes)", "action", "document type", "age on the network",
    "gender", "status reason",
})

_INLINE_PATTERNS: List[Tuple[str, str]] = [
    ("Name",                r"(?:subscriber name|sub name)\s*:\s*(.+)"),
    ("ID",                  r"(?:national id|id no)\s*:\s*(\d[\d\s]*)"),
    ("YOB",                 r"(?:yob|year of birth)\s*:\s*(\d{4})"),
    ("MSISDN",              r"(?:msisdn)\s*:\s*(\+?[\d\s-]+)"),
    ("Contact No",          r"(?:contact\s*(?:no|number))\s*:\s*(\+?[\d\s-]+)"),
    ("Amount",              r"(?:amount|topup\s*amount)\s*:\s*([\d,.\s]+)"),
    ("MPESA",               r"(?:m-?pesa\s*bal(?:ance)?)\s*:\s*([\d,.\s]+)"),
    ("Airtime",             r"(?:airtime\s*bal(?:ance)?)\s*:\s*([\d,.\s]+)"),
    ("Fuliza Limit",        r"(?:fuliza\s*(?:limit)?)\s*:\s*([\d,.\s]+)"),
]

_SKIP_VALUES: frozenset = frozenset({"", "-", "N/A", "n/a", "nil", "none", "No Data", "no data"})


def extract_vetting_fields_from_text(text: str) -> Dict[str, str]:
    """
    Extract vetting fields from a pasted VIEW360 CRM screen.

    Extraction strategy
    -------------------
    **Pass 1 — Line-by-line scan**
      - Type A (label-pair): label on one line, value on the next non-empty
        line (looks ahead up to 5 lines).  Captures Name parts, ID, D.O.B,
        CBS Status, and other structured fields.
      - Type B (keyword inline): M-PESA and Airtime balances, where the
        keyword and amount often appear on the same line or adjacent lines.

    **Pass 2 — Inline regex**
      Fallback ``Label: Value`` patterns for financial pages and non-standard
      CRM layouts.

    **Post-processing**
      - Combines First / Middle / Last Name parts.
      - Derives YOB from D.O.B.
      - Strict-type validation (name words, digit-only fields, YOB range).
      - Removes empty / placeholder values.

    Security note: this function returns extracted data; it does **not** log
    any of the extracted field values.

    Args:
        text: Raw clipboard text from the CRM screen.

    Returns:
        Dict mapping VettingEngine field labels to extracted string values.
        Only fields with non-empty, validated data are included.
    """
    extracted: Dict[str, str] = {}

    # Strip zero-width Unicode characters that VIEW360 sometimes injects
    text_clean = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
    lines = text_clean.splitlines()
    stripped = [line.strip() for line in lines]

    # ── Pass 1: Line-by-line scan ─────────────────────────────────────────
    mpesa_bal: Optional[str] = None
    airtime_bal: Optional[str] = None

    for i, line in enumerate(stripped):
        low = line.lower()

        # Type A: label-pair extraction
        if low in _LABEL_MAP:
            target_key = _LABEL_MAP[low]
            for j in range(i + 1, min(i + 6, len(stripped))):
                candidate = stripped[j]
                if not candidate:
                    continue
                if candidate.lower() in _SKIP_LINES:
                    continue
                if target_key not in extracted:
                    extracted[target_key] = candidate
                break
            continue

        # Type B: M-PESA balance
        if mpesa_bal is None and re.search(r"m[-\s]?pesa", low):
            num = _extract_number(line)
            if num:
                mpesa_bal = num
            else:
                for j in range(i + 1, min(i + 3, len(stripped))):
                    num = _extract_number(stripped[j])
                    if num:
                        mpesa_bal = num
                        break
            continue

        # Type B: Airtime balance (must not be M-PESA / Fuliza / M-Shwari / KCB)
        if airtime_bal is None and "balance" in low:
            if not re.search(r"m[-\s]?pesa|fuliza|m[-\s]?shwari|kcb", low):
                num = _extract_number(line)
                if num:
                    airtime_bal = num
                else:
                    for j in range(i + 1, min(i + 3, len(stripped))):
                        num = _extract_number(stripped[j])
                        if num:
                            airtime_bal = num
                            break

    # Inline airtime fallback
    if airtime_bal is None:
        match = re.search(
            r"(?:airtime|main\s+balance|balance\s*\(kes\))\s*[:\-]?\s*([\d,]+\.?\d*)",
            text_clean,
            re.I,
        )
        if match and not re.search(r"m[-\s]?pesa", match.group(0), re.I):
            airtime_bal = _clean_money(match.group(1))

    # Inline M-PESA fallback
    if mpesa_bal is None:
        match = re.search(
            r"m[-\s]?pesa[\w\s]*[:\-]?\s*(?:KES\s*)?([\d,]+\.?\d*)",
            text_clean,
            re.I,
        )
        if match:
            mpesa_bal = _clean_money(match.group(1))

    if mpesa_bal:
        extracted["MPESA"] = mpesa_bal
    if airtime_bal:
        extracted["Airtime"] = airtime_bal

    # ── Combine name parts ────────────────────────────────────────────────
    first = extracted.pop("_first_name", "")
    middle = extracted.pop("_middle_name", "")
    last = extracted.pop("_last_name", "")
    name = " ".join(part for part in [first, middle, last] if part)
    if name:
        extracted["Name"] = name

    # ── Derive YOB from D.O.B ─────────────────────────────────────────────
    dob = extracted.get("D.O.B", "")
    if dob:
        year_match = re.search(r"(\d{4})", dob)
        if year_match:
            extracted["YOB"] = year_match.group(1)

    # ── MSISDN from "Search Results of : <number>" ────────────────────────
    msisdn_match = re.search(
        r"Search\s+Results?\s+of\s*:\s*(\d+)", text_clean, re.I
    )
    if msisdn_match and "MSISDN" not in extracted:
        extracted["MSISDN"] = msisdn_match.group(1)

    # ── Pass 2: Inline Label: Value fallback patterns ─────────────────────
    for label, pattern in _INLINE_PATTERNS:
        if label not in extracted:
            match = re.search(pattern, text_clean, re.I)
            if match:
                val = match.group(1).strip()
                if val and val.lower() not in ("", "-", "n/a", "nil", "none"):
                    if label in _MONEY_LABELS:
                        val = _clean_money(val)
                    if val:
                        extracted[label] = val

    # ── Strip empty / placeholder values ──────────────────────────────────
    extracted = {
        k: v
        for k, v in extracted.items()
        if v and v.strip() and v.strip() not in _SKIP_VALUES
    }

    # ── Strict-typing pass ────────────────────────────────────────────────
    if "Name" in extracted:
        validated = _validate_name(extracted["Name"])
        if validated:
            extracted["Name"] = validated
        else:
            del extracted["Name"]

    if "ID" in extracted:
        validated = _validate_numeric_field(extracted["ID"])
        if validated:
            extracted["ID"] = validated
        else:
            del extracted["ID"]

    if "YOB" in extracted:
        yob_clean = _validate_numeric_field(extracted["YOB"])
        if yob_clean and re.fullmatch(r"\d{4}", yob_clean):
            yr = int(yob_clean)
            if 1900 <= yr <= 2030:
                extracted["YOB"] = yob_clean
            else:
                del extracted["YOB"]
        else:
            del extracted["YOB"]

    for field in _NUMERIC_FIELDS:
        if field in extracted:
            validated = _validate_numeric_field(extracted[field])
            if validated:
                extracted[field] = validated
            else:
                del extracted[field]

    _log.debug(
        "extract_vetting_fields_from_text: extracted %d field(s).", len(extracted)
    )
    return extracted


# ---------------------------------------------------------------------------
# SDP / Skiza extraction
# ---------------------------------------------------------------------------


def extract_sdp_codes(text: str, strict_prs: bool = False) -> List[str]:
    """
    Extract SDP service codes from a pasted CRM subscriptions screen.

    Matches numeric codes at the start of product name tokens, e.g.::

        23882_GamesVille_Ksh15_PerDay  →  "23882"

    Args:
        text:       Raw CRM subscriptions screen text.
        strict_prs: When ``True`` (PRS issues), only 5–6 digit codes are
                    accepted.  When ``False`` (Skiza/general), 4–6 digit codes
                    are accepted.

    Returns:
        Deduplicated list of code strings in order of first appearance.
    """
    min_digits = 5 if strict_prs else 4
    pattern = rf"\b(\d{{{min_digits},6}})[_\s]"
    codes: List[str] = []
    seen: set = set()
    for match in re.finditer(pattern, text):
        code = match.group(1)
        if code not in seen:
            seen.add(code)
            codes.append(code)
    return codes


def extract_skiza_tune_name(text: str) -> Optional[str]:
    """
    Extract the Skiza tune name from CRM subscription text.

    Attempts two patterns in order:

    1. ``Skiza: <Name>`` / ``Skiza Tune - <Name>`` / ``Skiza <Name>``
    2. ``<code>_<TuneName>_Ksh<N>`` structured format

    Args:
        text: Raw CRM subscription text.

    Returns:
        Tune name string (≥ 3 characters), or ``None`` if not found.
    """
    match = re.search(
        r"[Ss]kiza\s*(?:[Tt]une)?\s*[:\-]?\s*(.+?)(?:\s*Ksh|\s*per|\s*$)",
        text,
        re.I | re.M,
    )
    if match:
        name = match.group(1).strip()
        if len(name) >= 3:
            return name

    match = re.search(
        r"\b\d{4,6}[_\s]+(.+?)(?:_?Ksh|_?per|\s*$)",
        text,
        re.I | re.M,
    )
    if match:
        name = match.group(1).replace("_", " ").strip()
        if len(name) >= 3:
            return name

    return None
