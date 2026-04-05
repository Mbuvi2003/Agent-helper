# Agent Helper - Call Center Support Desktop App

Fast, offline desktop app for call center agents. Instantly identify customer issues, extract vetting data, retrieve resolution workflows, and copy prepared responses.

## Features

- **Issue Classification**: Instant keyword/fuzzy matching to identify customer problems
- **Vetting Extraction**: Auto-parse customer data from pasted notes or manual forms
- **Resolution Engine**: Smart rule-based resolution options based on issue + vetting state
- **Snippet Library**: One-click copy of pre-built response templates
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

## Performance

- Opens in < 2 seconds on typical Windows machine
- Search results appear in < 100ms
- All data fits in RAM (no database, no API calls)
- Works on slow networks or completely offline

## Planned Enhancements

- Hotkey support (Ctrl+1, Ctrl+2, etc. for snippets)
- In-app snippet editing UI
- History tracking (recent searches, copied items)
- Favorites management
- PyInstaller packaging into single .EXE

## License

Internal tool.
