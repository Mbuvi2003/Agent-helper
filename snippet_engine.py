"""
Snippet Engine for Agent Helper.
Fast retrieval and management of quick response snippets.
"""

from typing import Dict, List, Optional, Tuple
from text_utils import search_snippets, normalize_text

class SnippetEngine:
    """Manage quick response snippets."""
    
    def __init__(self, snippets_data: Dict):
        """Initialize with snippets data."""
        self.snippets = snippets_data.get('snippets', [])
    
    def search(self, query: str, limit: int = 5, threshold: int = 70) -> List[Dict]:
        """
        Fast search for snippets by trigger, keyword, or text.
        Returns top N matching snippets.
        """
        if not query or not query.strip():
            return []
        
        results = search_snippets(query, self.snippets, threshold)
        
        return [
            {
                'snippet_code': snippet.get('snippet_code'),
                'trigger': snippet.get('trigger'),
                'category': snippet.get('category'),
                'text': snippet.get('text'),
                'confidence': confidence,
                'match_reason': match_reason
            }
            for snippet, confidence, match_reason in results[:limit]
        ]
    
    def get_by_code(self, snippet_code: str) -> Optional[Dict]:
        """Get snippet by code."""
        for snippet in self.snippets:
            if snippet.get('snippet_code') == snippet_code:
                return snippet
        return None
    
    def get_by_trigger(self, trigger: str) -> Optional[Dict]:
        """Get snippet by trigger (e.g., /simswap)."""
        trigger = trigger.lower()
        for snippet in self.snippets:
            if snippet.get('trigger', '').lower() == trigger:
                return snippet
        return None
    
    def get_by_category(self, category: str) -> List[Dict]:
        """Get all snippets in a category."""
        return [s for s in self.snippets if s.get('category') == category]
    
    def get_categories(self) -> List[str]:
        """Get all snippet categories."""
        categories = set(s.get('category') for s in self.snippets if s.get('category'))
        return sorted(list(categories))
    
    def add_snippet(self, code: str, trigger: str, category: str, text: str, keywords: List[str] = None) -> bool:
        """Add a new snippet."""
        if self.get_by_code(code):
            return False  # Code already exists
        
        new_snippet = {
            'snippet_code': code,
            'trigger': trigger,
            'category': category,
            'text': text,
            'keywords': keywords or []
        }
        self.snippets.append(new_snippet)
        return True
    
    def update_snippet(self, code: str, text: str) -> bool:
        """Update existing snippet text."""
        for snippet in self.snippets:
            if snippet.get('snippet_code') == code:
                snippet['text'] = text
                return True
        return False
    
    def delete_snippet(self, code: str) -> bool:
        """Delete a snippet by code."""
        for i, snippet in enumerate(self.snippets):
            if snippet.get('snippet_code') == code:
                self.snippets.pop(i)
                return True
        return False
