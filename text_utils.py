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

def extract_vetting_fields_from_text(text: str) -> dict:
    """
    Extract vetting fields from unstructured pasted text using regex patterns.
    Returns a dict of extracted field names and values.
    """
    extracted = {}
    
    # Define patterns for common vetting fields
    patterns = {
        'name': r'(?:name|jina|sub):\s*([^\n]+)',
        'id': r'(?:id|ID):\s*(\d+)',
        'yob': r'(?:yob|DOB|dob):\s*(\d{4})',
        'msisdn': r'(?:msisdn|phone|mobile|number):\s*(\+?254\d{9}|\d{9,10})',
        'serial_no': r'(?:serial|serial no|sn|card):\s*(\d+)',
        'contact_no': r'(?:contact|contact no):\s*(\d+)',
        'mpesa_balance': r'(?:mpesa bal|m-pesa balance|balance):\s*([\d,.]+)',
        'airtime_balance': r'(?:airtime bal|airtime balance):\s*([\d,.]+)',
        'fuliza_limit': r'(?:fuliza|fuliza limit):\s*([\d,.]+)',
        'mshwari_limit': r'(?:m-shwari|mshwari|mshwari limit):\s*([\d,.]+)',
        'kcb_limit': r'(?:kcb|kcb limit|kcb m-pesa):\s*([\d,.]+)',
        'registration_date': r'(?:registration|reg date|registered):\s*([^\n]+)',
        'last_bundle_purchase': r'(?:bundle|last bundle):\s*([^\n]+)',
    }
    
    text_lower = text.lower()
    for field, pattern in patterns.items():
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            extracted[field] = match.group(1).strip()
    
    return extracted
