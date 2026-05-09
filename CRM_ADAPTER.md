# Plug-and-Play CRM Adapter — Implementation Guide

## What was built

| File | Status | Purpose |
|---|---|---|
| `crm_adapter.py` | **New** | Adapter module — the only file that ever talks to an external API |
| `.env.example` | **New** | Safe-to-commit credentials template |
| `.env` | *You create this* | Real secrets (git-ignored) |
| `vetting_engine.py` | **Updated** | Added `resolve_vetting_data()` with adapter → clipboard fallback |
| `requirements.txt` | **Updated** | Added `python-dotenv>=1.0.0` |
| `.gitignore` | **Updated** | Added `.env` exclusion rule |

---

## How the fallback chain works

```
UI / Resolution Engine
        │
        ▼
VettingEngine.resolve_vetting_data(identifier, raw_text)
        │
        ├─► crm_adapter.fetch_customer_data(identifier)
        │         │
        │    .env configured? ──No──► return None
        │         │
        │        Yes
        │         │
        │    _fetch_from_api(identifier)
        │         │
        │    return dict  ◄── CRM data used directly
        │
        └─► (if None) extract_vetting_fields_from_text(raw_text)
                  │
             return dict  ◄── Clipboard parsing fallback
```

The `_source` key in the returned dict (`'crm_api'` or `'clipboard'`) lets you optionally show a status badge in the UI — but nothing breaks if you ignore it.

---

## Secrets management

### 1. Copy the template
```powershell
Copy-Item .env.example .env
```

### 2. Fill in your credentials in `.env`
```ini
CRM_BASE_URL=https://api.your-crm-provider.com/v1
CRM_API_KEY=sk_live_abc123…
CRM_TIMEOUT_SECONDS=10
CRM_ENVIRONMENT=production
```

### 3. Never commit `.env`
`.gitignore` already excludes it. `.env.example` (no real values) is safe to commit.

---

## Calling `resolve_vetting_data` from the UI

The existing UI code calls `engine.extract_from_text(clipboard_text)`.  
To upgrade a call-site to use the adapter, change:

```python
# OLD — clipboard only
fields = engine.extract_from_text(clipboard_text)
```

```python
# NEW — adapter first, clipboard fallback
fields = engine.resolve_vetting_data(
    identifier=msisdn_field.get(),   # phone number the agent typed
    raw_text=clipboard_text          # paste buffer as before
)
```

The rest of the code (`validate()`, `format_vetting_result()`, etc.) is unchanged.

---

## Connecting a real API (future)

**Only one file changes: `crm_adapter.py`.**

Replace the body of `_fetch_from_api()`:

```python
def _fetch_from_api(self, identifier: str) -> Optional[dict]:
    import requests
    headers = {"Authorization": f"Bearer {self._api_key}"}
    url = f"{self._base_url}/customers/{identifier}"
    try:
        response = requests.get(url, headers=headers, timeout=self._timeout)
        response.raise_for_status()
        return self._parse_api_response(response.json())
    except requests.RequestException as exc:
        logger.error("CRMAdapter: API request failed — %s", exc)
        return None   # triggers clipboard fallback automatically
```

Then update `_parse_api_response()` to map your CRM's JSON keys to VettingEngine field names (a simple dict lookup — already scaffolded).

> **Zero changes** are required in `ui.py`, `resolution_engine.py`, `snippet_engine.py`, or any other module.

---

## Mock data (current state)

Two test MSISDNs are hard-coded in `_fetch_from_api()` for development:

| MSISDN | Name | ID |
|---|---|---|
| `0712345678` | Jane Doe | 12345678 |
| `0798765432` | John Mwangi | 87654321 |

Any other identifier returns `None` → clipboard fallback activates.

---

## Running the smoke test

```powershell
python test_crm_adapter.py
```

Expected output:
```
=== TEST 1: Adapter configured? ===
  crm_adapter.is_configured = False

=== TEST 2: fetch_customer_data (no .env -> returns None) ===
  Result: None

=== TEST 3: resolve_vetting_data (clipboard fallback) ===
  Source : clipboard
  Fields : {'MPESA': '1200', 'YOB': '1992', '_source': 'clipboard'}

All smoke tests passed.
```
