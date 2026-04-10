"""Quick standalone test of the new vetting extraction logic."""
from text_utils import extract_vetting_fields_from_text

# ── Test A: CRM multi-line layout (VIEW360 style) ──
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
r = extract_vetting_fields_from_text(crm_text)
print("=== Test A: CRM Layout ===")
for k, v in r.items():
    print(f"  {k}: {v}")

assert r.get("Name") == "NGIRUSIO KASELE LOGIEL", f"Name: {r.get('Name')}"
assert r.get("ID") == "33000129", f"ID: {r.get('ID')}"
assert r.get("YOB") == "1987", f"YOB: {r.get('YOB')}"
assert r.get("MPESA") == "1250", f"MPESA: {r.get('MPESA')}"
assert r.get("Airtime") == "23", f"Airtime: {r.get('Airtime')}"
print("  PASS\n")

# ── Test B: Edge cases — commas, multiple balances, missing middle name ──
edge = """
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
r2 = extract_vetting_fields_from_text(edge)
print("=== Test B: Edge Cases ===")
for k, v in r2.items():
    print(f"  {k}: {v}")

assert r2.get("Name") == "JANE DOE", f"Name: {r2.get('Name')}"
assert r2.get("MPESA") == "3400", f"MPESA: {r2.get('MPESA')}"
assert r2.get("Airtime") == "100", f"Airtime: {r2.get('Airtime')}"
assert r2.get("YOB") == "1992", f"YOB: {r2.get('YOB')}"
print("  PASS\n")

# ── Test C: Missing fields → None ──
empty = "hello world nothing here"
r3 = extract_vetting_fields_from_text(empty)
print("=== Test C: Missing Fields ===")
print(f"  Fields: {r3}")
assert r3.get("MPESA") is None
assert r3.get("Airtime") is None
assert r3.get("Name") is None
print("  PASS\n")

# ── Test D: Inline format (old-style paste) ──
inline = """
mpesa bal: 500
airtime bal: 75.50
subscriber name: JOHN SMITH
id no: 87654321
yob: 1985
msisdn: 254712345678
"""
r4 = extract_vetting_fields_from_text(inline)
print("=== Test D: Inline Format ===")
for k, v in r4.items():
    print(f"  {k}: {v}")
assert r4.get("MPESA") is not None, "MPESA missing"
assert r4.get("Airtime") is not None, "Airtime missing"
print("  PASS\n")

# ── Test E: M-PESA on separate line ──
separate = """
M-PESA
2,500.75
"""
r5 = extract_vetting_fields_from_text(separate)
print("=== Test E: MPESA on next line ===")
for k, v in r5.items():
    print(f"  {k}: {v}")
assert r5.get("MPESA") == "2500", f"MPESA: {r5.get('MPESA')}"
print("  PASS\n")

print("ALL TESTS PASSED")
