# Agent Helper - Call Center Support Desktop App

Fast, offline desktop app for call center agents. Instantly identify customer issues, extract vetting data, retrieve resolution workflows, and copy prepared responses.

## Features

- **Issue Classification**: Instant keyword/fuzzy matching to identify customer problems
- **Vetting Extraction**: Auto-parse customer data from pasted notes or manual forms
- **Strict Data Typing**: Name validated as letters-only (2-4 words); ID/YOB/balances validated as numbers-only — rejects noisy CRM artifacts
- **Resolution Engine**: Smart rule-based resolution options based on issue + vetting state
- **Snippet Library**: One-click copy of pre-built response templates
- **PRS/Skiza Intelligence**: PRS codes forced to 5+ digits (filters out false 4-digit matches); Skiza tune name auto-captured
- **Sticky Calling Number**: Once detected, the calling number stays locked until you copy it or clear the session
- **Mini-App Mode**: Phone-width window snapped to right edge with focus-based transparency
- **Search**: Lightning-fast search on keywords, triggers, synonyms
- **Offline**: No internet required; all data stored locally (JSON)
- **Keyboard Hotkeys**: Faster workflow during live calls

## Quick Start

### 1. Install dependencies:
```bash
pip install -r requirements.txt
```

### 2. Run the app:
```bash
python main.py
```

### 3. Use the app:
- **Type or paste** a customer issue in the search bar
- **Click a category** on the left to filter issues
- **Select an issue** from results to view details
- **Paste customer notes** to extract vetting data automatically
- **Copy snippets** to clipboard with one click

## Data Structure

All data is stored in `data/` folder as JSON:

- `issues.json` - Issue definitions with keywords, synonyms, required fields
- `snippets.json` - Quick response templates with triggers
- `resolutions.json` - Resolution rules and outcomes
- `settings.json` - App configuration
- `history.json` - Search history and recent copies
- `favorites.json` - User-saved favorites

## Customize Data

Edit JSON files directly to add:
- New issue categories
- Custom snippets and triggers
- Resolution rules

Changes are automatically loaded on app restart.

## Architecture

- `issue_engine.py` - Issue classification
- `vetting_engine.py` - Data extraction & validation
- `resolution_engine.py` - Resolution logic & rules
- `snippet_engine.py` - Snippet search & management
- `text_utils.py` - Search, fuzzy matching, text normalization
- `data_loader.py` - JSON persistence
- `ui.py` - Tkinter interface
- `main.py` - Entry point

## Example Workflows

### SIM Swap:
1. Type `sim swap` or `swap vetting`
2. Paste customer note → auto-extracts name, ID, YOB
3. See vetting status (COMPLETE/INCOMPLETE)
4. View resolution options (based on vetting status)
5. Copy final response to agent tools

### M-PESA Reversal:
1. Type `reversal 72hrs`
2. App suggests "Reversal - 72 Hour SLA"
3. View SLA details and Hakikisha education snippet
4. Copy response → `/reversal_72h` trigger auto-fills

### Quick Snippet:
1. Type `/simswap_failed`
2. See pre-built response
3. Copy to clipboard instantly

## Tips

- Use **Paste** button to auto-extract customer data from unstructured notes
- **Category buttons** are faster than searching when you know the domain
- **Hotkeys** (when enabled): Ctrl+1 for /simswap, Ctrl+2 for /reversal, etc.
- **Fuzzy matching** tolerates typos: "pin rset" → "pin reset"
- **Favorites** save your most-used snippets for instant access
- **Calling number** auto-locks on first detection — copy it to unlock for the next caller
- **Mini mode** (▫ Mini button) snaps to the right side and fades when you switch to CRM
- **Switching issues** auto-clears stale data — no more ghost fields from the last call

## Changelog

### v1.3.0 — Sprint 2: Advanced Vetting Engine
- **Strict typing**: Name must be 2-4 words (letters only); ID/YOB/balances numbers-only
- **PRS 5-digit enforcement**: 4-digit codes are no longer incorrectly captured for PRS
- **Skiza tune name capture**: Extracted automatically from CRM paste
- **Sticky calling number**: Locks on first detection, unlocked by Copy or Clear All
- **Ghost-clearing**: Switching issues clears all stale output/field data
- **Reversal redesign**: Step 2 box hidden; Pending Authorized added as checkbox
- **Mini-App**: Right-side snap + focus-based transparency
- **Auto-scroll**: Copy Output scrolls canvas back to top

### v1.4.0 — Sprint 3+4: New Issues, Automation & Guidance Editor
- **Line Unsuspension**: New issue type with full vetting (Pass/Fail Secondary/Fail Primary/Failed Twice)
- **SIM Swap serial suppression**: Serial No excluded from Fail Secondary and Failed Twice output
- **Apps cleared**: Shortened SUSPENDING_LINE footer from "Mpesa APP, Safaricom APP profile cleared." to "Apps cleared."
- **Smart Reversal Listener**: Copy a transaction ID → press 2/12/72 → reversal output auto-copied to clipboard
- **Win+A hotkey fix**: Replaced `keyboard` library hook with `ctypes.RegisterHotKey` for work-managed Windows
- **Guidance Editor**: Save (💾) and Add (+) buttons on the guidance panel — saves to `user_guidance.json`

## Planned Enhancements

- In-app snippet editing UI
- Expanded Skiza tune database
- Agent performance metrics

## License

Internal tool.
