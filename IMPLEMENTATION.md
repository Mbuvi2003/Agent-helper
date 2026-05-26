# Agent Helper — Implementation Summary

## Status: Production-Ready ✅

All core systems are operational and tested. The app is packaged as an MSIX bundle for the Microsoft Store.

---

## Project Structure

```
Agent_helper/
├── main.py                    # Entry point
├── ui.py                      # Tkinter GUI — Main (1400×800) & Mini-App views
├── issue_engine.py            # Issue classification engine
├── vetting_engine.py          # Vetting extraction & validation
├── resolution_engine.py       # Resolution rules & output generation
├── snippet_engine.py          # Snippet search & management
├── text_utils.py              # Fuzzy matching, normalization, validators
├── data_loader.py             # JSON persistence (writable dir + bundled defaults)
├── crm_adapter.py             # Plug-and-play live CRM API adapter
├── editor_ui.py               # Graphical issue/resolution editor
├── test_engines.py            # Engine smoke tests
├── requirements.txt           # Python dependencies
├── build.ps1                  # PyInstaller build script
├── README.md                  # User guide
├── IMPLEMENTATION.md          # This file
├── CRM_ADAPTER.md             # CRM adapter integration guide
├── PRIVACY_POLICY.md          # Data handling policy
└── data/
    ├── issues.json            # 26 issue definitions
    ├── snippets.json          # 25 pre-built response templates
    ├── resolutions.json       # 39 resolution rules & outcomes
    ├── settings.json          # App configuration & version
    ├── history.json           # Search history
    ├── favorites.json         # User favorites
    └── user_guidance.json     # Per-issue guidance overrides
```

---

## Engine Specifications

### 1. Issue Engine (`issue_engine.py`)
- Keyword matching (exact + partial) across 26 issue types
- Synonym matching with fuzzy scoring (rapidfuzz + difflib fallback)
- Confidence ranking; returns: `issue_code`, `display_name`, `category`, `confidence`, `requires_vetting`, `valid_resolutions`, `snippets`

### 2. Vetting Engine (`vetting_engine.py`)
- Auto-extraction from pasted CRM text (regex-based)
- **Name validation** — `_validate_name()` in `text_utils.py`: 2–4 words, all letters, no `-NA` filler ever appended. "John Doe" returns exactly "John Doe".
- **Numeric validation** — ID/YOB/balances: digits only, CRM noise rejected
- Status classification: `COMPLETE`, `INCOMPLETE`, `NO_DATA`, `INVALID_FORMAT`
- CRM adapter fallback chain: live API → clipboard paste

### 3. Resolution Engine (`resolution_engine.py`)
- Rule-based resolution filtering (issue_code + vetting_status)
- Template text generation with vetting field substitution
- Outcome tracking: approved, escalated, processing, advice, resolved

### 4. Snippet Engine (`snippet_engine.py`)
- Trigger-based lookup (`/simswap`, `/reversal`, `/puk`, etc.)
- Keyword fuzzy search; 25 snippets across 5 categories

### 5. Text Utils (`text_utils.py`)
- Text normalisation, fuzzy matching (rapidfuzz → difflib fallback)
- `_validate_name()` — strict 2–4 all-letter word rule, no filler logic
- `_validate_numeric_field()` — digits only
- PRS strict mode: 5+ digit codes; Skiza tune name regex extraction

### 6. Tkinter GUI (`ui.py`)

#### Top Bar — strict LEFT / RIGHT layout
```
LEFT cluster                                         RIGHT button_cluster_frame
[Agent Helper v1.9.0] [🔍 search entry] [Clear All]   [⚙️ Edit] [💡 Ask me how] [▣ Mini]
```
- All right-side buttons: `relief="flat"`, `cursor="hand2"`, consistent font/padding
- Mini view Row 1: `[🔍 entry]` LEFT | `[⚙️ Edit][💡][📌 Pin][▣ Full][Clear]` RIGHT
- **💡 Ask me how** present in BOTH Main and Mini views

#### Guidance Panel
| Control | Behaviour |
|---|---|
| 🔍 filter Entry | Live-typing filter (no popup); icon label outside the box; ✕ clears instantly |
| ➕ Add | Dialog prompt; rejects duplicates; enables 💾 Save |
| 💾 Save | Persists to `user_guidance.json`; disabled until ➕ Add used; resets after save |
| Click a note | Copies **full** raw note text to clipboard (including multi-line paragraphs) |

#### Phone Number Ring Buffer
- Replaces the old locked-flag system
- `_phone_ring_index` (modulo 2): even index → Box 1, odd → Box 2
- Endlessly cycles: 3rd number → Box 1, 4th → Box 2, etc.
- Reset only on "Clear All"

#### Smart Reversal Listener
- Triggers when a txn ID (8–12 alphanumeric with at least one letter) is copied
- **Mutually exclusive** with SR listener — arming one fully disarms the other (including pending timers and Hakikisha SMS queue)
- Listener waits **indefinitely** — no premature 3s auto-finalize
- Agent types SLA digits (`2`, `12`, or `72`); after 1.5s silence → finalize
- Builds: `<txn_id>\n<SLA note text>` → copies to clipboard
- Arms Sequential Clipboard Queue: next Ctrl+V loads Hakikisha SMS

