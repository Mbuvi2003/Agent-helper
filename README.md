# Agent Helper — Call Center Support Desktop App

Fast, offline desktop tool for call center agents. Instantly classify customer issues, auto-extract vetting data, retrieve resolution workflows, and copy prepared interaction notes — all in one keyboard-driven interface.

## Features

- **Issue Classification** — Instant keyword/fuzzy matching across 26 issue types
- **Vetting Extraction** — Auto-parse customer data from pasted CRM notes
- **Strict Data Typing** — Names: 2–4 all-letter words only (no `-NA` filler); ID/YOB/balances: digits only — rejects CRM noise
- **Resolution Engine** — Rule-based resolution options driven by issue + vetting state
- **Snippet Library** — One-click copy of 25+ pre-built response templates
- **PRS/Skiza Intelligence** — PRS codes enforced at 5+ digits; Skiza tune names auto-captured
- **Ring-Buffer Phone Numbers** — Calling/Target numbers cycle endlessly: 1st → Box 1, 2nd → Box 2, 3rd → Box 1 again…
- **Smart Reversal Listener** — Copy a txn ID → type `2`, `12`, or `72` → full reversal note auto-copies to clipboard; fires only after digit input (no premature auto-finalize)
- **Mutually Exclusive Listeners** — Reversal and SR listeners automatically disarm each other to prevent conflicting output
- **SR SLA Listener** — Copy an SR number → type SLA hours → note auto-built as `<SR> SR raised SLA <N> hours`
- **Sequential Clipboard Queue** — After reversal note copies, next Ctrl+V auto-loads the Hakikisha SMS
- **Guidance Panel** — Per-issue guidance with inline filter (live-typing), Add (with duplicate check), and Save (enabled only after Add is used)
- **Mini-App Mode** — Phone-width window snapped to the right edge of the screen
- **Global Hotkey** — `Ctrl+Shift+Space` toggles app visibility from any window
- **⚙️ Edit Issues** — Graphical in-app issue/resolution editor
- **💡 Ask me how** — Floating SIM Swap cheat-sheet (available in both Main and Mini views)
- **Search** — Lightning-fast fuzzy search across keywords, triggers, synonyms
- **Offline** — No internet required; all data stored locally in JSON

## Top Bar Layout

```
[Agent Helper v1.9.0] [🔍 _____________ ] [Clear All]     [⚙️ Edit] [💡 Ask me how] [▣ Mini]
 ←————————————— LEFT (search zone) ————————————————→       ←————— RIGHT (button cluster) ——→
```

**Mini view** exposes the same buttons in Row 1:
```
[🔍 ____] [⚙️ Edit] [💡] [📌 Pin] [▣ Full] [Clear]
```

## Deployment & Installation

### Official Production Release (MSIX & Microsoft Store)
Agent Helper is packaged as a secure, sandboxed **MSIX bundle** distributed via the **Microsoft Store**:
- Clean, sandboxed installation — no registry debris
- Seamless silent auto-updates
- Full compliance with enterprise deployment tools (MECM / Intune)

### Developer / Local Testing
```bash
pip install -r requirements.txt
python main.py
```

## Usage

1. **Type** a customer issue in the 🔍 search bar — results appear instantly in a dropdown
2. **Click an issue** to load its guidance, vetting fields, and resolution options
3. **Paste CRM notes** (📋 Paste CRM) to auto-extract vetting data
4. **Copy snippets or interaction output** with one click
5. Switch to **Mini mode** (▣ Mini) for a phone-width sidebar during calls

## Global Shortcut

| Shortcut | Action |
|---|---|
| `Ctrl+Shift+Space` | Toggle app visibility (show/hide from any window) |
| `Ctrl+C` | Copy interaction output |
| `Ctrl+V` *(armed)* | Load Hakikisha SMS to clipboard after reversal note |

## Guidance Panel

| Control | Behaviour |
|---|---|
| 🔍 filter box | Live-typing — filters notes instantly as you type; empty = show all |
| ✕ | Clears the filter in one click |
| ➕ Add | Prompts for a new note; rejects duplicates; enables 💾 Save |
| 💾 Save | Persists the current list to `user_guidance.json`; only enabled after ➕ Add is used |
| Click a note | Copies the **full** note text to clipboard (including multi-line paragraphs) |

## Data Structure

All data lives in `data/` (JSON, human-editable):

| File | Contents |
|---|---|
| `issues.json` | 26 issue definitions with keywords, synonyms, vetting requirements |
| `snippets.json` | 25 quick-response templates with triggers |
| `resolutions.json` | 39 resolution rules and outcomes |
| `settings.json` | App configuration and version |
| `history.json` | Search history |
| `favorites.json` | User-saved favorites |
| `user_guidance.json` | Per-issue guidance overrides (editable via ➕ Add / 💾 Save) |

## Architecture

| Module | Purpose |
|---|---|
| `main.py` | Entry point |
| `ui.py` | Tkinter GUI — Main & Mini views |
| `issue_engine.py` | Issue classification |
| `vetting_engine.py` | Data extraction & validation |
| `resolution_engine.py` | Resolution rules & output generation |
| `snippet_engine.py` | Snippet search & management |
| `text_utils.py` | Fuzzy matching, normalization, name/numeric validation |
| `data_loader.py` | JSON persistence (writable user dir + bundled defaults + auto-merge on update) |
| `crm_adapter.py` | Plug-and-play live CRM API adapter (clipboard fallback if unconfigured) |
| `editor_ui.py` | Graphical issue/resolution editor |

## Example Workflows

### SIM Swap
1. Type `sim swap` → select issue
2. Paste customer note → name, ID, YOB auto-extracted
3. See vetting status (COMPLETE / INCOMPLETE)
4. Copy interaction output

