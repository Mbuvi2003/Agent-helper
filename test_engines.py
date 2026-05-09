"""
Agent Helper -- Engine Integration Test
========================================
Exercises all core engines (Issue, Vetting, Snippet, Resolution) and the
DataLoader using real data files.

Run with: python test_engines.py
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(level=logging.WARNING)  # suppress INFO noise during tests

from data_loader import DataLoader
from issue_engine import IssueEngine
from resolution_engine import ResolutionEngine
from snippet_engine import SnippetEngine
from vetting_engine import VettingEngine


def test_app() -> None:
    """Run all engine integration tests and assert expected outputs."""
    print("=" * 60)
    print("Agent Helper -- Engine Integration Test")
    print("=" * 60)

    # -- Data loading --------------------------------------------------
    loader = DataLoader()
    data = loader.load_all()

    print(f"\n[1] Data Loaded:")
    print(f"  - Issues      : {len(data.get('issues', []))}")
    print(f"  - Snippets    : {len(data.get('snippets', []))}")
    print(f"  - Resolutions : {len(data.get('resolutions', []))}")

    # -- Issue Engine --------------------------------------------------
    issue_engine = IssueEngine(data)

    print(f"\n[2] Issue Engine Test:")
    test_queries = ["sim swap", "reversal 72hrs", "mpesa pin reset", "puk"]
    for query in test_queries:
        result = issue_engine.classify(query)
        if result:
            print(
                f"  '{query}' -> {result['display_name']} "
                f"(confidence: {result['confidence']}%)"
            )
        else:
            print(f"  '{query}' -> No match")

    # -- Vetting Engine ------------------------------------------------
    vetting_engine = VettingEngine()

    print(f"\n[3] Vetting Engine Test:")

    # Test A: CRM multi-line layout (VIEW360 style)
    crm_text = """
    Bio Card

    First Name
    NGIRUSIO

    Middle Name
    KASELE

    Last Name
    LOGIEL

    D.O.B
    01/07/1987

    ID Number
    33000129

    Airtime Balance
    23.50

    M-PESA Balance: 1,250.00
    """
    extracted = vetting_engine.extract_from_text(crm_text)
    print(f"  [A] CRM multi-line -- Extracted {len(extracted)} fields:")
    for field, value in extracted.items():
        print(f"    - {field}: {value}")

    assert extracted.get("Name") == "NGIRUSIO KASELE LOGIEL", (
        f"Name mismatch: {extracted.get('Name')}"
    )
    assert extracted.get("ID") == "33000129", f"ID mismatch: {extracted.get('ID')}"
    assert extracted.get("YOB") == "1987", f"YOB mismatch: {extracted.get('YOB')}"
    assert extracted.get("MPESA") == "1250", f"MPESA mismatch: {extracted.get('MPESA')}"
    assert extracted.get("Airtime") == "23", f"Airtime mismatch: {extracted.get('Airtime')}"
    print("  [A] OK All CRM assertions passed")

    # Test B: Inline / fallback format
    inline_text = """
    name: JOHN SMITH
    id: 12345678
    yob: 1990
    msisdn: 254712345678
    mpesa bal: 500
    """
    extracted_b = vetting_engine.extract_from_text(inline_text)
    print(f"\n  [B] Inline format -- Extracted {len(extracted_b)} fields:")
    for field, value in extracted_b.items():
        print(f"    - {field}: {value}")

    # Test C: Edge case -- commas in money, multiple balances
    edge_text = """
    First Name
    JANE

    Last Name
    DOE

    ID Number
    12345678

    D.O.B
    15/03/1992

    Fuliza Balance: 5,000.00
    M-PESA Account Balance: 3,400.50
    Main Balance: 100.00
    """
    extracted_c = vetting_engine.extract_from_text(edge_text)
    print(f"\n  [C] Edge cases -- Extracted {len(extracted_c)} fields:")
    for field, value in extracted_c.items():
        print(f"    - {field}: {value}")
    assert extracted_c.get("Name") == "JANE DOE", (
        f"Name mismatch: {extracted_c.get('Name')}"
    )
    assert extracted_c.get("MPESA") == "3400", (
        f"MPESA mismatch: {extracted_c.get('MPESA')}"
    )
    assert extracted_c.get("Airtime") == "100", (
        f"Airtime mismatch: {extracted_c.get('Airtime')}"
    )
    print("  [C] OK Edge case assertions passed")

    validation = vetting_engine.validate(extracted, "SIM_SWAP")
    print(f"\n  Validation status : {validation['vetting_status']}")
    print(f"  Complete          : {validation['is_complete']}")

    # -- Snippet Engine ------------------------------------------------
    snippet_engine = SnippetEngine({"snippets": data.get("snippets", [])})

    print(f"\n[4] Snippet Engine Test:")
    snippet_queries = ["/simswap", "reversal", "puk diy"]
    for query in snippet_queries:
        results = snippet_engine.search(query, limit=2)
        if results:
            for r in results:
                print(f"  '{query}' -> {r['trigger']} [{r['confidence']}%]")
        else:
            print(f"  '{query}' -> No match")

    # -- Resolution Engine ---------------------------------------------
    resolution_engine = ResolutionEngine({"resolutions": data.get("resolutions", [])})

    print(f"\n[5] Resolution Engine Test:")
    issue_code = "SIM_SWAP"
    vetting_status = "COMPLETE"
    resolutions = resolution_engine.get_valid_resolutions(issue_code, vetting_status)
    print(f"  {issue_code} with {vetting_status} vetting:")
    for res in resolutions:
        print(f"    - {res.get('resolution_code')}: {res.get('display_name')}")

    print(f"\n[6] Categories Available:")
    for cat in issue_engine.get_categories():
        print(f"  - {cat}")

    print("\n" + "=" * 60)
    print("All tests passed! App is ready to run.")
    print("Run: python main.py")
    print("=" * 60)


if __name__ == "__main__":
    test_app()
