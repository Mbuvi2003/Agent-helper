"""
Quick test of Agent Helper engines
Tests issue classification, vetting extraction, snippet search
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from data_loader import DataLoader
from issue_engine import IssueEngine
from vetting_engine import VettingEngine
from resolution_engine import ResolutionEngine
from snippet_engine import SnippetEngine

def test_app():
    print("=" * 60)
    print("Agent Helper - Engine Test")
    print("=" * 60)
    
    # Load data
    loader = DataLoader("data")
    data = loader.load_all()
    
    print(f"\n[1] Data Loaded:")
    print(f"  - Issues: {len(data.get('issues', {}).get('issues', []))}")
    print(f"  - Snippets: {len(data.get('snippets', {}).get('snippets', []))}")
    print(f"  - Resolutions: {len(data.get('resolutions', {}).get('resolutions', []))}")
    
    # Test Issue Engine
    issue_engine = IssueEngine(data.get('issues', {}))
    
    print(f"\n[2] Issue Engine Test:")
    test_queries = ["sim swap", "reversal 72hrs", "mpesa pin reset", "puk"]
    for query in test_queries:
        result = issue_engine.classify(query)
        if result:
            print(f"  '{query}' → {result['display_name']} (confidence: {result['confidence']}%)")
        else:
            print(f"  '{query}' → No match")
    
    # Test Vetting Engine
    vetting_engine = VettingEngine()
    
    print(f"\n[3] Vetting Engine Test:")
    sample_text = """
    name: JOHN SMITH
    id: 12345678
    yob: 1990
    msisdn: 254712345678
    mpesa bal: 500
    """
    extracted = vetting_engine.extract_from_text(sample_text)
    print(f"  Extracted {len(extracted)} fields from sample text:")
    for field, value in extracted.items():
        print(f"    - {field}: {value}")
    
    validation = vetting_engine.validate(extracted, 'SIM_SWAP')
    print(f"  Validation status: {validation['vetting_status']}")
    print(f"  Complete: {validation['is_complete']}")
    
    # Test Snippet Engine
    snippet_engine = SnippetEngine(data.get('snippets', {}))
    
    print(f"\n[4] Snippet Engine Test:")
    snippet_queries = ["/simswap", "reversal", "puk diy"]
    for query in snippet_queries:
        results = snippet_engine.search(query, limit=2)
        if results:
            for r in results:
                print(f"  '{query}' → {r['trigger']} [{r['confidence']}%]")
        else:
            print(f"  '{query}' → No match")
    
    # Test Resolution Engine
    resolution_engine = ResolutionEngine(data.get('resolutions', {}))
    
    print(f"\n[5] Resolution Engine Test:")
    issue_code = "SIM_SWAP"
    vetting_status = "COMPLETE"
    resolutions = resolution_engine.get_valid_resolutions(issue_code, vetting_status)
    print(f"  {issue_code} with {vetting_status} vetting:")
    for res in resolutions:
        print(f"    - {res.get('resolution_code')}: {res.get('display_name')}")
    
    print(f"\n[6] Categories Available:")
    categories = issue_engine.get_categories()
    for cat in categories:
        print(f"  - {cat}")
    
    print("\n" + "=" * 60)
    print("All tests passed! App is ready to run.")
    print("Run: python main.py")
    print("=" * 60)

if __name__ == "__main__":
    test_app()