#### SR SLA Listener
- Triggers when an SR number matching `_sr_regex` is copied
- **Mutually exclusive** with Reversal listener — arming one fully disarms the other
- Agent types SLA hours; after 1.5s silence → finalize
- Output format (fixed): `<SR> SR raised SLA <N> hours`

#### Global Hotkey (EDR-Compliant)
- `Ctrl+Shift+Space` — toggles app show/hide from any window
- Uses native Win32 `RegisterHotKey` in a background thread to completely avoid the `keyboard` library, which triggers corporate IT / EDR anti-keylogger defenses.

#### SIM Swap / HLR
- Manual "HLR" button added next to the target number Box 2
- Instantly extracts the last 6 digits of the target number to clipboard

### 7. CRM Adapter (`crm_adapter.py`)
- Plug-and-play: configure `.env` to enable live API; unconfigured → clipboard fallback
- Only `crm_adapter.py` changes when connecting a real API — no other module touched
- See `CRM_ADAPTER.md` for full integration guide

### 8. Data Loader (`data_loader.py`)
- Reads from bundled `data/` directory (source / MSIX bundle)
- Writes to `%LOCALAPPDATA%\AgentHelper\data\` (writable user directory)
- Seeds missing files from bundled defaults on first run
- **Auto-merges** missing issue codes from the bundled `issues.json` into the user's local copy on every load — ensures app updates always deliver new issue types without destroying user edits

### 9. CRM Extraction (`ui.py` — `_do_extract`)
- **Hard reset** on every new CRM paste: clears all `extracted_fields`, `field_entries`, `serial_var`, `extracted_codes`, and `_skiza_tune_name` before parsing
- Only fields actually found in the new CRM text are populated — no stale data from a previous customer can leak through
- Only `Name`, `ID`, `YOB`, `MPESA`, and `Airtime` are extracted; Serial No and Fuliza are excluded from auto-extraction

---

## Completed Feature Checklist

| Feature | Sprint |
|---|---|
| Issue classification (26 types, fuzzy matching) | 1 |
| Snippet library (25 templates, trigger search) | 1 |
| Mini-App mode (right-snap, phone-width) | 1 |
| Ghost-clearing (stale data wiped on issue switch) | 1 |
| Strict name validation (2–4 letters-only words, no -NA) | 2 → 8 |
| Strict numeric validation (ID/YOB/balances) | 2 |
| PRS 5-digit enforcement; Skiza tune capture | 2 |
| Ring-buffer calling number (endless modulo-2 cycle) | 2 → 8 |
| Line Unsuspension (Pass/Fail/Failed Twice) | 3 |
| Serial number suppression from Fail outputs | 3 |
| Smart Reversal Listener (txn ID → SLA → auto-copy) | 4 |
| Smart Reversal Listener hardened (no premature auto-fire) | 8 |
| SR SLA Listener (`<SR> SR raised SLA <N> hours`) | 4 → 8 |
| Sequential Clipboard Queue (Hakikisha SMS on next Ctrl+V) | 4 |
| Global hotkey — `Ctrl+Shift+Space` | 4 → 8 |
| Guidance panel (per-issue, editable, persisted) | 4 |
| Guidance panel — live filter, duplicate check, Save gating | 8 |
| Guidance click-to-copy | 8 |
| Search floating dropdown | 6 |
| Graphical Issue/Resolution Editor | 6 |
| Strict extraction whitelisting (sensitive fields excluded) | 7 |
| SLA graceful degradation (Txn Code fallback) | 7 |
| MSIX production bundle | 7 |
| EDR Compliant (Zero `keyboard` lib dependency, Win32 Hooks) | 8 |
| HLR Manual extraction button (SIM Swap) | 8 |
| Safaricom UI Branding (Colors, modern flat buttons) | 8 |
| Top bar LEFT/RIGHT strict layout | 8 |
| Button rename: ⚙️ Edit, 📌 Pin | 8 |
| 💡 Ask me how in Mini view | 8 |
| Consistent button styling (flat, hand2, uniform padding) | 8 |
| CRM Adapter (plug-and-play, clipboard fallback) | 6 |
| DataLoader writable user directory | 7 |
| DataLoader auto-merge missing issues on update | 9 |
| Missing issue error popup (replaces silent failure) | 9 |
| Listener mutual exclusion (Reversal ↔ SR) | 9 |
| Guidance full-paragraph copy (tag-based click) | 9 |
| CRM hard reset on new paste (no stale data leaks) | 9 |

---

## How to Run

### Production (MSIX)
Install from the Microsoft Store. Silent updates are automatic.

### Developer / Local Source
```bash
cd C:\Users\PC\Documents\Agent_helper
pip install -r requirements.txt
python main.py
```

### Standalone EXE (testing only)
```bash
pip install pyinstaller
python build.ps1   # or: pyinstaller --onefile --windowed main.py
```

---

## Performance

| Metric | Target |
|---|---|
| Cold start | < 2 seconds |
| Search response | < 100 ms |
| Fuzzy matching (26 issues) | < 50 ms |
| Memory footprint | ~20–30 MB |
| Internet required | ❌ None |

---

**Agent Helper is production-ready for call center use.**

Built for speed, reliability, and zero-friction extension.
