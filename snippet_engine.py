"""
Agent Helper — Snippet Engine
==============================
Fast retrieval and lifecycle management of quick-response snippets.

Architectural note
------------------
This module is entirely free of Tkinter / UI imports.  It operates on plain
Python dicts and strings, making it safe to consume from a REST API or
CRM webhook adapter in the future without any changes here.
"""

import logging
from typing import Dict, List, Optional

from text_utils import search_snippets

_log = logging.getLogger(__name__)


class SnippetEngine:
    """
    Manage and search the library of quick-response snippets.

    All operations are UI-agnostic and side-effect-free with respect to
    external state (writes only mutate the in-memory ``snippets`` list;
    persistence is the caller's responsibility).
    """

    def __init__(self, snippets_data: Dict) -> None:
        """
        Initialise the engine with pre-loaded snippets data.

        Args:
            snippets_data: Dict with a ``"snippets"`` key containing a list
                           of snippet definition dicts.
        """
        self.snippets: List[Dict] = snippets_data.get("snippets", [])
        _log.info("SnippetEngine: loaded %d snippet(s).", len(self.snippets))

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self, query: str, limit: int = 5, threshold: int = 70
    ) -> List[Dict]:
        """
        Search for snippets matching *query* by trigger, keyword, or body text.

        Args:
            query:     Agent's free-text or trigger input (e.g. ``"/simswap"``).
            limit:     Maximum number of results to return.
            threshold: Minimum fuzzy-match score (0–100) for inclusion.

        Returns:
            List of dicts (up to *limit*), each containing ``snippet_code``,
            ``trigger``, ``category``, ``text``, ``confidence``, and
            ``match_reason``.  Empty list when no matches meet the threshold.
        """
        if not query or not query.strip():
            return []

        results = search_snippets(query, self.snippets, threshold)
        return [
            {
                "snippet_code": snippet.get("snippet_code"),
                "trigger":      snippet.get("trigger"),
                "category":     snippet.get("category"),
                "text":         snippet.get("text"),
                "confidence":   confidence,
                "match_reason": match_reason,
            }
            for snippet, confidence, match_reason in results[:limit]
        ]

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_by_code(self, snippet_code: str) -> Optional[Dict]:
        """
        Retrieve a snippet by its unique code.

        Args:
            snippet_code: Unique identifier, e.g. ``"SIMSWAP_PASS"``.

        Returns:
            Snippet dict, or ``None`` if not found.
        """
        for snippet in self.snippets:
            if snippet.get("snippet_code") == snippet_code:
                return snippet
        return None

    def get_by_trigger(self, trigger: str) -> Optional[Dict]:
        """
        Retrieve a snippet by its trigger string (case-insensitive).

        Args:
            trigger: Trigger value, e.g. ``"/simswap"``.

        Returns:
            Snippet dict, or ``None`` if not found.
        """
        trigger_lower = trigger.lower()
        for snippet in self.snippets:
            if snippet.get("trigger", "").lower() == trigger_lower:
                return snippet
        return None

    def get_by_category(self, category: str) -> List[Dict]:
        """
        Return all snippets belonging to *category*.

        Args:
            category: Exact category label to filter by.

        Returns:
            List of matching snippet dicts (may be empty).
        """
        return [s for s in self.snippets if s.get("category") == category]

    def get_categories(self) -> List[str]:
        """
        Return a sorted list of unique snippet category labels.

        Returns:
            Sorted list of category strings; excludes ``None`` / empty values.
        """
        categories = {
            s.get("category")
            for s in self.snippets
            if s.get("category")
        }
        return sorted(categories)

    # ------------------------------------------------------------------
    # Mutation (in-memory; caller must persist via DataLoader)
    # ------------------------------------------------------------------

    def add_snippet(
        self,
        code: str,
        trigger: str,
        category: str,
        text: str,
        keywords: Optional[List[str]] = None,
    ) -> bool:
        """
        Add a new snippet to the in-memory collection.

        Args:
            code:     Unique snippet code.
            trigger:  Trigger string (e.g. ``"/greeting"``).
            category: Category label.
            text:     Snippet body text.
            keywords: Optional list of search keywords.

        Returns:
            ``True`` on success; ``False`` if *code* already exists.
        """
        if self.get_by_code(code):
            _log.warning("SnippetEngine.add_snippet: code '%s' already exists.", code)
            return False

        self.snippets.append(
            {
                "snippet_code": code,
                "trigger":      trigger,
                "category":     category,
                "text":         text,
                "keywords":     keywords or [],
            }
        )
        _log.info("SnippetEngine: added snippet '%s'.", code)
        return True

    def update_snippet(self, code: str, text: str) -> bool:
        """
        Update the body text of an existing snippet.

        Args:
            code: Target snippet code.
            text: New body text.

        Returns:
            ``True`` on success; ``False`` if *code* is not found.
        """
        for snippet in self.snippets:
            if snippet.get("snippet_code") == code:
                snippet["text"] = text
                _log.info("SnippetEngine: updated snippet '%s'.", code)
                return True
        _log.warning("SnippetEngine.update_snippet: code '%s' not found.", code)
        return False

    def delete_snippet(self, code: str) -> bool:
        """
        Remove a snippet from the in-memory collection by code.

        Args:
            code: Target snippet code.

        Returns:
            ``True`` on success; ``False`` if *code* is not found.
        """
        for i, snippet in enumerate(self.snippets):
            if snippet.get("snippet_code") == code:
                self.snippets.pop(i)
                _log.info("SnippetEngine: deleted snippet '%s'.", code)
                return True
        _log.warning("SnippetEngine.delete_snippet: code '%s' not found.", code)
        return False
