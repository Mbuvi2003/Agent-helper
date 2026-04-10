"""
Agent Helper - Call Center Support Desktop App
Main UI using Tkinter.

Workflow:
1. Search / pick issue (e.g. SIM Swap)
2. Paste CRM screen → app extracts vetting fields
3. Manually enter Serial No (if needed)
4. App builds copy-ready interaction text with only filled fields + notes
5. Copy to clipboard → paste into CRM
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import re
from datetime import datetime

try:
    import pyperclip
except ImportError:
    pyperclip = None

try:
    import keyboard as kb
except ImportError:
    kb = None

from data_loader import DataLoader
from issue_engine import IssueEngine
from vetting_engine import VettingEngine
from resolution_engine import ResolutionEngine
from snippet_engine import SnippetEngine
from text_utils import extract_sdp_codes
from updater import check_for_update, download_and_apply


# Preferred category display order (most frequent first).
# Categories not in this list are appended alphabetically at the end.
CATEGORY_ORDER = [
    'SIM SWAP', 'MPESA', 'LNM', 'LINE ISSUES', 'PIN',
    'SDP', 'REVERSAL', 'GENERAL',
]


class AgentHelperUI:
    """Main Tkinter UI for Agent Helper."""

    def __init__(self, root):
        self.root = root
        self.root.title("Agent Helper - Call Center Assistant")
        self.root.minsize(1100, 700)

        # Set window & taskbar icon
        try:
            import sys
            from pathlib import Path
            if getattr(sys, 'frozen', False):
                _base = Path(sys.executable).parent
            else:
                _base = Path(__file__).parent
            _ico = _base / 'images' / 'icon.ico'
            if _ico.exists():
                self.root.iconbitmap(str(_ico))
        except Exception:
            pass

        # Data & engines
        self.data_loader = DataLoader("data")
        all_data = self.data_loader.load_all()
        self.issue_engine = IssueEngine(all_data)
        self.vetting_engine = VettingEngine()
        self.resolution_engine = ResolutionEngine(all_data)
        self.snippet_engine = SnippetEngine(all_data)

        # State
        self.current_issue = None
        self.current_raw_issue = None
        self.extracted_fields = {}
        self.search_results = []
        self.note_vars = []  # dynamic checkbutton vars for interaction notes
        self.field_entries = {}  # field_key → StringVar for editable entry widgets
        self.vetting_result_var = tk.StringVar(value='pass')
        self.vetting_issue_code = None  # set when a vetting-flow issue is selected
        self.extracted_codes = []  # SDP codes extracted from CRM paste
        self._last_crm_text = ''   # raw CRM text from clipboard
        self._search_after_id = None  # debounce id for live search
        self._reversal_txn_code = ''  # M-PESA transaction code for reversals

        # Restore window geometry from settings (or use default)
        settings = all_data.get('settings', {})
        geo = settings.get('window_geometry')
        if geo:
            try:
                self.root.geometry(geo)
            except Exception:
                self.root.geometry("1450x880")
        else:
            self.root.geometry("1450x880")

        # History / favorites data
        self._history = all_data.get('history', {})
        if not isinstance(self._history, dict):
            self._history = {}
        self._favorites = all_data.get('favorites', {})
        if not isinstance(self._favorites, dict):
            self._favorites = {}
        self._history.setdefault('recent_issues', [])
        self._favorites.setdefault('favorite_issues', [])

        self._compact_mode = False
        self._full_geometry = None

        self._build_ui()
        self._bind_shortcuts()
        self._register_global_hotkey()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._last_clipboard = ""  # for clipboard polling
        self._poll_clipboard()
        self._check_update_async()

    # ─── UI BUILD ────────────────────────────────────────────────

    def _build_ui(self):
        # ── Top bar ──
        self._top_bar = ttk.Frame(self.root)
        self._top_bar.pack(side=tk.TOP, fill=tk.X, padx=10, pady=6)
        top = self._top_bar

        ttk.Label(top, text="Agent Helper", font=("Arial", 15, "bold")).pack(side=tk.LEFT, padx=5)
        _ver_str = self.data_loader.load_json('settings.json').get('version', '')
        if _ver_str:
            ttk.Label(top, text=f"v{_ver_str}", font=("Arial", 8), foreground="gray").pack(side=tk.LEFT, padx=0)

        # Search controls (hidden in compact mode)
        self._search_frame = ttk.Frame(top)
        self._search_frame.pack(side=tk.LEFT)
        ttk.Label(self._search_frame, text="Issue search:", font=("Arial", 10)).pack(side=tk.LEFT, padx=10)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(self._search_frame, textvariable=self.search_var, width=30)
        self.search_entry.pack(side=tk.LEFT, padx=4)
        self.search_entry.bind("<Return>", self._on_search)
        self.search_var.trace_add('write', self._on_search_typed)
        ttk.Button(self._search_frame, text="Search", command=self._on_search).pack(side=tk.LEFT, padx=4)
        ttk.Button(self._search_frame, text="Clear All", command=self._on_clear).pack(side=tk.LEFT, padx=4)

        # Calling Number (hidden in compact mode)
        self._calling_frame = ttk.Frame(top)
        self._calling_frame.pack(side=tk.LEFT)
        ttk.Separator(self._calling_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=10, fill=tk.Y)
        ttk.Label(self._calling_frame, text="Calling No:", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=2)
        self.calling_no_var = tk.StringVar(value="—")
        ttk.Label(self._calling_frame, textvariable=self.calling_no_var, font=("Consolas", 11),
                  foreground="blue", width=12).pack(side=tk.LEFT, padx=2)
        ttk.Button(self._calling_frame, text="Copy", command=self._copy_calling_no).pack(side=tk.LEFT, padx=2)

        # Check for updates button (far right)
        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.RIGHT, padx=8, fill=tk.Y)
        ttk.Button(top, text="⟳ Updates", command=self._manual_check_update).pack(side=tk.RIGHT, padx=4)
        self._compact_btn = ttk.Button(top, text="▫ Mini", command=self._toggle_compact)
        self._compact_btn.pack(side=tk.RIGHT, padx=4)

        # ── Main 3-column content ──
        body = ttk.Frame(self.root)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
        self._body_frame = body

        # --- LEFT: categories + search results + guidance ---
        self._left_panel = ttk.Frame(body, width=260)
        self._left_panel.pack(side=tk.LEFT, fill=tk.BOTH, padx=4)
        self._left_panel.pack_propagate(False)
        left = self._left_panel

        cat_frame = ttk.LabelFrame(left, text="Categories")
        cat_frame.pack(fill=tk.X, padx=2, pady=2)
        for cat in self._ordered_categories():
            ttk.Button(cat_frame, text=cat,
                       command=lambda c=cat: self._on_category(c)).pack(fill=tk.X, padx=4, pady=1)

        # Favorites
        fav_frame = ttk.LabelFrame(left, text="★ Favorites")
        fav_frame.pack(fill=tk.X, padx=2, pady=2)
        self.fav_listbox = tk.Listbox(fav_frame, height=3)
        self.fav_listbox.pack(fill=tk.X, padx=4, pady=2)
        self.fav_listbox.bind("<<ListboxSelect>>", self._on_fav_select)

        self._refresh_fav_recent()

        res_frame = ttk.LabelFrame(left, text="Results")
        res_frame.pack(fill=tk.X, padx=2, pady=4)
        self.results_listbox = tk.Listbox(res_frame, height=8)
        self.results_listbox.pack(fill=tk.X, padx=4, pady=4)
        self.results_listbox.bind("<<ListboxSelect>>", self._on_result_select)

        # Guidance panel (populated when issue selected)
        guide_frame = ttk.LabelFrame(left, text="Guidance / Instructions")
        guide_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=4)

        guide_search_frame = ttk.Frame(guide_frame)
        guide_search_frame.pack(fill=tk.X, padx=4, pady=(4, 0))
        ttk.Label(guide_search_frame, text="Filter:", font=("Arial", 8)).pack(side=tk.LEFT)
        self.guidance_filter_var = tk.StringVar()
        guide_filter_entry = ttk.Entry(guide_search_frame, textvariable=self.guidance_filter_var, width=20)
        guide_filter_entry.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)
        self.guidance_filter_var.trace_add('write', lambda *_: self._filter_guidance())

        self.guidance_text = scrolledtext.ScrolledText(guide_frame, height=10, wrap=tk.WORD,
                                                        font=("Consolas", 9), cursor="hand2")
        self.guidance_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.guidance_text.bind("<Button-1>", self._on_guidance_click)
        self._current_guidance = []  # store full list for filtering
        self._guidance_line_map = {}  # line_number -> original guidance text

        # --- CENTRE: CRM paste + extracted fields ---
        self._centre_panel = ttk.Frame(body)
        self._centre_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
        centre = self._centre_panel

        # Issue label
        self.issue_label_var = tk.StringVar(value="No issue selected")
        ttk.Label(centre, textvariable=self.issue_label_var,
                  font=("Arial", 11, "bold")).pack(anchor=tk.W, pady=2)

        # Paste CRM button (reads clipboard + auto-extracts)
        paste_frame = ttk.Frame(centre)
        paste_frame.pack(fill=tk.X, pady=4)
        ttk.Button(paste_frame, text="📋 Paste CRM / View 360 Data",
                   command=self._on_paste_and_extract).pack(side=tk.LEFT, padx=4, pady=2)

        # Step 2: Dynamic fields area (content rebuilt per issue type)
        self.fields_frame = ttk.LabelFrame(centre, text="Step 2 — Vetting Fields")
        self.fields_frame.pack(fill=tk.BOTH, expand=True, pady=4)
        self.serial_var = tk.StringVar()
        self._build_generic_fields()

        # --- RIGHT: interaction output ---
        self._right_panel = ttk.Frame(body, width=400)
        self._right_panel.pack(side=tk.LEFT, fill=tk.BOTH, padx=4)
        self._right_panel.pack_propagate(False)
        right = self._right_panel

        out_frame = ttk.LabelFrame(right, text="Step 3 — Interaction Output (copy → paste into CRM)")
        out_frame.pack(fill=tk.BOTH, expand=True, pady=4)

        # Dynamic interaction notes (populated per issue)
        self.notes_frame = ttk.LabelFrame(out_frame, text="Interaction Notes")
        self.notes_frame.pack(fill=tk.X, padx=4, pady=4)
        self._default_notes_label = ttk.Label(self.notes_frame, text="Select an issue to see notes",
                                               foreground="gray")
        self._default_notes_label.pack(anchor=tk.W, padx=4)

        # Custom note
        custom_frame = ttk.Frame(out_frame)
        custom_frame.pack(fill=tk.X, padx=4, pady=2)
        ttk.Label(custom_frame, text="Extra note:").pack(side=tk.LEFT)
        self.custom_note_var = tk.StringVar()
        self.custom_note_var.trace_add('write', lambda *_: self._on_field_changed())
        ttk.Entry(custom_frame, textvariable=self.custom_note_var, width=35).pack(side=tk.LEFT, padx=4)

        self.output_text = scrolledtext.ScrolledText(out_frame, height=14, wrap=tk.WORD)
        self.output_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        btn_row2 = ttk.Frame(out_frame)
        btn_row2.pack(fill=tk.X, padx=4, pady=4)
        ttk.Button(btn_row2, text="Copy Output", command=self._on_copy_output).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_row2, text="Copy Serial No", command=self._on_copy_serial).pack(side=tk.LEFT, padx=2)
        self.fav_btn = ttk.Button(btn_row2, text="★ Fav", command=self._toggle_favorite)
        self.fav_btn.pack(side=tk.LEFT, padx=2)

        # ── Status bar ──
        self.status_var = tk.StringVar(value="Ready — select an issue and paste CRM data")
        ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN).pack(
            side=tk.BOTTOM, fill=tk.X, padx=5, pady=4)

    # ─── COMPACT MODE ────────────────────────────────────────────

    def _toggle_compact(self):
        if self._compact_mode:
            self._exit_compact()
        else:
            self._enter_compact()

    def _enter_compact(self):
        self._compact_mode = True
        self._full_geometry = self.root.geometry()

        # Preserve current field values so they survive the mode switch
        for key, var in self.field_entries.items():
            val = var.get().strip()
            if val:
                self.extracted_fields[key] = val

        # Save original widget references
        self._full = {
            'results_listbox': self.results_listbox,
            'output_text': self.output_text,
            'fav_listbox': self.fav_listbox,
            'guidance_text': self.guidance_text,
            'fields_frame': self.fields_frame,
            'notes_frame': self.notes_frame,
        }
        if hasattr(self, 'fields_text'):
            self._full['fields_text'] = self.fields_text

        # Hide original layout
        self._top_bar.pack_forget()
        self._body_frame.pack_forget()

        # Build compact UI (creates new widgets, swaps references)
        self._build_compact_ui()

        # Phone-sized window, snapped to left edge, full screen height
        screen_h = self.root.winfo_screenheight() - 80
        self.root.geometry(f"400x{screen_h}+0+0")
        self.root.minsize(340, 500)

        # Replay current state into compact widgets
        self._refresh_fav_recent()
        if self.search_results:
            self._update_results()
        if self.current_issue:
            self._apply_selected_issue()
            # Re-populate field values that were saved
            if self.vetting_issue_code:
                self._populate_vetting_entries()
        if self._current_guidance:
            self._filter_guidance()

    def _build_compact_ui(self):
        """Build a vertically-stacked compact UI with full functionality."""
        # Scrollable container
        outer = ttk.Frame(self.root)
        outer.pack(fill=tk.BOTH, expand=True)
        self._compact_frame = outer

        canvas = tk.Canvas(outer, highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        inner = ttk.Frame(canvas)
        inner_id = canvas.create_window((0, 0), window=inner, anchor='nw')

        def _on_configure(e):
            canvas.configure(scrollregion=canvas.bbox('all'))
        inner.bind('<Configure>', _on_configure)
        def _on_canvas_configure(e):
            canvas.itemconfig(inner_id, width=e.width)
        canvas.bind('<Configure>', _on_canvas_configure)
        # Mouse-wheel scrolling
        def _on_mousewheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), 'units')
        canvas.bind_all('<MouseWheel>', _on_mousewheel)
        self._compact_canvas = canvas

        cf = inner  # shorthand

        # ── Row 1: Title + Search + Pin + Full button ──
        top = ttk.Frame(cf)
        top.pack(fill=tk.X, padx=4, pady=(4, 2))
        ttk.Label(top, text="Agent Helper", font=("Arial", 11, "bold")).pack(side=tk.LEFT)
        ttk.Button(top, text="▣ Full", width=5, command=self._toggle_compact).pack(side=tk.RIGHT, padx=2)
        self._pin_btn = ttk.Button(top, text="\U0001F4CC", width=3, command=self._toggle_pin)
        self._pin_btn.pack(side=tk.RIGHT, padx=2)
        se = ttk.Entry(top, textvariable=self.search_var, width=12)
        se.pack(side=tk.RIGHT, padx=2)
        se.bind("<Return>", self._on_search)
        ttk.Label(top, text="\U0001F50D").pack(side=tk.RIGHT)

        # ── Row 2: 3 pinned issue buttons (direct select, no extra click) ──
        cat_row = ttk.Frame(cf)
        cat_row.pack(fill=tk.X, padx=4, pady=2)
        for label, code in [('SIM SWAP', 'SIM_SWAP'), ('START KEY', 'MPESA_STARTKEY_PIN'), ('REVERSAL', 'REVERSAL')]:
            ttk.Button(cat_row, text=label,
                       command=lambda c=code: self._select_issue_by_code(c)).pack(
                           side=tk.LEFT, expand=True, fill=tk.X, padx=1)

        # ── Row 3: Paste CRM + Calling No ──
        paste_row = ttk.Frame(cf)
        paste_row.pack(fill=tk.X, padx=4, pady=2)
        ttk.Button(paste_row, text="\U0001F4CB Paste CRM",
                   command=self._on_paste_and_extract).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Label(paste_row, text="\U0001F4DE").pack(side=tk.LEFT)
        ttk.Label(paste_row, textvariable=self.calling_no_var,
                  font=("Consolas", 9), foreground="blue").pack(side=tk.LEFT, padx=2)
        ttk.Button(paste_row, text="Copy", width=5,
                   command=self._copy_calling_no).pack(side=tk.LEFT, padx=2)

        # ── Row 4: Results + Favorites side-by-side ──
        rf_row = ttk.Frame(cf)
        rf_row.pack(fill=tk.X, padx=4, pady=2)
        rf_row.columnconfigure(0, weight=1)
        rf_row.columnconfigure(1, weight=1)

        res_lf = ttk.LabelFrame(rf_row, text="Results")
        res_lf.grid(row=0, column=0, sticky='nsew', padx=(0, 2))
        self.results_listbox = tk.Listbox(res_lf, height=2, font=("Arial", 8))
        self.results_listbox.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.results_listbox.bind("<<ListboxSelect>>", self._on_result_select)

        fav_lf = ttk.LabelFrame(rf_row, text="\u2605 Favs")
        fav_lf.grid(row=0, column=1, sticky='nsew', padx=(2, 0))
        self.fav_listbox = tk.Listbox(fav_lf, height=2, font=("Arial", 8))
        self.fav_listbox.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.fav_listbox.bind("<<ListboxSelect>>", self._on_fav_select)

        # ── Row 5: Guidance (small) with filter ──
        guide_lf = ttk.LabelFrame(cf, text="Guidance")
        guide_lf.pack(fill=tk.X, padx=4, pady=2)
        guide_filter_row = ttk.Frame(guide_lf)
        guide_filter_row.pack(fill=tk.X, padx=2, pady=(2, 0))
        ttk.Label(guide_filter_row, text="Filter:", font=("Arial", 7)).pack(side=tk.LEFT)
        guide_filter = ttk.Entry(guide_filter_row, textvariable=self.guidance_filter_var, width=20)
        guide_filter.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        self.guidance_text = scrolledtext.ScrolledText(
            guide_lf, height=3, wrap=tk.WORD, font=("Consolas", 8), cursor="hand2")
        self.guidance_text.pack(fill=tk.X, padx=2, pady=2)
        self.guidance_text.bind("<Button-1>", self._on_guidance_click)

        # ── Row 6: Issue label ──
        ttk.Label(cf, textvariable=self.issue_label_var,
                  font=("Arial", 10, "bold")).pack(anchor=tk.W, padx=4, pady=(4, 0))

        # ── Row 7: Vetting Fields (MAIN area) ──
        self.fields_frame = ttk.LabelFrame(cf, text="Vetting Fields")
        self.fields_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)

        # ── Row 8: Vetting Result (radio buttons) + Notes ──
        self.notes_frame = ttk.LabelFrame(cf, text="Vetting Result")
        self.notes_frame.pack(fill=tk.X, padx=4, pady=2)

        # ── Row 9: Extra note + action buttons ──
        act_row = ttk.Frame(cf)
        act_row.pack(fill=tk.X, padx=4, pady=2)
        ttk.Label(act_row, text="Note:", font=("Arial", 8)).pack(side=tk.LEFT)
        ttk.Entry(act_row, textvariable=self.custom_note_var, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Button(act_row, text="\U0001F4CB Serial", command=self._on_copy_serial).pack(side=tk.LEFT, padx=2)
        ttk.Button(act_row, text="\U0001F4CB Output", command=self._on_copy_output).pack(side=tk.LEFT, padx=2)
        ttk.Button(act_row, text="\u2605", width=2, command=self._toggle_favorite).pack(side=tk.LEFT, padx=2)

        # ── Row 10: Output ──
        out_lf = ttk.LabelFrame(cf, text="Interaction Output")
        out_lf.pack(fill=tk.X, padx=4, pady=(2, 4))
        self.output_text = scrolledtext.ScrolledText(
            out_lf, height=7, wrap=tk.WORD, font=("Consolas", 8))
        self.output_text.pack(fill=tk.X, padx=2, pady=2)

    def _toggle_pin(self):
        """Toggle always-on-top (pin) for the compact window."""
        self._pinned = not getattr(self, '_pinned', False)
        self.root.attributes('-topmost', self._pinned)
        self._pin_btn.configure(text="\U0001F4CD" if self._pinned else "\U0001F4CC")

    def _exit_compact(self):
        self._compact_mode = False

        # Disable pin if active
        self._pinned = False
        self.root.attributes('-topmost', False)

        # Preserve current field values
        for key, var in self.field_entries.items():
            val = var.get().strip()
            if val:
                self.extracted_fields[key] = val

        # Unbind mousewheel from compact canvas
        try:
            self._compact_canvas.unbind_all('<MouseWheel>')
        except Exception:
            pass

        # Destroy compact frame
        if hasattr(self, '_compact_frame') and self._compact_frame:
            self._compact_frame.destroy()
            self._compact_frame = None

        # Restore original widget references
        self.results_listbox = self._full['results_listbox']
        self.output_text = self._full['output_text']
        self.fav_listbox = self._full['fav_listbox']
        self.guidance_text = self._full['guidance_text']
        self.fields_frame = self._full['fields_frame']
        self.notes_frame = self._full['notes_frame']
        if 'fields_text' in self._full:
            self.fields_text = self._full['fields_text']

        # Show original layout
        self._top_bar.pack(side=tk.TOP, fill=tk.X, padx=10, pady=6)
        self._body_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

        # Restore size
        self.root.minsize(1100, 700)
        if self._full_geometry:
            self.root.geometry(self._full_geometry)
        self._compact_btn.configure(text="\u25ab Mini")

        # Replay state into original widgets
        self._refresh_fav_recent()
        if self.search_results:
            self._update_results()
        if self.current_issue:
            self._apply_selected_issue()
            if self.vetting_issue_code:
                self._populate_vetting_entries()
        if self._current_guidance:
            self._filter_guidance()

    # ─── KEYBOARD SHORTCUTS ──────────────────────────────────────

    def _bind_shortcuts(self):
        """Register in-app keyboard shortcuts."""
        self.root.bind('<Control-v>', self._shortcut_paste_extract)
        self.root.bind('<Control-V>', self._shortcut_paste_extract)
        self.root.bind('<Control-c>', self._shortcut_copy_output)
        self.root.bind('<Control-C>', self._shortcut_copy_output)

    def _register_global_hotkey(self):
        """Register Win+A as a system-wide hotkey to bring the app to front."""
        if kb:
            try:
                kb.add_hotkey('win+a', self._request_bring_to_front, suppress=True)
            except Exception:
                pass  # non-critical if it fails

    def _request_bring_to_front(self):
        """Schedule bring-to-front on the Tkinter main thread."""
        self.root.after(0, self._bring_to_front)

    def _bring_to_front(self):
        """Bring the app window to the foreground."""
        self.root.deiconify()
        self.root.attributes('-topmost', True)
        self.root.focus_force()
        self.root.after(100, lambda: self.root.attributes('-topmost', False))
        # If serial auto-copy is armed, fire it now (mouse-paste workflow)
        if getattr(self, '_serial_auto_copy_armed', False):
            self._serial_auto_copy_armed = False
            try:
                kb.unhook_key('v')
            except Exception:
                pass
            self.root.after(100, self._auto_copy_output_after_serial)

    def _shortcut_paste_extract(self, event=None):
        """Ctrl+V: paste CRM data and extract in one step (unless a text widget has focus)."""
        focused = self.root.focus_get()
        # If focus is in any Entry or Text widget, let normal paste work
        if isinstance(focused, (tk.Entry, tk.Text, ttk.Entry, scrolledtext.ScrolledText)):
            return  # let default handler run
        self._on_paste_and_extract()
        return 'break'

    def _shortcut_copy_output(self, event=None):
        """Ctrl+C: copy output text (unless a text widget has a selection)."""
        focused = self.root.focus_get()
        if isinstance(focused, (tk.Text, scrolledtext.ScrolledText)):
            try:
                if focused.tag_ranges(tk.SEL):
                    return  # let default copy-selection work
            except Exception:
                pass
        if isinstance(focused, (tk.Entry, ttk.Entry)):
            return  # let default copy work in entries
        text = self.output_text.get("1.0", tk.END).strip()
        if text:
            self._copy(text)
            self._set_status("Output copied to clipboard (Ctrl+C)")
        return 'break'

    # ─── CATEGORY ORDERING ───────────────────────────────────────

    def _ordered_categories(self):
        """Return categories in preferred display order."""
        all_cats = self.issue_engine.get_categories()
        ordered = [c for c in CATEGORY_ORDER if c in all_cats]
        remaining = sorted(c for c in all_cats if c not in ordered)
        return ordered + remaining

    # ─── FAVORITES / RECENT ──────────────────────────────────────

    def _refresh_fav_recent(self):
        """Refresh the favorites listbox."""
        self.fav_listbox.delete(0, tk.END)
        for code in self._favorites.get('favorite_issues', []):
            issue = self._find_issue_by_code(code)
            if issue:
                self.fav_listbox.insert(tk.END, issue.get('display_name', code))

    def _find_issue_by_code(self, code):
        """Find raw issue dict by issue_code."""
        for issue in self.issue_engine.issues:
            if issue.get('issue_code') == code:
                return issue
        return None

    def _record_recent(self, issue_code):
        """Add an issue to the recent list (most recent first, max 10)."""
        recent = self._history.get('recent_issues', [])
        if issue_code in recent:
            recent.remove(issue_code)
        recent.insert(0, issue_code)
        self._history['recent_issues'] = recent[:10]
        self._refresh_fav_recent()

    def _toggle_favorite(self):
        """Toggle current issue as a favorite."""
        if not self.current_raw_issue:
            return
        code = self.current_raw_issue.get('issue_code')
        favs = self._favorites.get('favorite_issues', [])
        if code in favs:
            favs.remove(code)
            self._set_status(f"Removed from favorites")
        else:
            favs.insert(0, code)
            self._set_status(f"Added to favorites")
        self._favorites['favorite_issues'] = favs
        self._refresh_fav_recent()

    def _on_fav_select(self, event):
        sel = self.fav_listbox.curselection()
        if not sel:
            return
        favs = self._favorites.get('favorite_issues', [])
        if sel[0] < len(favs):
            self._select_issue_by_code(favs[sel[0]])

    def _select_issue_by_code(self, code):
        """Programmatically select an issue by its code."""
        issue_raw = self._find_issue_by_code(code)
        if not issue_raw:
            return
        self.current_issue = {
            'issue_code': issue_raw['issue_code'],
            'display_name': issue_raw['display_name'],
            'category': issue_raw['category'],
            'confidence': 100,
            'matched_terms': 'direct',
            'raw_issue': issue_raw,
        }
        self.current_raw_issue = issue_raw
        self._apply_selected_issue()

    # ─── ISSUE SELECTION ─────────────────────────────────────────

    def _on_search(self, event=None):
        q = self.search_var.get().strip()
        if q:
            threading.Thread(target=self._do_search, args=(q,), daemon=True).start()

    def _on_search_typed(self, *args):
        """Debounced live search triggered on every keystroke."""
        if self._search_after_id:
            self.root.after_cancel(self._search_after_id)
        self._search_after_id = self.root.after(300, self._on_search)

    def _do_search(self, query):
        self.search_results = self.issue_engine.get_top_matches(query, limit=8)
        self.root.after(0, self._update_results)

    def _on_category(self, category):
        issues = self.issue_engine.get_issues_by_category(category)
        self.search_results = [
            {'issue_code': i['issue_code'], 'display_name': i['display_name'],
             'category': i['category'], 'confidence': 100,
             'matched_terms': 'category', 'raw_issue': i}
            for i in issues]
        self._update_results()
        # Auto-select if only one result in category
        if len(self.search_results) == 1:
            self.results_listbox.selection_set(0)
            self.current_issue = self.search_results[0]
            self.current_raw_issue = self.current_issue.get('raw_issue', {})
            self._apply_selected_issue()

    def _update_results(self):
        self.results_listbox.delete(0, tk.END)
        for r in self.search_results:
            self.results_listbox.insert(tk.END,
                f"{r['display_name']}")

    def _on_result_select(self, event):
        sel = self.results_listbox.curselection()
        if not sel:
            return
        self.current_issue = self.search_results[sel[0]]
        self.current_raw_issue = self.current_issue.get('raw_issue', {})
        self._apply_selected_issue()

    def _apply_selected_issue(self):
        """Shared logic after an issue is selected (from results, fav, or recent)."""
        name = self.current_issue['display_name']
        self.issue_label_var.set(f"Issue: {name}")
        self._set_status(f"Issue selected: {name}")

        # Record in recent history
        issue_code = self.current_raw_issue.get('issue_code', '')
        self._record_recent(issue_code)

        # Update guidance panel
        self._show_guidance()

        # Detect vetting flow issues (have pass/fail_primary/fail_secondary)
        issue_code = self.current_raw_issue.get('issue_code', '')
        if issue_code in self.vetting_engine.VETTING_CONFIGS:
            self.vetting_issue_code = issue_code
            self._build_vetting_fields(issue_code)
            self._build_vetting_notes()
        else:
            self.vetting_issue_code = None
            self._build_generic_fields()
            self._build_interaction_notes()

        self._rebuild_output()

    def _show_guidance(self):
        self._current_guidance = self.current_raw_issue.get('guidance', [])
        self.guidance_filter_var.set('')
        self._filter_guidance()

    def _filter_guidance(self):
        self.guidance_text.delete("1.0", tk.END)
        self._guidance_line_map = {}
        query = self.guidance_filter_var.get().strip().lower()
        guidance = self._current_guidance
        if not guidance:
            self.guidance_text.insert(tk.END, "No guidance available for this issue.")
            return
        shown = 0
        text_line = 1  # track which text widget line each entry starts on
        for i, line in enumerate(guidance, 1):
            if not query or query in line.lower():
                self.guidance_text.insert(tk.END, f"– {line}\n\n")
                self._guidance_line_map[text_line] = line
                text_line += 2  # each entry is 2 lines (text + blank)
                shown += 1
        if shown == 0:
            self.guidance_text.insert(tk.END, "No matching guidance.")
        self.guidance_text.config(state=tk.NORMAL)

    def _on_guidance_click(self, event):
        """Copy the clicked guidance line to clipboard."""
        index = self.guidance_text.index(f"@{event.x},{event.y}")
        line_num = int(index.split(".")[0])
        # Find the guidance entry that owns this line
        best_key = None
        for key in sorted(self._guidance_line_map.keys()):
            if key <= line_num:
                best_key = key
            else:
                break
        if best_key is not None:
            text = self._guidance_line_map[best_key]
            self._copy(text)
            self._set_status(f"Copied: {text[:60]}{'...' if len(text) > 60 else ''}")

    def _build_interaction_notes(self):
        """Rebuild interaction note checkboxes from the selected issue's notes."""
        # Clear existing checkbuttons
        for widget in self.notes_frame.winfo_children():
            widget.destroy()
        self.note_vars = []

        notes = self.current_raw_issue.get('interaction_notes', [])
        if not notes:
            ttk.Label(self.notes_frame, text="No predefined notes for this issue",
                      foreground="gray").pack(anchor=tk.W, padx=4)
            return

        for note_text in notes:
            var = tk.BooleanVar(value=False)
            self.note_vars.append((note_text, var))
            ttk.Checkbutton(self.notes_frame, text=note_text, variable=var,
                            command=(lambda v=var: self._on_note_toggle(v))).pack(anchor=tk.W, padx=4, pady=1)

    def _on_note_toggle(self, toggled_var: tk.BooleanVar):
        """Ensure only one interaction note checkbox is selected at a time.

        When a checkbox is toggled on, untick all others. Then rebuild output.
        """
        try:
            state = toggled_var.get()
        except Exception:
            state = False
        if state:
            # untick all other vars
            for _, var in self.note_vars:
                if var is not toggled_var:
                    try:
                        var.set(False)
                    except Exception:
                        pass
        # Rebuild output to reflect new selection
        self._rebuild_output()

    # ─── SIM SWAP WORKFLOW ────────────────────────────────────────

    def _build_generic_fields(self):
        """Build the generic extracted fields display (non-SIM-Swap)."""
        for widget in self.fields_frame.winfo_children():
            widget.destroy()
        self.field_entries = {}
        self.fields_frame.config(text="Step 2 — Extracted Vetting Fields")

        self.fields_text = scrolledtext.ScrolledText(self.fields_frame, height=8, wrap=tk.WORD)
        self.fields_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        serial_frame = ttk.Frame(self.fields_frame)
        serial_frame.pack(fill=tk.X, padx=4, pady=2)
        ttk.Label(serial_frame, text="Serial No (manual):").pack(side=tk.LEFT, padx=2)
        ttk.Entry(serial_frame, textvariable=self.serial_var, width=25).pack(side=tk.LEFT, padx=4)
        ttk.Button(serial_frame, text="Add Serial & Refresh",
                   command=self._on_add_serial).pack(side=tk.LEFT, padx=4)

    def _build_vetting_fields(self, issue_code):
        """Build editable field entries for any vetting-flow issue."""
        for widget in self.fields_frame.winfo_children():
            widget.destroy()
        self.field_entries = {}

        display_name = self.current_raw_issue.get('display_name', issue_code)
        self.fields_frame.config(text=f"Step 2 — {display_name} Vetting Fields")

        inner = ttk.Frame(self.fields_frame)
        inner.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # Determine which fields come from CRM extraction vs manual
        auto_keys = {'Name', 'ID', 'YOB', 'MPESA', 'Airtime'}
        config = self.vetting_engine.VETTING_CONFIGS.get(issue_code, {})
        output_field_attr = config.get('output_fields', '')
        output_fields = getattr(self.vetting_engine, output_field_attr, [])

        if config.get('manual_only'):
            auto_fields = []
            manual_fields = list(output_fields)
        else:
            auto_fields = [(lbl, key) for lbl, key in output_fields if key in auto_keys]
            manual_fields = [(lbl, key) for lbl, key in output_fields if key not in auto_keys]

        row = 0
        if auto_fields:
            ttk.Label(inner, text="\u2500\u2500 Auto-extracted (from CRM paste) \u2500\u2500",
                      font=("Arial", 8, "bold"), foreground="blue").grid(
                row=row, column=0, columnspan=2, sticky=tk.W, pady=(0, 2))
            row += 1

        for label, key in auto_fields:
            ttk.Label(inner, text=f"{label}:", font=("Arial", 9)).grid(
                row=row, column=0, sticky=tk.E, padx=(4, 4), pady=1)
            var = tk.StringVar()
            ttk.Entry(inner, textvariable=var, width=35).grid(
                row=row, column=1, sticky=tk.W, padx=2, pady=1)
            self.field_entries[key] = var
            row += 1

        if manual_fields and auto_fields:
            ttk.Label(inner, text="\u2500\u2500 Manual entry (if customer can't confirm balances) \u2500\u2500",
                      font=("Arial", 8, "bold"), foreground="gray").grid(
                row=row, column=0, columnspan=2, sticky=tk.W, pady=(6, 2))
            row += 1

        for label, key in manual_fields:
            ttk.Label(inner, text=f"{label}:", font=("Arial", 9)).grid(
                row=row, column=0, sticky=tk.E, padx=(4, 4), pady=1)
            if key == 'Serial No':
                var = self.serial_var
                var.set('89254021')
                serial_frame = ttk.Frame(inner)
                serial_frame.grid(row=row, column=1, sticky=tk.W, padx=2, pady=1)
                ttk.Entry(serial_frame, textvariable=var, width=25).pack(side=tk.LEFT)
                self._serial_counter_var = tk.StringVar(value="8/20")
                counter_lbl = ttk.Label(serial_frame, textvariable=self._serial_counter_var,
                                        font=("Arial", 8))
                counter_lbl.pack(side=tk.LEFT, padx=4)
                def _update_serial_counter(*_):
                    n = len(self.serial_var.get())
                    self._serial_counter_var.set(f"{n}/20")
                    if n == 20:
                        counter_lbl.configure(foreground="green")
                    elif n > 20:
                        counter_lbl.configure(foreground="red")
                    else:
                        counter_lbl.configure(foreground="gray")
                var.trace_add('write', _update_serial_counter)
                _update_serial_counter()
            else:
                var = tk.StringVar()
                ttk.Entry(inner, textvariable=var, width=35).grid(
                    row=row, column=1, sticky=tk.W, padx=2, pady=1)
            self.field_entries[key] = var
            row += 1

        # Auto-rebuild output whenever any field changes
        self._attach_field_traces()

    def _attach_field_traces(self):
        """Add write traces to all field entry vars so output auto-updates."""
        self._field_trace_ids = []
        for key, var in self.field_entries.items():
            tid = var.trace_add('write', self._on_field_changed)
            self._field_trace_ids.append((var, tid))

    def _on_field_changed(self, *_):
        """Debounced auto-rebuild of output when any Step 2 field changes."""
        if hasattr(self, '_field_rebuild_id'):
            self.root.after_cancel(self._field_rebuild_id)
        self._field_rebuild_id = self.root.after(300, self._rebuild_output)

    def _build_vetting_notes(self):
        """Build vetting result radio buttons for any vetting-flow issue."""
        for widget in self.notes_frame.winfo_children():
            widget.destroy()
        self.note_vars = []
        self.notes_frame.config(text="Vetting Result")
        self.vetting_result_var.set('pass')

        row = ttk.Frame(self.notes_frame)
        row.pack(fill=tk.X, padx=4, pady=2)

        ttk.Radiobutton(row, text="Pass",
                        variable=self.vetting_result_var, value='pass',
                        command=self._rebuild_output).pack(side=tk.LEFT, padx=4)

        config = self.vetting_engine.VETTING_CONFIGS.get(self.vetting_issue_code, {})
        if config.get('fail_secondary_header'):
            ttk.Radiobutton(row, text="Fail Secondary",
                            variable=self.vetting_result_var, value='fail_secondary',
                            command=self._rebuild_output).pack(side=tk.LEFT, padx=4)

        ttk.Radiobutton(row, text="Fail Primary",
                        variable=self.vetting_result_var, value='fail_primary',
                        command=self._rebuild_output).pack(side=tk.LEFT, padx=4)

    def _populate_vetting_entries(self):
        """Fill vetting entry widgets from extracted_fields."""
        for key, var in self.field_entries.items():
            val = self.extracted_fields.get(key, '')
            if val:
                var.set(val)

    def _gather_vetting_fields(self) -> dict:
        """Collect all vetting field values from entry widgets."""
        fields = {}
        for key, var in self.field_entries.items():
            val = var.get().strip()
            if val:
                fields[key] = val
        return fields

    # ─── CRM PASTE & EXTRACTION ──────────────────────────────────

    def _on_paste_and_extract(self):
        """Single button: read clipboard and auto-extract vetting fields."""
        # Disarm any pending serial auto-copy so it doesn't steal clipboard
        self._serial_auto_copy_armed = False
        if kb:
            try:
                kb.unhook_key('v')
            except Exception:
                pass
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            if pyperclip:
                text = pyperclip.paste()
            else:
                messagebox.showerror("Error", "Clipboard empty or pyperclip not installed")
                return
        if not text or not text.strip():
            messagebox.showwarning("Empty", "Clipboard is empty — copy CRM/View 360 data first")
            return
        self._last_crm_text = text
        self._do_extract(text.strip())

    def _on_paste_crm(self):
        """Legacy: used by Ctrl+V shortcut."""
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            if pyperclip:
                text = pyperclip.paste()
            else:
                return
        self._last_crm_text = text

    def _on_extract(self):
        """Legacy: used by Ctrl+V shortcut."""
        raw = getattr(self, '_last_crm_text', '').strip()
        if not raw:
            return
        self._do_extract(raw)

    def _do_extract(self, raw):
        self.extracted_fields = self.vetting_engine.extract_from_text(raw)

        # Also extract SDP codes for issues that use CODE placeholder
        self.extracted_codes = extract_sdp_codes(raw)

        if self.vetting_issue_code:
            self._populate_vetting_entries()
            # Show feedback on what was/wasn't found
            found = [k for k in self.extracted_fields if self.extracted_fields[k]]
            config = self.vetting_engine.VETTING_CONFIGS.get(self.vetting_issue_code, {})
            required = self.vetting_engine.REQUIRED_BY_ISSUE.get(self.vetting_issue_code, [])
            missing = [f for f in required if f not in found]
            if not found:
                self._set_status("Warning: No fields extracted — check that CRM data is pasted correctly")
            elif missing:
                self._set_status(f"Extracted {len(found)} fields — missing required: {', '.join(missing)}")
            else:
                self._set_status(f"Extracted {len(found)} fields — all required fields found")
        else:
            if self.extracted_codes:
                self._show_extracted_codes()
                self._set_status(f"Extracted {len(self.extracted_codes)} SDP codes: {', '.join(self.extracted_codes)}")
            elif not self.extracted_fields:
                self._set_status("Warning: No fields or codes extracted — check that CRM data is pasted correctly")
            else:
                self._set_status(f"Extracted {len(self.extracted_fields)} fields")
            self._show_extracted()
        self._rebuild_output()

    def _show_extracted(self):
        self.fields_text.delete("1.0", tk.END)
        if not self.extracted_fields:
            self.fields_text.insert("1.0", "(no fields extracted — check CRM data)")
            return

        # Show only fields relevant to current issue if one is selected
        relevant = self.current_raw_issue.get('vetting_fields', []) if self.current_raw_issue else []

        for field in self.vetting_engine.VETTING_FIELDS:
            val = self.extracted_fields.get(field)
            if val:
                marker = ""
                if relevant and field not in relevant:
                    marker = "  (extra)"
                self.fields_text.insert(tk.END, f"{field}: {val}{marker}\n")

        # Show if required fields are missing
        if relevant:
            missing = [f for f in relevant if f not in self.extracted_fields and f != 'Serial No']
            if missing:
                self.fields_text.insert(tk.END, f"\nMissing: {', '.join(missing)}\n")

    def _show_extracted_codes(self):
        """Show extracted SDP codes in the fields area."""
        self.fields_text.delete("1.0", tk.END)
        if not self.extracted_codes:
            self.fields_text.insert("1.0", "(no codes found — check CRM data)")
            return
        self.fields_text.insert(tk.END, "Extracted codes:\n")
        for code in self.extracted_codes:
            self.fields_text.insert(tk.END, f"  {code}\n")

    def _on_add_serial(self):
        sn = self.serial_var.get().strip()
        if sn:
            if not sn.startswith('89254021'):
                sn = '89254021' + sn
                self.serial_var.set(sn)
            self.extracted_fields['Serial No'] = sn
            self._show_extracted()
            self._rebuild_output()
            self._set_status("Serial number added")

    # ─── OUTPUT GENERATION ───────────────────────────────────────

    def _rebuild_output(self):
        if self.vetting_issue_code:
            fields = self._gather_vetting_fields()
            result = self.vetting_result_var.get()
            output = self.vetting_engine.format_vetting_result(fields, result, self.vetting_issue_code)
        else:
            notes = []
            today = datetime.now().strftime("%d/%m/%Y")

            for note_text, var in self.note_vars:
                if var.get():
                    line = note_text
                    # Replace CODE placeholder with extracted SDP codes
                    if 'CODE' in line and self.extracted_codes:
                        line = line.replace('CODE', ', '.join(self.extracted_codes))
                    if line.rstrip().endswith(":"):
                        line = f"{line} {today}"
                    notes.append(line)

            # For REVERSAL: grab txn code from clipboard on-demand
            has_sr = any('SR raised' in n for n in notes)
            issue_code = self.current_raw_issue.get('issue_code', '') if self.current_raw_issue else ''
            if issue_code == 'REVERSAL' and notes and not has_sr:
                # Check clipboard right now for a txn code
                try:
                    clip = self.root.clipboard_get().strip()
                except Exception:
                    clip = ''
                if (clip and re.fullmatch(r'[A-Za-z0-9]{8,12}', clip)
                        and re.search(r'[A-Za-z]', clip)):
                    self._reversal_txn_code = clip.upper()
                if self._reversal_txn_code:
                    notes.insert(0, self._reversal_txn_code)

            custom = self.custom_note_var.get().strip()
            if custom:
                notes.append(custom)

            serial = self.serial_var.get().strip()

            fields_to_output = {}
            relevant = self.current_raw_issue.get('vetting_fields', []) if self.current_raw_issue else []

            if relevant:
                for field in relevant:
                    val = self.extracted_fields.get(field)
                    if val:
                        fields_to_output[field] = val
            else:
                fields_to_output = dict(self.extracted_fields)

            output = self.vetting_engine.format_vetting_output(
                fields_to_output, serial_no=serial,
                issue_label=self.current_issue['display_name'] if self.current_issue else "",
                extra_notes=notes)

        self.output_text.delete("1.0", tk.END)
        self.output_text.insert("1.0", output)

    def _on_copy_output(self):
        text = self.output_text.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("Empty", "Generate output first")
            return
        self._copy(text)
        self._set_status("Interaction output copied to clipboard")

    def _on_copy_serial(self):
        sn = self.serial_var.get().strip()
        if not sn:
            messagebox.showwarning("Empty", "Enter a serial number first")
            return
        self._copy(sn)
        self._set_status("Serial copied — paste it, then output auto-copies (Ctrl+V or Win+A)")
        # Arm auto-copy: triggers on next Ctrl+V (keyboard paste) or Win+A (bring app back)
        if self.vetting_issue_code:
            self._serial_auto_copy_armed = True
            if kb:
                try:
                    kb.on_press_key('v', self._on_global_v_press, suppress=False)
                except Exception:
                    pass

    def _on_global_v_press(self, event):
        """Detect Ctrl+V globally — fire auto-copy if armed."""
        if not getattr(self, '_serial_auto_copy_armed', False):
            return
        # Only trigger on Ctrl+V, not bare 'v' typing
        import keyboard as _kb
        if _kb.is_pressed('ctrl'):
            self._serial_auto_copy_armed = False
            try:
                kb.unhook_key('v')
            except Exception:
                pass
            # Small delay so the paste completes first
            self.root.after(200, self._auto_copy_output_after_serial)

    def _auto_copy_output_after_serial(self):
        """Auto-copy full output to clipboard after serial was copied (SIM SWAP flow)."""
        text = self.output_text.get("1.0", tk.END).strip()
        if text:
            self._copy(text)
            self._set_status("Output auto-copied to clipboard — ready to paste in CRM")

    # ─── CALLING NUMBER ──────────────────────────────────────────

    def _paste_calling_no(self):
        """Read clipboard; if it's exactly a 9-digit number, store it as calling number."""
        try:
            text = self.root.clipboard_get().strip()
        except tk.TclError:
            if pyperclip:
                text = pyperclip.paste().strip()
            else:
                self._set_status("Clipboard empty")
                return
        if re.fullmatch(r'\d{9}', text):
            self.calling_no_var.set(text)
            self._set_status(f"Calling number set: {text}")
        else:
            self._set_status("Clipboard does not contain a 9-digit number")

    def _copy_calling_no(self):
        """Copy the stored calling number back to clipboard."""
        num = self.calling_no_var.get().strip()
        if not num or num == "—":
            self._set_status("No calling number set")
            return
        self._copy(num)
        self._set_status(f"Calling number copied: {num}")

    def _poll_clipboard(self):
        """Poll clipboard every 500ms; auto-detect a 9-digit calling number."""
        try:
            text = self.root.clipboard_get().strip()
        except Exception:
            text = ""
        if text and text != self._last_clipboard:
            self._last_clipboard = text
            if re.fullmatch(r'\d{9}', text):
                self.calling_no_var.set(text)
                self._set_status(f"Calling number auto-detected: {text}")
        self.root.after(500, self._poll_clipboard)

    # ─── HELPERS ─────────────────────────────────────────────────

    def _on_clear(self):
        self.search_var.set("")
        self.results_listbox.delete(0, tk.END)
        self._last_crm_text = ''
        self.output_text.delete("1.0", tk.END)
        self.serial_var.set("")
        self.custom_note_var.set("")
        self.current_issue = None
        self.current_raw_issue = None
        self.extracted_fields = {}
        self.extracted_codes = []
        self._reversal_txn_code = ''
        self.calling_no_var.set("—")
        self.vetting_issue_code = None
        self.field_entries = {}
        self.vetting_result_var.set('pass')
        self.issue_label_var.set("No issue selected")
        self.guidance_text.delete("1.0", tk.END)
        # Reset fields to generic
        self._build_generic_fields()
        # Reset notes
        for widget in self.notes_frame.winfo_children():
            widget.destroy()
        self.note_vars = []
        self.notes_frame.config(text="Interaction Notes")
        ttk.Label(self.notes_frame, text="Select an issue to see notes",
                  foreground="gray").pack(anchor=tk.W, padx=4)
        self._set_status("Cleared")

    def _copy(self, text: str):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
        except Exception:
            if pyperclip:
                pyperclip.copy(text)
            else:
                messagebox.showerror("Error", "Could not copy to clipboard")

    def _set_status(self, msg: str):
        self.status_var.set(msg)

    # ─── AUTO-UPDATE ─────────────────────────────────────────────

    def _manual_check_update(self):
        """Triggered by the Updates button — always checks, ignores 24h throttle."""
        self._set_status("Checking for updates...")
        def _run():
            try:
                settings = self.data_loader.load_json('settings.json')
                token = settings.get('github_token', '')
                result = check_for_update(token)
                if result.get('available'):
                    self.root.after(0, lambda: self._prompt_update(result))
                elif result.get('error') == 'offline':
                    self.root.after(0, lambda: (
                        self._set_status("No internet connection."),
                        messagebox.showwarning("Updates", "Could not reach GitHub.\nCheck your internet connection."),
                    ))
                elif result.get('error') == 'auth':
                    self.root.after(0, lambda: (
                        self._set_status("Update check failed: invalid token."),
                        messagebox.showerror("Updates", "GitHub token is invalid or expired.\nContact your administrator to get a fresh copy of the app."),
                    ))
                elif result.get('error') == 'notfound':
                    self.root.after(0, lambda: (
                        self._set_status("No releases found."),
                        messagebox.showinfo("Updates", "No releases found on GitHub yet."),
                    ))
                elif result.get('error'):
                    err = result['error']
                    self.root.after(0, lambda: (
                        self._set_status(f"Update check error: {err}"),
                        messagebox.showerror("Updates", f"Update check failed:\n{err}"),
                    ))
                else:
                    self.root.after(0, lambda: (
                        self._set_status("You're up to date."),
                        messagebox.showinfo("Updates", "You're already on the latest version."),
                    ))
            except Exception as e:
                self.root.after(0, lambda: self._set_status(f"Update check failed: {e}"))
        threading.Thread(target=_run, daemon=True).start()

    def _check_update_async(self):
        """Run update check in background thread, at most once every 24 hours."""
        def _run():
            try:
                import time
                settings = self.data_loader.load_json('settings.json')
                if not settings:  # guard: never overwrite with an empty dict
                    return
                last = settings.get('last_update_check', 0)
                if time.time() - last < 86400:
                    return  # checked within the last 24 hours, skip
                token = settings.get('github_token', '')
                result = check_for_update(token)
                # Save ONLY the timestamp key — don't risk losing other keys
                settings['last_update_check'] = time.time()
                self.data_loader.save_json('settings.json', settings)
                if result.get('available'):
                    self.root.after(0, lambda: self._prompt_update(result))
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()

    def _prompt_update(self, result):
        """Show update dialog and download if user agrees."""
        ver = result.get('latest_version', '')
        notes = result.get('notes', '').strip()
        msg = f"Version {ver} is available.\n\nDownload and install now?"
        if notes:
            msg += f"\n\nRelease notes:\n{notes[:300]}"
        if not messagebox.askyesno("Update Available", msg):
            return
        url = result.get('download_url', '')
        dl_name = result.get('download_name', '')
        dl_size = result.get('download_size', 0)
        if not url:
            messagebox.showerror("Update", "No download link found in release.")
            return
        self._set_status("Downloading update...")
        settings = self.data_loader.load_json('settings.json')
        token = settings.get('github_token', '')

        def _progress(done, total):
            pct = int(done / total * 100)
            self.root.after(0, lambda: self._set_status(f"Downloading update... {pct}%"))

        def _do_download():
            ok, err = download_and_apply(url, token, _progress,
                                          expected_size=dl_size,
                                          download_name=dl_name)
            if ok:
                self.root.after(0, lambda: (
                    self._set_status("Update ready. Restarting..."),
                    self.root.after(1500, self._on_close),
                ))
            else:
                _err = err
                self.root.after(0, lambda: (
                    self._set_status("Update download failed."),
                    messagebox.showerror("Update", f"Download failed:\n{_err}"),
                ))
        threading.Thread(target=_do_download, daemon=True).start()

    def _on_close(self):
        """Save state and close the application."""
        # Unregister global hotkey
        if kb:
            try:
                kb.unhook_all()
            except Exception:
                pass

        # Save window geometry
        geo = self.root.geometry()
        settings = self.data_loader.load_json('settings.json')
        settings['window_geometry'] = geo
        self.data_loader.save_json('settings.json', settings)

        # Save history & favorites
        self.data_loader.save_json('history.json', self._history)
        self.data_loader.save_json('favorites.json', self._favorites)

        self.root.destroy()


def main():
    import sys
    was_updated = '--updated' in sys.argv

    root = tk.Tk()
    app = AgentHelperUI(root)
    if was_updated:
        root.after(800, lambda: messagebox.showinfo(
            "Update Complete",
            f"Successfully updated to v{app.data_loader.load_json('settings.json').get('version', '')}!"
        ))
    root.mainloop()


if __name__ == "__main__":
    main()
