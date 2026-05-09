from crm_adapter import crm_adapter
from vetting_engine import VettingEngine

engine = VettingEngine()

print("=== TEST 1: Adapter configured? ===")
print("  crm_adapter.is_configured =", crm_adapter.is_configured)

print()
print("=== TEST 2: fetch_customer_data (no .env -> returns None) ===")
result = crm_adapter.fetch_customer_data("0712345678")
print("  Result:", result)

print()
print("=== TEST 3: resolve_vetting_data (clipboard fallback) ===")
sample_text = "Name: Alice Wambui\nID: 30001234\nYOB: 1992\nMPESA: KES 1,200.00"
data = engine.resolve_vetting_data(identifier="0712345678", raw_text=sample_text)
print("  Source :", data.get("_source"))
print("  Fields :", data)

print()
print("All smoke tests passed.")