### M-PESA Reversal (Smart Listener)
1. Copy the transaction ID from CRM → app detects it automatically
2. Type `72` (or `12` or `2`) for the SLA
3. Full reversal note + SLA text copies to clipboard after 1.5s of silence
4. Press Ctrl+V again → Hakikisha SMS auto-loads

### SR Escalation (SR Listener)
1. Copy an SR number matching the configured pattern
2. Type the SLA hours (e.g. `48`)
3. App builds: `SR12345 SR raised SLA 48 hours` — auto-copied

### Quick Snippet
1. Type `/simswap_failed` in the search bar
2. Pre-built response appears
3. Click to copy instantly

## Changelog

### v1.9.0 — Sprint 9: Stability, Data Sync & Bug Fixes
- **Data Auto-Sync on Update** — `data_loader.py` now auto-merges missing issue codes from the bundled database into the user's local `issues.json` on every load. Ensures app updates never leave users with a broken/outdated issue catalogue while preserving any custom edits.
- **Missing Issue Error Popup** — `_select_issue_by_code` now shows a clear error dialog instead of silently doing nothing when an issue code is missing from the local database.
- **Listener Mutual Exclusion** — Reversal and SR SLA listeners are now mutually exclusive. Arming one fully disarms the other (including pending timers and Hakikisha SMS queue), eliminating race conditions that produced merged/wrong output.
- **Guidance Full-Paragraph Copy** — Clicking a multi-line guidance note now copies the entire paragraph, not just the single visual line under the cursor. Uses tag-based lookup instead of `linestart`/`lineend`.
- **CRM Hard Reset on New Paste** — `_do_extract` now performs a full wipe of all previous extracted fields, serial number, SDP codes, and entry widgets before parsing new CRM text. Prevents stale data from a previous customer leaking into the next extraction.

### v1.8.1 — Sprint 8: Enterprise Security & Brand UI
- **EDR Compliance** — Completely removed `keyboard` library dependencies. Global hotkeys and clipboard monitoring now use native Win32 `RegisterHotKey` and Tkinter polling to bypass locked-down corporate IT/EDR security software.
- **HLR Manual Button** — Replaced the complex HLR auto-timer with a simple, speed-independent "HLR" button next to the target number box that instantly copies the 6-digit suffix.
- **Safaricom Branding** — Full UI overhaul featuring Safaricom brand colors (Primary Green, Danger Red, Secondary Light Green) with modern, flat, padded button designs.
- **Vetting Layout** — Reverted vetting fields to the classic single-column vertical list for optimal workflow familiarity.

### v1.8.0 — Sprint 8: UX Polish & Logic Fixes

- **Name extraction fixed** — `_validate_name()` now strictly requires 2–4 all-letter words with no `-NA` filler logic. "John Doe" returns exactly "John Doe".
- **Ring-buffer phone numbers** — Replaced the locked-flag system with an infinite ring buffer: 3rd number replaces Box 1, 4th replaces Box 2, and so on endlessly.
- **SR interaction note format** — Fixed output to the exact spec: `<SR> SR raised SLA <N> hours` (template-based approach removed).
- **Smart Reversal Listener hardened** — Removed the 3s auto-finalize timer that caused premature "Txn Code Only" output. Listener now waits indefinitely until the agent types SLA digits, then finalises after 1.5s of silence. All digit keys accepted (not just `1`, `2`, `7`).
- **Global hotkey** — Changed from `Alt+Space` (OS menu conflict) to **`Ctrl+Shift+Space`**.
- **Guidance panel overhaul**:
  - Inline live-filter search box (no popup) — 🔍 icon outside, empty Entry, ✕ clear button
  - Layout: Filter (50%) | ➕ Add (25%) | 💾 Save (25%) in both Main and Mini views
  - Save disabled until ➕ Add is used; duplicate notes rejected automatically
  - Click any guidance line → copies it to clipboard
- **Top bar redesign**:
  - Strict LEFT / RIGHT zone layout using `button_cluster_frame`
  - Renamed: `"✏️ Editor"` → `"⚙️ Edit"`, Pin button now labelled `"📌 Pin"`
  - Button order: `[⚙️ Edit]` → `[💡 Ask me how]` → `[▣ Mini]`
  - **💡 Ask me how** now present in Mini view (was missing before)
  - Consistent `relief="flat"`, `cursor="hand2"` across all header buttons

### v1.7.4 — Sprint 7: Production Hardening
- Strict extraction whitelisting; excluded sensitive fields from auto-extraction
- SLA graceful degradation (no hardcoded 2hr default)
- Inline guidance `ScrolledText` editor; persisted to `user_guidance.json`
- MSIX bundle compiled and workspace sanitized

### v1.7.0 — Sprint 6: Issue Editor & Streamlined UI
- Graphical in-app issue/resolution editor (`editor_ui.py`)
- Floating search-result dropdown replaces static listboxes
- Reversal 72hr SLA output cleaned up

### v1.4.0 — Sprint 3+4: Automation & Guidance
- Line Unsuspension issue with full vetting model
- Smart Reversal Listener (txn ID → SLA keypress → auto-copy)
- Global hotkey architecture (keyboard library)
- Guidance Editor with Save/Add buttons

### v1.3.0 — Sprint 2: Advanced Vetting Engine
- Strict name/numeric typing; PRS 5-digit enforcement
- Skiza tune name auto-capture
- Sticky calling number (lock on detection)
- Mini-App right-snap mode

## Privacy Policy
See [PRIVACY_POLICY.md](PRIVACY_POLICY.md) for full details on offline-first data handling.

## License
Internal tool — not for redistribution.
