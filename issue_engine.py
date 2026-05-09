"""
Agent Helper — Issue Engine
============================
Classifies agent-entered queries against the configured issue catalogue
using keyword, synonym, and fuzzy matching.

Architectural note
------------------
This module is intentionally free of any Tkinter / UI imports.  It operates
solely on plain Python dicts and strings, making it directly usable by a
future REST API or CRM webhook adapter without modification.
"""

import logging
from typing import Dict, List, Optional

from text_utils import normalize_text, search_issues

_log = logging.getLogger(__name__)


class IssueEngine:
    """
    Classify customer issues from free-text queries against a loaded catalogue.

    All methods are pure (no side-effects on external state) and UI-agnostic.
    """

    def __init__(self, issues_data: Dict) -> None:
        """
        Initialise the engine with pre-loaded issues data.

        Args:
            issues_data: Dict with an ``"issues"`` key containing a list of
                         issue definition dicts.
        """
        self.issues: List[Dict] = issues_data.get("issues", [])
        _log.info("IssueEngine: loaded %d issue definitions.", len(self.issues))

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def classify(self, query: str, threshold: int = 70) -> Optional[Dict]:
        """
        Classify *query* and return the single best-matching issue.

        Args:
            query:     Agent's free-text description of the customer problem.
            threshold: Minimum fuzzy-match score (0–100) for a result to
                       be considered a match.

        Returns:
            Dict with keys ``issue_code``, ``display_name``, ``category``,
            ``confidence``, ``matched_terms``, ``requires_vetting``,
            ``vetting_fields``, ``resolution_group``, ``snippet_group``,
            and ``raw_issue``; or ``None`` if no match meets the threshold.
        """
        if not query or not query.strip():
            return None

        results = search_issues(query, self.issues, threshold)
        if not results:
            _log.debug("IssueEngine.classify: no match found above threshold %d.", threshold)
            return None

        issue, confidence, match_reason = results[0]
        _log.debug(
            "IssueEngine.classify: matched '%s' (confidence=%d, reason=%s).",
            issue.get("issue_code"),
            confidence,
            match_reason,
        )

        return {
            "issue_code":       issue.get("issue_code"),
            "display_name":     issue.get("display_name"),
            "category":         issue.get("category"),
            "confidence":       confidence,
            "matched_terms":    match_reason,
            "requires_vetting": issue.get("requires_vetting", False),
            "vetting_fields":   issue.get("vetting_fields", []),
            "resolution_group": issue.get("valid_resolutions", []),
            "snippet_group":    issue.get("snippets", []),
            "raw_issue":        issue,
        }

    def get_top_matches(
        self, query: str, limit: int = 3, threshold: int = 70
    ) -> List[Dict]:
        """
        Return the top *limit* matching issues for *query*.

        Args:
            query:     Agent's free-text input.
            limit:     Maximum number of results to return.
            threshold: Minimum fuzzy-match score for inclusion.

        Returns:
            List of dicts, each with keys ``issue_code``, ``display_name``,
            ``category``, ``confidence``, ``matched_terms``, and ``raw_issue``.
            Empty list when no matches are found.
        """
        if not query or not query.strip():
            return []

        results = search_issues(query, self.issues, threshold)
        return [
            {
                "issue_code":    issue.get("issue_code"),
                "display_name":  issue.get("display_name"),
                "category":      issue.get("category"),
                "confidence":    confidence,
                "matched_terms": match_reason,
                "raw_issue":     issue,
            }
            for issue, confidence, match_reason in results[:limit]
        ]

    def get_categories(self) -> List[str]:
        """
        Return a sorted list of unique issue category labels.

        Returns:
            Sorted list of category strings; excludes ``None`` values.
        """
        categories = {
            issue.get("category")
            for issue in self.issues
            if issue.get("category")
        }
        return sorted(categories)

    def get_issues_by_category(self, category: str) -> List[Dict]:
        """
        Return all issues belonging to *category*.

        Args:
            category: Exact category label to filter by.

        Returns:
            List of matching issue dicts (may be empty).
        """
        return [
            issue
            for issue in self.issues
            if issue.get("category") == category
        ]
