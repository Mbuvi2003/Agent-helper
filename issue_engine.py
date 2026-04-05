"""
Issue Engine for Agent Helper.
Identifies the customer issue using keyword matching, synonyms, and fuzzy matching.
"""

from typing import Dict, List, Optional, Tuple
from text_utils import search_issues, normalize_text

class IssueEngine:
    """Identify and classify customer issues."""
    
    def __init__(self, issues_data: Dict):
        """Initialize with issues data."""
        self.issues = issues_data.get('issues', [])
    
    def classify(self, query: str, threshold: int = 70) -> Optional[Dict]:
        """
        Classify the provided query to an issue.
        Returns the best matching issue with confidence score.
        """
        if not query or not query.strip():
            return None
        
        results = search_issues(query, self.issues, threshold)
        
        if not results:
            return None
        
        # Take the top result
        issue, confidence, match_reason = results[0]
        
        return {
            'issue_code': issue.get('issue_code'),
            'display_name': issue.get('display_name'),
            'category': issue.get('category'),
            'confidence': confidence,
            'matched_terms': match_reason,
            'requires_vetting': issue.get('requires_vetting', False),
            'vetting_fields': issue.get('vetting_fields', []),
            'resolution_group': issue.get('valid_resolutions', []),
            'snippet_group': issue.get('snippets', []),
            'raw_issue': issue
        }
    
    def get_top_matches(self, query: str, limit: int = 3, threshold: int = 70) -> List[Dict]:
        """Get top N matching issues."""
        if not query or not query.strip():
            return []
        
        results = search_issues(query, self.issues, threshold)
        top = results[:limit]
        
        return [
            {
                'issue_code': issue.get('issue_code'),
                'display_name': issue.get('display_name'),
                'category': issue.get('category'),
                'confidence': confidence,
                'matched_terms': match_reason,
                'raw_issue': issue
            }
            for issue, confidence, match_reason in top
        ]
    
    def get_categories(self) -> List[str]:
        """Get unique issue categories."""
        categories = set(issue.get('category') for issue in self.issues)
        return sorted(list(categories))
    
    def get_issues_by_category(self, category: str) -> List[Dict]:
        """Get all issues in a category."""
        return [issue for issue in self.issues if issue.get('category') == category]
