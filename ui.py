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
import os
import sys
import threading
import time
import re

try:
    import pyperclip
except ImportError:
    pyperclip = None

try:
    import keyboard as kb
except ImportError:
    kb = None

try:
    from PIL import Image, ImageTk
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

from data_loader import DataLoader
from issue_engine import IssueEngine
from vetting_engine import VettingEngine
from resolution_engine import ResolutionEngine
from snippet_engine import SnippetEngine
from text_utils import extract_sdp_codes, extract_skiza_tune_name


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

        # ── Visual theme (must run before any widget is built) ──────────
        self._setup_styles()

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
        self._dropdown_win = None  # search dropdown Toplevel
        self._dropdown_listbox = None  # Listbox inside dropdown
        self.vetting_result_var = tk.StringVar(value='pass')
        self.vetting_issue_code = None  # set when a vetting-flow issue is selected
        self.extracted_codes = []  # SDP codes extracted from CRM paste
        self._last_crm_text = ''   # raw CRM text from clipboard
        self._search_after_id = None  # debounce id for live search
        self._reversal_txn_code = ''  # M-PESA transaction code for reversals
        self._phone_ring_index = 0  # ring-buffer index: 0→box1, 1→box2, 2→box1, …
        self._skiza_tune_name = ''  # captured Skiza tune name from CRM paste
        self._smart_listener_armed = False  # True when txn ID detected, waiting for SLA key
        self._detected_txn_id = ''  # transaction ID captured by smart listener
        self._hotkey_hook = None   # keyboard.add_hotkey handle for Alt+Space
        self._user_guidance = {}  # user-editable guidance overrides
        self._guidance_dropdown_win = None  # waterfall guidance dropdown Toplevel
        self._guide_inner = None  # bullet-list inner frame (set in _build_ui)
        # SR SLA listener state
        self._detected_sr = ''          # SR number detected from clipboard
        self._sr_listener_armed = False  # True while waiting for SLA digits
        self._sr_sla_pending = ''        # accumulated digit string
        self._sr_sla_timer_id = None     # after() timer id for finalize
        self._sr_sla_hook = None         # keyboard hook handle
        # Sequential Clipboard Queue state (timer-based, EDR-safe)
        self._hakikisha_pending = False      # True while hakikisha SMS timer is active
        self._paste_hook_timeout_id = None   # after() id for hakikisha timer
        # HLR Smart Listener state (timer-based, EDR-safe)
        self._hlr_pending_suffix = ''        # pre-computed 6-digit suffix awaiting timer fire
        self._hlr_timeout_id = None          # after() id for HLR suffix timer
        self._help_window = None             # Contextual help singleton
        # SR configurable settings (loaded from settings.json, editable in editor)
        _sett = all_data.get('settings', {})
        self._sr_regex = _sett.get('sr_regex', r'1-[A-Z0-9]+')
        self._sr_template = _sett.get('sr_template', 'Escalated to backend. SR: [SR], SLA: [SLA] hours.')

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
        
        # Maximize main app on startup
        self.root.state('zoomed')

        # History / favorites data
        self._history = all_data.get('history', {})
        if not isinstance(self._history, dict):
            self._history = {}
        self._favorites = all_data.get('favorites', {})
        if not isinstance(self._favorites, dict):
            self._favorites = {}
        self._history.setdefault('recent_issues', [])
        self._history.setdefault('guidance_usage', {})
        self._favorites.setdefault('favorite_issues', [])

        # Process-mining telemetry state
        self._workflow_logs = self.data_loader.load_json('workflow_logs.json')
        if not isinstance(self._workflow_logs, list):
            self._workflow_logs = []
        self._current_session = []  # actions for the in-progress resolution

        self._compact_mode = False
        self._full_geometry = None

        self._build_ui()
        self._bind_shortcuts()
        self._register_global_hotkey()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._last_clipboard = ""  # for clipboard polling
        self._poll_clipboard()

    # ─── VISUAL THEME ─────────────────────────────────────────────

    def _setup_styles(self):
        """Configure the global ttk.Style palette.

        Uses the 'clam' base theme (available on all platforms) and applies
        the full Safaricom brand palette — green, red, and white — with
        colour-psychology-driven button categories:

        Button hierarchy
        ----------------
        PRIMARY   (Green)  — Positive / constructive actions: Copy, Paste, Pass
        SECONDARY (LtGreen)— Navigation / low-risk: categories, search, utility
        DANGER    (Red)    — Destructive / negative: Clear, Fail, Delete
        INFO      (Teal)   — Informational / help: Ask me how, guidance clicks
        NEUTRAL   (Gray)   — Passive / toggles: Mini, Pin, Edit

        Palette
        -------
        BG_MAIN   #F4F5F7  — soft clean-grey page background (reduces eye strain)
        WHITE     #FFFFFF  — card / labelframe fill
        GREEN     #00A650  — M-PESA / Safaricom Green (primary actions)
        GREEN_DK  #008A3D  — darker green for active/hover states
        GREEN_LT  #E6F4EA  — pale green tint for secondary buttons
        RED       #E60000  — Safaricom Red (destructive / fail / alert)
        RED_DK    #B80000  — darker red for active/hover states
        RED_LT    #FDEAEA  — pale red tint for danger secondary
        TEAL      #00796B  — info/help actions
        TEAL_LT   #E0F2F1  — pale teal tint
        BORDER    #D1D5DB  — neutral light border
        TEXT      #202124  — near-black for body text
        NEUTRAL   #6B7280  — muted gray for passive actions
        NEUTRAL_LT #F1F3F4 — light neutral background
        """
        BG_MAIN    = '#F4F5F7'
        WHITE      = '#FFFFFF'
        GREEN      = '#00A650'
        GREEN_DK   = '#008A3D'
        GREEN_LT   = '#E6F4EA'
        RED        = '#E60000'
        RED_DK     = '#B80000'
        RED_LT     = '#FDEAEA'
        TEAL       = '#00796B'
        TEAL_LT    = '#E0F2F1'
        BORDER     = '#D1D5DB'
        TEXT       = '#202124'
        NEUTRAL    = '#6B7280'
        NEUTRAL_LT = '#F1F3F4'
        FONT_UI    = ('Segoe UI', 9)
        FONT_LBL   = ('Segoe UI', 10, 'bold')

        self.style = ttk.Style(self.root)
        self.style.theme_use('clam')

        # Root window background
        self.root.configure(bg=BG_MAIN)

        # ── Frames ──────────────────────────────────────────────────────
        self.style.configure('TFrame', background=BG_MAIN)
        self.style.configure('TNotebook', background=BG_MAIN)
        self.style.configure('Card.TFrame', background=WHITE)

        # ── LabelFrames (cards) ─────────────────────────────────────────
        self.style.configure(
            'TLabelframe',
            background=WHITE,
            bordercolor=BORDER,
            relief='solid',
            padding=6,
        )
        self.style.configure(
            'TLabelframe.Label',
            font=FONT_LBL,
            foreground=GREEN,
            background=WHITE,
        )

        # ── PRIMARY buttons (green — constructive actions) ──────────────
        self.style.configure(
            'TButton',
            font=FONT_UI,
            foreground=WHITE,
            background=GREEN,
            borderwidth=0,
            padding=(10, 5),
            relief='flat',
        )
        self.style.map(
            'TButton',
            background=[('active', GREEN_DK), ('disabled', BORDER)],
            foreground=[('disabled', '#888888')],
        )

        # ── SECONDARY buttons (light green — navigation / utility) ──────
        self.style.configure(
            'Secondary.TButton',
            font=FONT_UI,
            foreground=GREEN,
            background=GREEN_LT,
            borderwidth=0,
            padding=(10, 5),
            relief='flat',
        )
        self.style.map(
            'Secondary.TButton',
            background=[('active', '#CEEAD6'), ('disabled', BORDER)],
            foreground=[('disabled', '#888888')],
        )

        # ── DANGER buttons (red — destructive / fail / alert) ───────────
        self.style.configure(
            'Danger.TButton',
            font=FONT_UI,
            foreground=WHITE,
            background=RED,
            borderwidth=0,
            padding=(10, 5),
            relief='flat',
        )
        self.style.map(
            'Danger.TButton',
            background=[('active', RED_DK), ('disabled', BORDER)],
            foreground=[('disabled', '#888888')],
        )

        # ── DANGER SECONDARY (light red — soft warning) ─────────────────
        self.style.configure(
            'DangerSecondary.TButton',
            font=FONT_UI,
            foreground=RED,
            background=RED_LT,
            borderwidth=0,
            padding=(10, 5),
            relief='flat',
        )
        self.style.map(
            'DangerSecondary.TButton',
            background=[('active', '#F5C6C6'), ('disabled', BORDER)],
            foreground=[('disabled', '#888888')],
        )

        # ── INFO buttons (teal — informational / help) ──────────────────
        self.style.configure(
            'Info.TButton',
            font=FONT_UI,
            foreground=WHITE,
            background=TEAL,
            borderwidth=0,
            padding=(10, 5),
            relief='flat',
        )
        self.style.map(
            'Info.TButton',
            background=[('active', '#004D40'), ('disabled', BORDER)],
            foreground=[('disabled', '#888888')],
        )

        # ── NEUTRAL buttons (gray — passive toggles) ────────────────────
        self.style.configure(
            'Neutral.TButton',
            font=FONT_UI,
            foreground=TEXT,
            background=NEUTRAL_LT,
            borderwidth=0,
            padding=(10, 5),
            relief='flat',
        )
        self.style.map(
            'Neutral.TButton',
            background=[('active', '#E0E0E0'), ('disabled', BORDER)],
            foreground=[('disabled', '#888888')],
        )

        # ── CATEGORY buttons (outlined green — sidebar navigation) ──────
        self.style.configure(
            'Category.TButton',
            font=('Segoe UI', 9, 'bold'),
            foreground=GREEN,
            background=WHITE,
            borderwidth=1,
            bordercolor=GREEN,
            padding=(10, 6),
            relief='solid',
        )
        self.style.map(
            'Category.TButton',
            background=[('active', GREEN_LT), ('disabled', BORDER)],
            foreground=[('active', GREEN_DK), ('disabled', '#888888')],
        )

        # ── Labels ──────────────────────────────────────────────────────
        self.style.configure('TLabel',
                             background=BG_MAIN,
                             foreground=TEXT,
                             font=FONT_UI)
        self.style.configure('Card.TLabel',
                             background=WHITE,
                             foreground=TEXT,
                             font=FONT_UI)
        self.style.configure('FieldLabel.TLabel',
                             background=WHITE,
                             foreground=NEUTRAL,
                             font=('Segoe UI', 8, 'bold'))
        self.style.configure('SectionHeader.TLabel',
                             background=WHITE,
                             foreground=GREEN,
                             font=('Segoe UI', 9, 'bold'))

        # ── Entries ─────────────────────────────────────────────────────
        self.style.configure('TEntry',
                             fieldbackground=WHITE,
                             foreground=TEXT,
                             bordercolor=BORDER,
                             lightcolor=GREEN,
                             padding=(4, 3))
        self.style.map('TEntry',
                       bordercolor=[('focus', GREEN)],
                       lightcolor=[('focus', GREEN)])

        # ── Scrollbars ─────────────────────────────────────────────────
        self.style.configure('TScrollbar',
                             background=BORDER,
                             troughcolor=BG_MAIN,
                             arrowcolor=GREEN)

        # ── Separator ──────────────────────────────────────────────────
        self.style.configure('TSeparator', background=BORDER)

        # ── Status bar label ───────────────────────────────────────────
        self.style.configure('Status.TLabel',
                             background='#1B2430',
                             foreground='#42D07D',
                             font=('Segoe UI', 9),
                             padding=(8, 4))

        # ── Radiobuttons / Checkbuttons ────────────────────────────────
        self.style.configure('TRadiobutton',
                             background=WHITE,
                             foreground=TEXT,
                             font=FONT_UI)
        self.style.configure('TCheckbutton',
                             background=WHITE,
                             foreground=TEXT,
                             font=FONT_UI)
        # Pass radio (green indicator)
        self.style.configure('Pass.TRadiobutton',
                             background=WHITE,
                             foreground=GREEN,
                             font=('Segoe UI', 9, 'bold'))
        # Fail radio (red indicator)
        self.style.configure('Fail.TRadiobutton',
                             background=WHITE,
                             foreground=RED,
                             font=('Segoe UI', 9, 'bold'))

        # Store palette colours as instance attrs for reuse in _build_ui
        self._c = dict(
            bg=BG_MAIN, white=WHITE, blue=GREEN,
            blue_dk=GREEN_DK, blue_lt=GREEN_LT,
            red=RED, red_dk=RED_DK, red_lt=RED_LT,
            teal=TEAL, teal_lt=TEAL_LT,
            border=BORDER, text=TEXT,
            neutral=NEUTRAL, neutral_lt=NEUTRAL_LT,
        )

    # ─── UI BUILD ────────────────────────────────────────────────

    def _build_ui(self):
        # ── Top bar — strict LEFT / RIGHT zones ──────────────────────
        _bg = self._c['bg']
        self._top_bar = tk.Frame(self.root, bg=_bg)
        self._top_bar.pack(side=tk.TOP, fill=tk.X, padx=10, pady=6)
        top = self._top_bar

        # ── RIGHT button cluster (packed first so LEFT fills remaining space) ──
        # Neutral gray for passive utility actions
        _BTN_NEUTRAL = dict(relief="flat", cursor="hand2", padx=10, pady=5, bd=0,
                    font=("Segoe UI", 9, "bold"),
                    bg=self._c['neutral_lt'], fg=self._c['text'],
                    activebackground='#E0E0E0', activeforeground=self._c['text'])

        button_cluster_frame = tk.Frame(top, bg=_bg)
        button_cluster_frame.pack(side=tk.RIGHT, padx=4)

        # [⚙️ Edit]
        tk.Button(button_cluster_frame, text="\u2699\ufe0f Edit",
                  command=self._open_issue_editor, **_BTN_NEUTRAL).pack(side=tk.LEFT, padx=5)

        # [💡 Ask me how]
        self._help_btn = tk.Button(
            button_cluster_frame,
            text="\U0001f4a1 Ask me how",
            command=self._show_cheat_sheet,
            relief="flat", cursor="hand2",
            bg=self._c['blue'], fg='#FFFFFF',
            activebackground=self._c['blue_dk'], activeforeground='#FFFFFF',
            font=("Segoe UI", 9, "bold"),
            padx=10, pady=4, bd=0,
        )
        self._help_btn.pack(side=tk.LEFT, padx=5)

        # [▣ Mini]
        self._compact_btn = tk.Button(
            button_cluster_frame, text="\u25ab Mini",
            command=self._toggle_compact, **_BTN_NEUTRAL)
        self._compact_btn.pack(side=tk.LEFT, padx=5)

        # ── LEFT cluster: logo + version + search + calling numbers ──
        left_cluster = tk.Frame(top, bg=_bg)
        left_cluster.pack(side=tk.LEFT, fill=tk.Y)

        tk.Label(left_cluster, text="Agent Helper",
                 font=("Segoe UI", 15, "bold"), fg=self._c['blue'], bg=_bg).pack(side=tk.LEFT, padx=(0, 4))
        _ver_str = self.data_loader.load_json('settings.json').get('version', '')
        if _ver_str:
            tk.Label(left_cluster, text=f"v{_ver_str}",
                     font=("Segoe UI", 8), fg="#888888", bg=_bg).pack(side=tk.LEFT, padx=(0, 12))

        # Search controls
        self._search_frame = tk.Frame(left_cluster, bg=_bg)
        self._search_frame.pack(side=tk.LEFT)
        tk.Label(self._search_frame, text="\U0001F50D",
                 font=("Arial", 11), bg=_bg).pack(side=tk.LEFT, padx=(0, 2))
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(self._search_frame, textvariable=self.search_var, width=28)
        self.search_entry.pack(side=tk.LEFT, padx=(0, 4), ipady=3)
        self.search_entry.bind("<Return>", self._on_search)
        self.search_entry.bind("<Escape>", lambda e: self._hide_dropdown())
        self.search_entry.bind("<Down>", self._dropdown_focus)
        self.search_var.trace_add('write', self._on_search_typed)
        self._make_context_menu(self.search_entry)
        ttk.Button(self._search_frame, text="\u2716 Clear All", cursor="hand2",
                   style='Danger.TButton',
                   command=self._on_clear).pack(side=tk.LEFT, padx=(0, 4))

        # Calling Number indicator
        self._calling_frame = tk.Frame(left_cluster, bg=_bg)
        self._calling_frame.pack(side=tk.LEFT)
        ttk.Separator(self._calling_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=8, fill=tk.Y)
        tk.Label(self._calling_frame, text="SIM SWAP Nos:",
                 font=("Segoe UI", 9, "bold"), fg=self._c['blue'], bg=_bg).pack(side=tk.LEFT, padx=2)
        self.calling_no_var = tk.StringVar(value="\u2014")
        self.target_no_var  = tk.StringVar(value="\u2014")

        self._calling_numbers_frame = tk.Frame(self._calling_frame, bg=_bg)
        self._calling_numbers_frame.pack(side=tk.LEFT)

        icon1 = tk.Label(self._calling_numbers_frame, text="\u260E",
                         fg="red", cursor="hand2", bg=_bg)
        icon1.pack(side=tk.LEFT)
        icon1.bind("<Button-1>", lambda e: self._copy_number(self.calling_no_var.get()))
        icon1.bind("<Double-Button-1>", lambda e: self._copy_hlr_suffix(self.calling_no_var.get()))
        _lbl_calling = tk.Label(self._calling_numbers_frame, textvariable=self.calling_no_var,
                 font=("Consolas", 11), fg="blue", width=10, bg=_bg, cursor="hand2")
        _lbl_calling.pack(side=tk.LEFT, padx=2)
        _lbl_calling.bind("<Button-1>", lambda e: self._copy_number(self.calling_no_var.get()))
        _lbl_calling.bind("<Double-Button-1>", lambda e: self._copy_hlr_suffix(self.calling_no_var.get()))

        icon2 = tk.Label(self._calling_numbers_frame, text="\u260E",
                         fg="green", cursor="hand2", bg=_bg)
        icon2.pack(side=tk.LEFT)
        icon2.bind("<Button-1>", lambda e: self._copy_number(self.target_no_var.get()))
        icon2.bind("<Double-Button-1>", lambda e: self._copy_hlr_suffix(self.target_no_var.get()))
        _lbl_target = tk.Label(self._calling_numbers_frame, textvariable=self.target_no_var,
                 font=("Consolas", 11), fg="blue", width=10, bg=_bg, cursor="hand2")
        _lbl_target.pack(side=tk.LEFT, padx=2)
        _lbl_target.bind("<Button-1>", lambda e: self._copy_number(self.target_no_var.get()))
        _lbl_target.bind("<Double-Button-1>", lambda e: self._copy_hlr_suffix(self.target_no_var.get()))

        # HLR button — copies last 6 digits of target number
        self._hlr_btn = tk.Button(
            self._calling_numbers_frame, text="HLR",
            font=("Segoe UI", 8, "bold"), fg="#FFFFFF", bg=self._c['teal'],
            activebackground='#004D40', activeforeground='#FFFFFF',
            relief="flat", cursor="hand2", bd=0, padx=6, pady=1,
            command=lambda: self._copy_hlr_suffix(self.target_no_var.get()),
        )
        self._hlr_btn.pack(side=tk.LEFT, padx=(4, 0))



        # ── Main 3-column content ──
        body = ttk.Frame(self.root)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
        self._body_frame = body

        # --- LEFT: categories + guidance (Results/Favorites removed — search uses dropdown) ---
        self._left_panel = ttk.Frame(body, width=260)
        self._left_panel.pack(side=tk.LEFT, fill=tk.BOTH, padx=4)
        self._left_panel.pack_propagate(False)
        left = self._left_panel

        cat_frame = ttk.LabelFrame(left, text="\U0001F4C1 Categories")
        cat_frame.pack(fill=tk.X, padx=2, pady=2)
        for cat in self._ordered_categories():
            ttk.Button(cat_frame, text=cat, style='Category.TButton',
                       command=lambda c=cat: self._on_category(c)).pack(fill=tk.X, padx=4, pady=2)

        # Guidance panel (populated when issue selected)
        guide_frame = ttk.LabelFrame(left, text="Guidance / Instructions")
        guide_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=4)

        # ── Guidance toolbar: [🔍][___filter___][x] [➕ Add] [💾 Save] ──
        guide_btn_frame = ttk.Frame(guide_frame)
        guide_btn_frame.pack(fill=tk.X, padx=4, pady=(4, 2))
        guide_btn_frame.columnconfigure(0, weight=0)  # icon
        guide_btn_frame.columnconfigure(1, weight=2)  # entry (half)
        guide_btn_frame.columnconfigure(2, weight=0)  # clear btn
        guide_btn_frame.columnconfigure(3, weight=1)  # Add (quarter)
        guide_btn_frame.columnconfigure(4, weight=1)  # Save (quarter)

        # Search icon
        ttk.Label(guide_btn_frame, text="\U0001F50D", font=("Arial", 10)).grid(
            row=0, column=0, padx=(0, 2))

        # Clean, empty search entry
        self._guidance_filter_var = tk.StringVar()
        self._guidance_filter_var.trace_add('write', self._on_guidance_filter_typed)
        self._guide_filter_entry = ttk.Entry(
            guide_btn_frame, textvariable=self._guidance_filter_var,
            font=("Arial", 9))
        self._guide_filter_entry.grid(row=0, column=1, sticky="ew", ipady=3)

        # Clear button (×)
        self._guide_filter_clear = tk.Label(
            guide_btn_frame, text="\u00d7", font=("Arial", 11, "bold"),
            fg="#888", cursor="hand2", padx=4)
        self._guide_filter_clear.grid(row=0, column=2, padx=(1, 6))
        self._guide_filter_clear.bind(
            "<Button-1>", lambda e: (self._guidance_filter_var.set(''),
                                     self._guide_filter_entry.focus_set()))

        self._guide_add_btn = ttk.Button(guide_btn_frame, text="\u2795 Add",
                                         command=self._add_guidance_line)
        self._guide_add_btn.grid(row=0, column=3, sticky="ew", padx=(0, 4), ipady=3)

        self._guide_save_btn = ttk.Button(guide_btn_frame, text="\U0001F4BE Save",
                                          command=self._save_user_guidance,
                                          state=tk.DISABLED)
        self._guide_save_btn.grid(row=0, column=4, sticky="ew", ipady=3)

        self.guidance_text = scrolledtext.ScrolledText(
            guide_frame, height=10, wrap=tk.WORD,
            font=("Consolas", 9), relief="flat",
            borderwidth=1, highlightthickness=1,
            highlightcolor=self._c['blue'],
            highlightbackground=self._c['border'],
            background='#FFFFFF')
        self.guidance_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.guidance_text.bind("<Button-1>", self._on_guidance_click)
        self._make_context_menu(self.guidance_text)

        self._current_guidance = []
        self._user_guidance = {}
        self._guidance_has_pending_adds = False  # tracks unsaved additions
        self._guidance_dropdown_win = None

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
        self._custom_note_frame = ttk.Frame(out_frame)
        self._custom_note_frame.pack(fill=tk.X, padx=4, pady=2)
        ttk.Label(self._custom_note_frame, text="Extra note:").pack(side=tk.LEFT)
        self.custom_note_var = tk.StringVar()
        self.custom_note_var.trace_add('write', lambda *_: self._on_field_changed())
        _custom_note_entry = ttk.Entry(self._custom_note_frame, textvariable=self.custom_note_var, width=35)
        _custom_note_entry.pack(side=tk.LEFT, padx=4)
        self._make_context_menu(_custom_note_entry)

        self.output_text = scrolledtext.ScrolledText(
            out_frame, height=14, wrap=tk.WORD,
            relief="flat", borderwidth=1,
            highlightthickness=1,
            highlightcolor=self._c['blue'],
            highlightbackground=self._c['border'],
            background='#FFFFFF', font=("Consolas", 9))
        self.output_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self._make_context_menu(self.output_text)

        btn_row2 = ttk.Frame(out_frame)
        btn_row2.pack(fill=tk.X, padx=4, pady=4)
        self._btn_copy_output = ttk.Button(btn_row2, text="\u2714 Copy Output", command=self._on_copy_output)
        self._btn_copy_output.pack(side=tk.LEFT, padx=2)
        self._btn_copy_serial = ttk.Button(btn_row2, text="Copy Serial No",
                                            style='Secondary.TButton',
                                            command=self._on_copy_serial)
        self._btn_copy_serial.pack(side=tk.LEFT, padx=2)
        self.fav_btn = ttk.Button(btn_row2, text="\u2605 Fav",
                                   style='Secondary.TButton',
                                   command=self._toggle_favorite)
        self.fav_btn.pack(side=tk.LEFT, padx=2)

        # ── Status bar ──
        self.status_var = tk.StringVar(value="Ready — select an issue and paste CRM data")
        ttk.Label(self.root, textvariable=self.status_var,
                  style='Status.TLabel').pack(
            side=tk.BOTTOM, fill=tk.X)

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
            'output_text': self.output_text,
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

        # Phone-sized window, snapped to right edge, full screen height
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight() - 80
        self.root.state('normal')  # Un-maximize before applying geometry
        self.root.geometry(f"400x{screen_h}+{screen_w - 400}+0")
        self.root.minsize(340, 500)

        # Focus-based transparency removed
        self._transparency_focus_active = False
        # self.root.bind('<FocusIn>', self._on_compact_focus_in)
        # self.root.bind('<FocusOut>', self._on_compact_focus_out)

        # Replay current state into compact widgets
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

        # ── Row 1: LEFT = 🔍 search  |  RIGHT = button cluster ──────
        top = ttk.Frame(cf)
        top.pack(fill=tk.X, padx=4, pady=(4, 2))

        # LEFT: search
        ttk.Label(top, text="\U0001F50D").pack(side=tk.LEFT)
        se = ttk.Entry(top, textvariable=self.search_var, width=10)
        se.pack(side=tk.LEFT, padx=(2, 4))
        self._make_context_menu(se)
        se.bind("<Escape>", lambda e: self._hide_dropdown())
        se.bind("<Down>", self._dropdown_focus)

        # RIGHT cluster (right-to-left packing: last packed = leftmost on screen)
        _MB = dict(relief="flat", cursor="hand2", font=("Arial", 8, "bold"),
                   bg="#F1F3F4", fg="#202124",
                   activebackground="#E0E0E0", padx=3, pady=2, bd=0)

        tk.Button(top, text="Clear", command=self._on_clear, **_MB).pack(
            side=tk.RIGHT, padx=2)
        tk.Button(top, text="\u25a3 Full", command=self._toggle_compact, **_MB).pack(
            side=tk.RIGHT, padx=2)
        self._pin_btn = tk.Button(
            top, text="\U0001F4CC Pin",
            command=self._toggle_pin, **_MB)
        self._pin_btn.pack(side=tk.RIGHT, padx=2)
        tk.Button(
            top, text="\U0001f4a1",
            command=self._show_cheat_sheet,
            relief="flat", cursor="hand2",
            font=("Arial", 10),
            bg="#E8F0FE", fg="#1A73E8",
            activebackground="#C5D8FB",
            padx=3, pady=2, bd=0,
        ).pack(side=tk.RIGHT, padx=2)
        tk.Button(top, text="\u2699\ufe0f Edit",
                  command=self._open_issue_editor, **_MB).pack(side=tk.RIGHT, padx=2)


        # ── Row 2: 4 pinned issue buttons (direct select, no extra click) ──
        cat_row = ttk.Frame(cf)
        cat_row.pack(fill=tk.X, padx=4, pady=2)
        for label, code in [('SIM SWAP', 'SIM_SWAP'), ('START KEY', 'MPESA_STARTKEY_PIN'), ('REVERSAL', 'REVERSAL'), ('GENERAL', 'GENERAL')]:
            ttk.Button(cat_row, text=label,
                       command=lambda c=code: self._select_issue_by_code(c)).pack(
                           side=tk.LEFT, expand=True, fill=tk.X, padx=1)

        # ── Row 3: Paste CRM + Dual Calling Numbers ──
        paste_row = ttk.Frame(cf)
        paste_row.pack(fill=tk.X, padx=4, pady=2)
        ttk.Button(paste_row, text="\U0001F4CB Paste CRM",
                   command=self._on_paste_and_extract).pack(side=tk.LEFT, padx=(0, 2))
                   
        self._compact_calling_frame = ttk.Frame(paste_row)
        self._compact_calling_frame.pack(side=tk.LEFT)
        
        c_icon1 = ttk.Label(self._compact_calling_frame, text="\u260E", foreground="red", cursor="hand2")
        c_icon1.pack(side=tk.LEFT)
        c_icon1.bind("<Button-1>", lambda e: self._copy_number(self.calling_no_var.get()))
        c_icon1.bind("<Double-Button-1>", lambda e: self._copy_hlr_suffix(self.calling_no_var.get()))

        _c_lbl_calling = ttk.Label(self._compact_calling_frame, textvariable=self.calling_no_var,
                  font=("Consolas", 9), foreground="blue", cursor="hand2")
        _c_lbl_calling.pack(side=tk.LEFT, padx=1)
        _c_lbl_calling.bind("<Button-1>", lambda e: self._copy_number(self.calling_no_var.get()))
        _c_lbl_calling.bind("<Double-Button-1>", lambda e: self._copy_hlr_suffix(self.calling_no_var.get()))

        c_icon2 = ttk.Label(self._compact_calling_frame, text="\u260E", foreground="green", cursor="hand2")
        c_icon2.pack(side=tk.LEFT, padx=(4, 0))
        c_icon2.bind("<Button-1>", lambda e: self._copy_number(self.target_no_var.get()))
        c_icon2.bind("<Double-Button-1>", lambda e: self._copy_hlr_suffix(self.target_no_var.get()))

        _c_lbl_target = ttk.Label(self._compact_calling_frame, textvariable=self.target_no_var,
                  font=("Consolas", 9), foreground="blue", cursor="hand2")
        _c_lbl_target.pack(side=tk.LEFT, padx=1)
        _c_lbl_target.bind("<Button-1>", lambda e: self._copy_number(self.target_no_var.get()))
        _c_lbl_target.bind("<Double-Button-1>", lambda e: self._copy_hlr_suffix(self.target_no_var.get()))

        # HLR button (compact)
        self._hlr_btn_compact = tk.Button(
            self._compact_calling_frame, text="HLR",
            font=("Segoe UI", 7, "bold"), fg="#FFFFFF", bg=self._c['teal'],
            activebackground='#004D40', activeforeground='#FFFFFF',
            relief="flat", cursor="hand2", bd=0, padx=4, pady=0,
            command=lambda: self._copy_hlr_suffix(self.target_no_var.get()),
        )
        self._hlr_btn_compact.pack(side=tk.LEFT, padx=(3, 0))

        # ── Row 4: Guidance (compact) ──
        guide_lf = ttk.LabelFrame(cf, text="Guidance")
        guide_lf.pack(fill=tk.X, padx=4, pady=2)

        # Toolbar: [🔍][___filter___][x] [➕ Add] [💾 Save]
        guide_btn_c = ttk.Frame(guide_lf)
        guide_btn_c.pack(fill=tk.X, padx=2, pady=(3, 1))
        guide_btn_c.columnconfigure(0, weight=0)
        guide_btn_c.columnconfigure(1, weight=2)
        guide_btn_c.columnconfigure(2, weight=0)
        guide_btn_c.columnconfigure(3, weight=1)
        guide_btn_c.columnconfigure(4, weight=1)

        ttk.Label(guide_btn_c, text="\U0001F50D", font=("Arial", 9)).grid(
            row=0, column=0, padx=(0, 2))

        c_fe = ttk.Entry(guide_btn_c, textvariable=self._guidance_filter_var,
                         font=("Arial", 8))
        c_fe.grid(row=0, column=1, sticky="ew", ipady=2)

        c_clr = tk.Label(guide_btn_c, text="\u00d7", font=("Arial", 10, "bold"),
                         fg="#888", cursor="hand2", padx=3)
        c_clr.grid(row=0, column=2, padx=(1, 4))
        c_clr.bind("<Button-1>", lambda e: (self._guidance_filter_var.set(''),
                                             c_fe.focus_set()))

        self._guide_add_btn = ttk.Button(guide_btn_c, text="\u2795 Add",
                                          command=self._add_guidance_line)
        self._guide_add_btn.grid(row=0, column=3, sticky="ew", padx=(0, 3), ipady=2)

        self._guide_save_btn = ttk.Button(guide_btn_c, text="\U0001F4BE Save",
                                           command=self._save_user_guidance,
                                           state=tk.DISABLED)
        self._guide_save_btn.grid(row=0, column=4, sticky="ew", ipady=2)

        self.guidance_text = scrolledtext.ScrolledText(
            guide_lf, height=4, wrap=tk.WORD,
            font=("Consolas", 8), relief="flat",
            borderwidth=1, highlightthickness=1,
            highlightcolor=self._c['blue'],
            highlightbackground=self._c['border'],
            background='#FFFFFF')
        self.guidance_text.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.guidance_text.bind("<Button-1>", self._on_guidance_click)
        self._make_context_menu(self.guidance_text)

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
        self._compact_act_row = ttk.Frame(cf)
        self._compact_act_row.pack(fill=tk.X, padx=4, pady=2)
        self._compact_note_label = ttk.Label(self._compact_act_row, text="Note:", font=("Arial", 8))
        self._compact_note_label.pack(side=tk.LEFT)
        self._compact_note_entry = ttk.Entry(self._compact_act_row, textvariable=self.custom_note_var, width=12)
        self._compact_note_entry.pack(side=tk.LEFT, padx=2)
        self._make_context_menu(self._compact_note_entry)
        self._compact_btn_serial = ttk.Button(self._compact_act_row, text="\U0001F4CB Serial", command=self._on_copy_serial)
        self._compact_btn_serial.pack(side=tk.LEFT, padx=2)
        self._compact_btn_output = ttk.Button(self._compact_act_row, text="\U0001F4CB Output", command=self._on_copy_output)
        self._compact_btn_output.pack(side=tk.LEFT, padx=2)
        self._compact_fav_btn = ttk.Button(self._compact_act_row, text="\u2605", width=2, command=self._toggle_favorite)
        self._compact_fav_btn.pack(side=tk.LEFT, padx=2)

        # ── Row 10: Output ──
        self._compact_out_lf = ttk.LabelFrame(cf, text="Interaction Output")
        self._compact_out_lf.pack(fill=tk.X, padx=4, pady=(2, 4))
        self.output_text = scrolledtext.ScrolledText(
            self._compact_out_lf, height=7, wrap=tk.WORD,
            font=("Consolas", 8), relief="flat",
            borderwidth=1, highlightthickness=1,
            highlightcolor=self._c['blue'],
            highlightbackground=self._c['border'],
            background='#FFFFFF')
        self.output_text.pack(fill=tk.X, padx=2, pady=2)
        self._make_context_menu(self.output_text)

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

        # Unbind focus-based transparency and restore full opacity
        self._transparency_focus_active = False
        try:
            self.root.unbind('<FocusIn>')
            self.root.unbind('<FocusOut>')
        except Exception:
            pass
        self.root.attributes('-alpha', 1.0)

        # Destroy compact frame
        if hasattr(self, '_compact_frame') and self._compact_frame:
            self._compact_frame.destroy()
            self._compact_frame = None

        # Restore original widget references
        self.output_text = self._full['output_text']
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
        self.root.state('zoomed')  # Maximize when returning to full version
        self._compact_btn.configure(text="\u25ab Mini")

        # Replay state into original widgets
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
        """Register Ctrl+Shift+Space as a global toggle hotkey using the
        Win32 RegisterHotKey API (EDR-safe).

        Unlike the `keyboard` library which uses WH_KEYBOARD_LL low-level
        hooks (blocked by corporate EDR/antivirus), RegisterHotKey is a
        legitimate Win32 API that registers a system-wide hotkey without
        triggering security software.

        A dedicated daemon thread runs the Windows message pump so the
        main Tkinter event loop is never blocked.
        """
        if sys.platform != 'win32':
            return
        try:
            import ctypes
            from ctypes import wintypes

            def _hotkey_thread():
                user32 = ctypes.windll.user32
                MOD_CONTROL = 0x0002
                MOD_SHIFT = 0x0004
                VK_SPACE = 0x20
                WM_HOTKEY = 0x0312
                HOTKEY_ID = 1

                if not user32.RegisterHotKey(None, HOTKEY_ID,
                                             MOD_CONTROL | MOD_SHIFT, VK_SPACE):
                    return  # registration failed (another app owns the combo)

                msg = wintypes.MSG()
                while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                    if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                        self.root.after(0, self._toggle_visibility)

            t = threading.Thread(target=_hotkey_thread, daemon=True)
            t.start()
        except Exception:
            pass

    def _toggle_visibility(self):
        """Alt+Space handler (runs on Tkinter main thread via root.after).

        Show/raise the window if it is hidden or minimised;
        withdraw it if it is already the focused foreground window.
        """
        state = self.root.state()           # 'normal', 'iconic', 'withdrawn'
        try:
            is_focused = (self.root.focus_displayof() is not None)
        except Exception:
            is_focused = False

        if state in ('iconic', 'withdrawn') or not is_focused:
            self._bring_to_front()
        else:
            self.root.withdraw()

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
        """No-op: favorites are still tracked in memory/disk but there is no
        listbox to populate (removed in Sprint 5 UI cleanup)."""
        pass

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
        q = self.search_var.get().strip()
        if not q:
            self._hide_dropdown()
            return
        self._search_after_id = self.root.after(250, self._on_search)

    def _do_search(self, query):
        self._log_action('SEARCH', query[:60])
        self.search_results = self.issue_engine.get_top_matches(query, limit=8)
        self.root.after(0, self._update_results)

    def _on_category(self, category):
        issues = self.issue_engine.get_issues_by_category(category)
        self.search_results = [
            {'issue_code': i['issue_code'], 'display_name': i['display_name'],
             'category': i['category'], 'confidence': 100,
             'matched_terms': 'category', 'raw_issue': i}
            for i in issues]
        # Auto-select if only one result in category
        if len(self.search_results) == 1:
            self.current_issue = self.search_results[0]
            self.current_raw_issue = self.current_issue.get('raw_issue', {})
            self._apply_selected_issue()
        else:
            self._show_dropdown()

    def _update_results(self):
        """Show search results in a dropdown popup below the search entry."""
        if not self.search_results:
            self._hide_dropdown()
            return
        # Auto-select if only one result
        if len(self.search_results) == 1:
            self._hide_dropdown()
            self.current_issue = self.search_results[0]
            self.current_raw_issue = self.current_issue.get('raw_issue', {})
            self._apply_selected_issue()
            return
        self._show_dropdown()

    def _on_result_select(self, event=None):
        """Handle selection from the dropdown listbox."""
        if not self._dropdown_listbox:
            return
        sel = self._dropdown_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < len(self.search_results):
            self.current_issue = self.search_results[idx]
            self.current_raw_issue = self.current_issue.get('raw_issue', {})
            self._hide_dropdown()
            self._apply_selected_issue()

    # ─── SEARCH DROPDOWN ───────────────────────────────────────

    def _show_dropdown(self):
        """Show (or refresh) the search results dropdown below the search entry."""
        if not self.search_results:
            self._hide_dropdown()
            return

        # Determine anchor widget: search_entry in full mode, or root in compact
        anchor = self.search_entry

        if self._dropdown_win is None or not self._dropdown_win.winfo_exists():
            self._dropdown_win = tk.Toplevel(self.root)
            self._dropdown_win.overrideredirect(True)  # no title bar
            self._dropdown_win.attributes('-topmost', True)
            self._dropdown_listbox = tk.Listbox(
                self._dropdown_win, font=("Arial", 10),
                selectmode=tk.SINGLE, activestyle='dotbox',
                relief=tk.SOLID, borderwidth=1,
                bg='#FFFDE7', selectbackground='#1976D2', selectforeground='white'
            )
            self._dropdown_listbox.pack(fill=tk.BOTH, expand=True)
            self._dropdown_listbox.bind('<<ListboxSelect>>', self._on_result_select)
            self._dropdown_listbox.bind('<Return>', lambda e: self._on_result_select())
            self._dropdown_listbox.bind('<Escape>', lambda e: self._hide_dropdown())
            # Close dropdown when clicking elsewhere
            self.root.bind('<Button-1>', self._on_root_click, add='+')

        # Populate
        self._dropdown_listbox.delete(0, tk.END)
        for r in self.search_results:
            self._dropdown_listbox.insert(tk.END, r['display_name'])

        # Position below anchor
        try:
            anchor.update_idletasks()
            x = anchor.winfo_rootx()
            y = anchor.winfo_rooty() + anchor.winfo_height()
            w = max(anchor.winfo_width(), 250)
            h = min(len(self.search_results) * 22 + 4, 220)
            self._dropdown_win.geometry(f"{w}x{h}+{x}+{y}")
            self._dropdown_win.deiconify()
        except Exception:
            pass

    def _hide_dropdown(self):
        """Hide the search dropdown popup."""
        if self._dropdown_win and self._dropdown_win.winfo_exists():
            self._dropdown_win.withdraw()

    def _dropdown_focus(self, event=None):
        """Move focus into the dropdown listbox (Down arrow from search entry)."""
        if (self._dropdown_win and self._dropdown_win.winfo_exists()
                and self._dropdown_listbox and self._dropdown_listbox.size() > 0):
            self._dropdown_listbox.focus_set()
            self._dropdown_listbox.selection_set(0)
            self._dropdown_listbox.activate(0)
            return 'break'

    def _on_root_click(self, event):
        """Close dropdown if click is outside of it."""
        if self._dropdown_win and self._dropdown_win.winfo_exists():
            try:
                w = event.widget
                if w != self._dropdown_listbox and w != self.search_entry:
                    self._hide_dropdown()
            except Exception:
                pass

    def _apply_selected_issue(self):
        """Shared logic after an issue is selected (from results, fav, or recent)."""
        # Reset telemetry session for the new resolution cycle
        self._current_session = []
        self._log_action('SELECT_ISSUE', self.current_raw_issue.get('issue_code', ''))

        # Soft-reset: clear stale output/fields from the previous issue
        self._reset_for_new_issue()

        name = self.current_issue['display_name']
        self.issue_label_var.set(f"Issue: {name}")
        self._set_status(f"Issue selected: {name}")

        # Record in recent history
        issue_code = self.current_raw_issue.get('issue_code', '')
        self._record_recent(issue_code)

        # Update guidance panel
        self._show_guidance()

        # Detect vetting flow: use requires_vetting flag, not hardcoded issue names
        requires_vetting = self.current_raw_issue.get('requires_vetting', False)
        is_built_in_vetting = issue_code in self.vetting_engine.VETTING_CONFIGS

        # Show calling/target number capture for all vetting issues, hide for others
        if requires_vetting or is_built_in_vetting:
            if hasattr(self, '_calling_frame'):
                self._calling_frame.pack(side=tk.LEFT)
            if hasattr(self, '_compact_calling_frame'):
                self._compact_calling_frame.pack(side=tk.LEFT)
        else:
            self._reset_capture_state()
            if hasattr(self, '_calling_frame'):
                self._calling_frame.pack_forget()
            if hasattr(self, '_compact_calling_frame'):
                self._compact_calling_frame.pack_forget()

        if requires_vetting or is_built_in_vetting:
            self.vetting_issue_code = issue_code
            self._set_fields_frame_visible(True)
            self._build_vetting_fields(issue_code)
            self._build_vetting_notes()
        else:
            self.vetting_issue_code = None
            self._build_generic_fields()
            self._build_interaction_notes()
            # Hide Step 2 box for REVERSAL and snippet-only categories
            cat = self.current_raw_issue.get('category', '')
            self._set_fields_frame_visible(issue_code != 'REVERSAL' and cat not in ('GENERAL', 'MPESA'))

        # ── SIM_SWAP-only widgets: Serial, Extra note, Fav ─────────────────
        # Copy Output is always visible.
        is_sim_swap = (issue_code in ('SIM_SWAP', 'TILL_SWAP'))

        # Full-mode widgets
        for widget, pack_kwargs in [
            (getattr(self, '_btn_copy_serial',   None), dict(side=tk.LEFT, padx=2)),
            (getattr(self, '_custom_note_frame', None), dict(fill=tk.X, padx=4, pady=2)),
            (getattr(self, 'fav_btn',            None), dict(side=tk.LEFT, padx=2)),
        ]:
            if widget is None:
                continue
            try:
                if is_sim_swap:
                    widget.pack(**pack_kwargs)
                else:
                    widget.pack_forget()
            except Exception:
                pass

        # Compact-mode widgets
        for widget, pack_kwargs in [
            (getattr(self, '_compact_btn_serial',  None), dict(side=tk.LEFT, padx=2)),
            (getattr(self, '_compact_note_label',  None), dict(side=tk.LEFT)),
            (getattr(self, '_compact_note_entry',  None), dict(side=tk.LEFT, padx=2)),
            (getattr(self, '_compact_fav_btn',     None), dict(side=tk.LEFT, padx=2)),
        ]:
            if widget is None:
                continue
            try:
                if is_sim_swap:
                    widget.pack(**pack_kwargs)
                else:
                    widget.pack_forget()
            except Exception:
                pass

        # Ensure Output buttons are always visible (idempotent re-pack)
        for attr, kwargs in [
            ('_btn_copy_output',     dict(side=tk.LEFT, padx=2)),
            ('_compact_btn_output',  dict(side=tk.LEFT, padx=2)),
        ]:
            btn = getattr(self, attr, None)
            if btn is None:
                continue
            try:
                btn.pack(**kwargs)
            except Exception:
                pass

        self._rebuild_output()

    def _show_guidance(self):
        issue_code = self.current_raw_issue.get('issue_code', '')
        user_guide = self._load_user_guidance(issue_code)
        self._current_guidance = list(user_guide) if user_guide else list(
            self.current_raw_issue.get('guidance', []))

        # Reset filter bar to empty and disable Save for fresh issue
        self._guidance_has_pending_adds = False
        try:
            self._guide_save_btn.configure(state=tk.DISABLED)
        except Exception:
            pass
        self._guidance_filter_var.set('')
        
        self._filter_guidance()

    def _filter_guidance(self, keyword: str = ""):
        """Populate the guidance text widget.

        Each line is tagged so that clicking it copies the text to clipboard.
        When *keyword* is provided only matching lines are shown, with the
        keyword highlighted in yellow.
        """
        widget = self.guidance_text
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        # Remove stale per-line tags
        for tag in list(widget.tag_names()):
            if tag.startswith("_guide_line_"):
                widget.tag_delete(tag)

        lines = self._current_guidance
        # ── Smart sort: most-clicked notes rise to the top ──────────────
        usage = self._history.get('guidance_usage', {})
        lines = sorted(lines, key=lambda x: usage.get(x, 0), reverse=True)
        if not lines:
            widget.insert(tk.END, "No guidance for this issue.\n")
            return

        kw = keyword.strip().lower()
        matched = 0
        for idx, line in enumerate(lines):
            if kw and kw not in line.lower():
                continue
            tag = f"_guide_line_{idx}"
            display = f"\u2013 {line}\n"
            start = widget.index(tk.END)
            widget.insert(tk.END, display, tag)
            # Single-click → copy
            widget.tag_bind(
                tag, "<Button-1>",
                lambda e, t=line: (self._copy(t), self._set_status(f"Copied: {t[:60]}"))
            )
            # Double-click → inline edit (Fix 7)
            widget.tag_bind(
                tag, "<Double-Button-1>",
                lambda e, i=idx, t=line: self._edit_guidance_line(i, t)
            )
            widget.tag_configure(tag, foreground="#1A237E")
            if kw:
                pos = display.lower().find(kw)
                if pos != -1:
                    hl_s = f"{start} + {pos} chars"
                    hl_e = f"{start} + {pos + len(kw)} chars"
                    widget.tag_configure("_kw_hl", background="#FFEB3B", foreground="black")
                    widget.tag_add("_kw_hl", hl_s, hl_e)
            matched += 1

        if kw and matched == 0:
            widget.insert(tk.END, f'No guidance matched "{keyword}".\n')

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
            # Log which note the agent selected
            note_label = next(
                (txt for txt, v in self.note_vars if v is toggled_var), ''
            )
            self._log_action('SELECT_NOTE', note_label[:60])
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
        """Build editable field entries for any vetting-flow issue (built-in or dynamic)."""
        for widget in self.fields_frame.winfo_children():
            widget.destroy()
        self.field_entries = {}

        display_name = self.current_raw_issue.get('display_name', issue_code)
        self.fields_frame.config(text=f"Step 2 — {display_name} Vetting Fields")

        inner = ttk.Frame(self.fields_frame)
        inner.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # ── Determine field list ──────────────────────────────────────
        config = self.vetting_engine.VETTING_CONFIGS.get(issue_code, {})
        is_built_in = bool(config)

        if is_built_in:
            # Existing behaviour: read from VETTING_CONFIGS output_fields
            output_field_attr = config.get('output_fields', '')
            output_fields = getattr(self.vetting_engine, output_field_attr, [])
            auto_keys = {'Name', 'ID', 'YOB', 'MPESA', 'Airtime'}
            if config.get('manual_only'):
                auto_fields   = []
                manual_fields = list(output_fields)
            else:
                auto_fields   = [(lbl, key) for lbl, key in output_fields if key in auto_keys]
                manual_fields = [(lbl, key) for lbl, key in output_fields if key not in auto_keys]
        else:
            # Dynamic issue: build field list from issues.json vetting_fields
            # Each entry is a plain field name like 'Name', 'ID', 'YOB', 'MPESA', ...
            raw_fields = self.current_raw_issue.get('vetting_fields', [])
            # Use field name as both label and key; auto-extract the primary ones
            auto_keys_dyn = {'Name', 'ID', 'YOB'}
            auto_fields   = [(f, f) for f in raw_fields if f in auto_keys_dyn]
            manual_fields = [(f, f) for f in raw_fields if f not in auto_keys_dyn]

        # ── Render auto-extracted fields ──────────────────────────────
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

        # ── Render manual / secondary fields ─────────────────────────
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
                    try:
                        if n == 20:
                            counter_lbl.configure(foreground="green")
                        elif n > 20:
                            counter_lbl.configure(foreground="red")
                        else:
                            counter_lbl.configure(foreground="gray")
                    except tk.TclError:
                        pass
                var.trace_add('write', _update_serial_counter)
                _update_serial_counter()
            else:
                var = tk.StringVar()
                ttk.Entry(inner, textvariable=var, width=35).grid(
                    row=row, column=1, sticky=tk.W, padx=2, pady=1)
            self.field_entries[key] = var
            row += 1

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

        # Always show Pass
        ttk.Radiobutton(row, text="Pass",
                        variable=self.vetting_result_var, value='pass',
                        command=self._rebuild_output).pack(side=tk.LEFT, padx=4)

        config = self.vetting_engine.VETTING_CONFIGS.get(self.vetting_issue_code, {})
        is_built_in = bool(config)

        if is_built_in:
            # Static issues: show buttons based on declared headers
            if config.get('fail_secondary_header'):
                ttk.Radiobutton(row, text="Fail Secondary",
                                variable=self.vetting_result_var, value='fail_secondary',
                                command=self._rebuild_output).pack(side=tk.LEFT, padx=4)
            ttk.Radiobutton(row, text="Fail Primary",
                            variable=self.vetting_result_var, value='fail_primary',
                            command=self._rebuild_output).pack(side=tk.LEFT, padx=4)
            if config.get('failed_twice_header'):
                ttk.Radiobutton(row, text="Failed Twice",
                                variable=self.vetting_result_var, value='failed_twice',
                                command=self._rebuild_output).pack(side=tk.LEFT, padx=4)
        else:
            # Dynamic issue: show buttons for every resolution saved in resolutions.json
            _SUFFIX_TO_RESULT = {
                'FAIL2': ('fail_secondary', 'Fail Secondary'),
                'FAIL1': ('fail_primary',   'Fail Primary'),
                'FAIL_2X': ('failed_twice', 'Failed Twice'),
            }
            shown = set()
            for res in self.resolution_engine.get_all_by_issue(self.vetting_issue_code):
                code = res.get('resolution_code', '')
                for suffix, (val, label) in _SUFFIX_TO_RESULT.items():
                    if code.endswith(f'_{suffix}') and val not in shown:
                        ttk.Radiobutton(row, text=label,
                                        variable=self.vetting_result_var, value=val,
                                        command=self._rebuild_output).pack(side=tk.LEFT, padx=4)
                        shown.add(val)
            # Fallback: always at least offer Fail Primary if no resolutions yet
            if not shown:
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
        self._log_action('PASTE_CRM')
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

        # Determine current issue code for context-aware extraction
        issue_code = self.current_raw_issue.get('issue_code', '') if self.current_raw_issue else ''

        # Extract SDP codes: PRS requires strict 5+ digits, Skiza/general accepts 4+
        strict = (issue_code == 'PRS')
        self.extracted_codes = extract_sdp_codes(raw, strict_prs=strict)

        # Capture Skiza tune name if on a Skiza issue
        if issue_code == 'SKIZA':
            self._skiza_tune_name = extract_skiza_tune_name(raw) or ''

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
            c_no = getattr(self, 'calling_no_var', tk.StringVar(value="—")).get()
            t_no = getattr(self, 'target_no_var', tk.StringVar(value="—")).get()

            # Static built-in vetting issues use VETTING_CONFIGS
            if self.vetting_issue_code in self.vetting_engine.VETTING_CONFIGS:
                output = self.vetting_engine.format_vetting_result(
                    fields, result, self.vetting_issue_code,
                    calling_no=c_no if c_no != "—" else "",
                    target_no=t_no if t_no != "—" else ""
                )
            else:
                # Dynamic issue: look up the resolution template for this outcome
                res_suffix = {
                    'pass': 'PASS', 'fail_secondary': 'FAIL2',
                    'fail_primary': 'FAIL1', 'failed_twice': 'FAIL_2X',
                }.get(result, 'PASS')
                res_code = f"{self.vetting_issue_code}_{res_suffix}"
                resolution = self.resolution_engine.get_resolution(res_code)
                template = resolution.get('template_text', '') if resolution else ''
                vetting_fields = (
                    self.current_raw_issue.get('vetting_fields', [])
                    if self.current_raw_issue else []
                )
                output = self.vetting_engine.format_dynamic_vetting_result(
                    fields, result, template, vetting_fields
                )
        else:
            notes = []

            for note_text, var in self.note_vars:
                if var.get():
                    line = note_text
                    # Replace CODE placeholder with extracted SDP codes
                    if 'CODE' in line and self.extracted_codes:
                        code_str = ', '.join(self.extracted_codes)
                        if self._skiza_tune_name:
                            code_str += f' ({self._skiza_tune_name})'
                        line = line.replace('CODE', code_str)
                    notes.append(line)

            # For REVERSAL: prepend txn code if we have one
            issue_code = self.current_raw_issue.get('issue_code', '') if self.current_raw_issue else ''
            if issue_code == 'REVERSAL':
                # Try to pick up a txn code from clipboard if we don't have one yet
                if not self._reversal_txn_code:
                    try:
                        clip = self.root.clipboard_get().strip()
                    except Exception:
                        clip = ''
                    if (clip and re.fullmatch(r'[A-Za-z0-9]{8,12}', clip)
                            and re.search(r'[A-Za-z]', clip)):
                        self._reversal_txn_code = clip.upper()
                # Prepend txn code to output if we have one and notes are selected
                if self._reversal_txn_code and notes:
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

            issue_code = self.current_raw_issue.get('issue_code', '') if self.current_raw_issue else ''
            output = self.vetting_engine.format_vetting_output(
                fields_to_output, serial_no=serial,
                issue_label=self.current_issue['display_name'] if self.current_issue else "",
                extra_notes=notes,
                issue_code=issue_code)

        self.output_text.delete("1.0", tk.END)
        self.output_text.insert("1.0", output)

    def _on_copy_output(self):
        text = self.output_text.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("Empty", "Generate output first")
            return
        # ── Telemetry: save completed workflow session ──────────────────
        self._log_action('COPY_OUTPUT', 'Workflow Complete')
        session_record = {
            'timestamp': time.time(),
            'issue':     self.current_raw_issue.get('issue_code', 'UNKNOWN')
                         if self.current_raw_issue else 'UNKNOWN',
            'sequence':  list(self._current_session),
        }
        self._workflow_logs.append(session_record)
        self.data_loader.save_json('workflow_logs.json', self._workflow_logs)
        self._current_session = []  # reset for the next call
        # ── End telemetry ───────────────────────────────────────────────
        self._copy(text)
        self._set_status("Interaction output copied to clipboard")
        self._reset_capture_state()
        # Auto-scroll output widget back to top
        self.output_text.yview_moveto(0.0)
        # In compact mode also scroll the main canvas to top
        if self._compact_mode and hasattr(self, '_compact_canvas'):
            self._compact_canvas.yview_moveto(0.0)

    def _on_copy_serial(self):
        sn = self.serial_var.get().strip()
        if not sn:
            messagebox.showwarning("Empty", "Enter a serial number first")
            return
        self._copy(sn)
        self._set_status("Serial copied — paste it, then output auto-copies (Ctrl+V or Win+A)")
        self._reset_capture_state()
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

    def _reset_capture_state(self):
        """Reset the dual-capture clipboard state (ring buffer)."""
        if hasattr(self, 'calling_no_var'):
            self.calling_no_var.set("—")
        if hasattr(self, 'target_no_var'):
            self.target_no_var.set("—")
        self._phone_ring_index = 0

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

    def _copy_number(self, num: str):
        """Copy a captured number back to the clipboard."""
        num = num.strip()
        if not num or num == "—":
            self._set_status("No number to copy")
            return
        self._copy(num)
        self._set_status(f"Number copied: {num}")

    def _poll_clipboard(self):
        """Poll clipboard every 500ms; auto-detect a 9-digit calling/target number.

        Uses a ring-buffer (modulo 2):
          1st number  → Box 1 (Calling No)
          2nd number  → Box 2 (Target No)
          3rd number  → replaces Box 1
          4th number  → replaces Box 2  … and so on.
        Numbers are never cleared by clicking output / serial widgets.
        """
        try:
            text = self.root.clipboard_get().strip()
        except Exception:
            text = ""
        if text and text != self._last_clipboard:
            self._last_clipboard = text
            digits = re.sub(r'\D', '', text)
            if len(digits) == 9:
                idx = getattr(self, '_phone_ring_index', 0)
                if idx % 2 == 0:
                    self.calling_no_var.set(digits)
                    self._set_status(f"Calling No (box 1): {digits}")
                else:
                    if hasattr(self, 'target_no_var'):
                        self.target_no_var.set(digits)
                    self._set_status(f"Target No (box 2): {digits}")
                    pass  # HLR is manual — agent clicks HLR button when ready
                self._phone_ring_index = idx + 1
            # Smart Listener: check for transaction ID
            self._check_txn_id_clipboard(text)
            # SR SLA Listener: check for SR number
            self._check_sr_clipboard(text)
        self.root.after(500, self._poll_clipboard)

    # ─── HLR SMART LISTENER ──────────────────────────────────────

    def _arm_hlr_paste_hook(self, phone_number: str) -> None:
        """No-op.  HLR is now fully manual (button-driven)."""
        pass

    def _fire_hlr_suffix(self) -> None:
        """No-op.  HLR is now fully manual (button-driven)."""
        pass

    def _disarm_hlr_paste_hook(self) -> None:
        """Cancel any pending HLR suffix timer.  Idempotent."""
        if self._hlr_timeout_id is not None:
            try:
                self.root.after_cancel(self._hlr_timeout_id)
            except Exception:
                pass
            self._hlr_timeout_id = None
        self._hlr_pending_suffix = ''

    def _copy_hlr_suffix(self, phone_number: str) -> None:
        """Manual double-click override: copy last 6 digits immediately.

        Args:
            phone_number: Value from calling_no_var or target_no_var StringVar.
        """
        phone_number = phone_number.strip()
        if not phone_number or phone_number == '\u2014':
            self._set_status("No number captured yet")
            return
        digits = re.sub(r'\D', '', phone_number)
        if len(digits) < 6:
            self._set_status("Number too short for HLR suffix")
            return
        suffix = digits[-6:]
        self._disarm_hlr_paste_hook()
        self._copy(suffix)
        self._last_clipboard = suffix
        self._set_status(f"HLR suffix copied manually: {suffix}")

    # ─── HELPERS ─────────────────────────────────────────────────

    def _on_clear(self):
        self.search_var.set("")
        self._hide_dropdown()
        self._last_crm_text = ''
        self.output_text.delete("1.0", tk.END)
        self.serial_var.set("")
        self.custom_note_var.set("")
        self.current_issue = None
        self.current_raw_issue = None
        self.extracted_fields = {}
        self.extracted_codes = []
        self._reversal_txn_code = ''
        self._reset_capture_state()
        self._smart_listener_armed = False
        self._detected_txn_id = ''
        self._sla_pending = ''
        self._disarm_sla_listener()
        self._sr_listener_armed = False
        self._detected_sr = ''
        self._sr_sla_pending = ''
        self._disarm_sr_sla_listener()
        self._disarm_paste_hook()       # disarm Hakikisha SMS clipboard queue hook
        self._disarm_hlr_paste_hook()   # disarm HLR suffix clipboard queue hook
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

    def _reset_for_new_issue(self):
        """Full clean-slate reset when switching issues: clears ALL previous
        output, fields, notes, and listener state.  Keeps search results,
        calling number, and favorites/history intact.
        """
        # ── Clear output widget ──
        self.output_text.delete("1.0", tk.END)

        # ── Clear all field entry StringVars ──
        for var in self.field_entries.values():
            try:
                var.set('')
            except Exception:
                pass

        # ── Clear data state ──
        self.extracted_fields = {}
        self.extracted_codes = []
        self._reversal_txn_code = ''
        self._skiza_tune_name = ''
        self._last_crm_text = ''
        self.serial_var.set('')
        self.custom_note_var.set('')
        self.vetting_result_var.set('pass')

        # ── Clear interaction note checkboxes (prevents stale output) ──
        self.note_vars = []
        for widget in self.notes_frame.winfo_children():
            widget.destroy()

        # ── Disarm smart reversal listener ──
        self._smart_listener_armed = False
        self._detected_txn_id = ''
        self._sla_pending = ''
        self._disarm_sla_listener()
        # ── Disarm SR SLA listener ──
        self._sr_listener_armed = False
        self._detected_sr = ''
        self._sr_sla_pending = ''
        self._disarm_sr_sla_listener()

    def _set_fields_frame_visible(self, visible: bool):
        """Show or hide the Step 2 fields frame, safely maintaining pack order
        in both full and compact layouts.
        """
        if visible:
            if self._compact_mode:
                # Re-insert fields_frame before notes/act/out widgets
                self.notes_frame.pack_forget()
                if hasattr(self, '_compact_act_row') and self._compact_act_row:
                    self._compact_act_row.pack_forget()
                if hasattr(self, '_compact_out_lf') and self._compact_out_lf:
                    self._compact_out_lf.pack_forget()
                self.fields_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)
                self.notes_frame.pack(fill=tk.X, padx=4, pady=2)
                if hasattr(self, '_compact_act_row') and self._compact_act_row:
                    self._compact_act_row.pack(fill=tk.X, padx=4, pady=2)
                if hasattr(self, '_compact_out_lf') and self._compact_out_lf:
                    self._compact_out_lf.pack(fill=tk.X, padx=4, pady=(2, 4))
            else:
                self.fields_frame.pack(fill=tk.BOTH, expand=True, pady=4)
        else:
            self.fields_frame.pack_forget()

    def _on_compact_focus_in(self, event=None):
        """Restore full opacity when the compact window gains focus."""
        if self._compact_mode and getattr(self, '_transparency_focus_active', False):
            self.root.attributes('-alpha', 1.0)

    def _on_compact_focus_out(self, event=None):
        """Fade to 75% opacity when the compact window loses focus."""
        if self._compact_mode and getattr(self, '_transparency_focus_active', False):
            self.root.attributes('-alpha', 0.75)

    # ─── SMART REVERSAL LISTENER (Sprint 4) ──────────────────────

    def _check_txn_id_clipboard(self, text):
        """Check if clipboard contains an M-PESA transaction ID (e.g. SIO3LK7Q4D).
        Arms the smart listener — waits indefinitely for SLA digit input.
        """
        if not text:
            return
        # Transaction IDs: 8-12 alphanumeric, must contain at least one letter
        if (re.fullmatch(r'[A-Za-z0-9]{8,12}', text)
                and re.search(r'[A-Za-z]', text)):
            txn = text.upper()
            if txn != self._detected_txn_id:
                self._detected_txn_id = txn
                self._smart_listener_armed = True
                self._sla_pending = ''
                self._reversal_txn_code = txn
                self._set_status(f"Txn ID detected: {txn} — type 2, 12, or 72 for SLA")
                self._arm_sla_listener()
                # Cancel any stale finalize timer — do NOT schedule one here;
                # finalize is only triggered after the agent types SLA digits.
                if hasattr(self, '_sla_timer_id') and self._sla_timer_id:
                    self.root.after_cancel(self._sla_timer_id)
                    self._sla_timer_id = None

    def _arm_sla_listener(self):
        """Listen for SLA keypresses (digits) using the keyboard library."""
        if not kb:
            return
        self._disarm_sla_listener()

        def _on_sla_key(event):
            if not self._smart_listener_armed:
                return
            key = event.name
            # Accept any digit — SLA values are '2', '12', '72'
            if key.isdigit():
                self.root.after(0, lambda k=key: self._handle_sla_digit(k))

        try:
            self._sla_hook = kb.on_press(_on_sla_key, suppress=False)
        except Exception:
            pass

    def _handle_sla_digit(self, digit):
        """Accumulate SLA digits. After 1500ms of silence, finalize."""
        if not self._smart_listener_armed:
            return
        # Cancel any pending finalize timer
        if hasattr(self, '_sla_timer_id') and self._sla_timer_id:
            self.root.after_cancel(self._sla_timer_id)
        self._sla_pending = getattr(self, '_sla_pending', '') + digit
        # Schedule finalize after 1500ms of silence
        self._sla_timer_id = self.root.after(1500, self._finalize_sla)

    def _finalize_sla(self):
        """Finalize the SLA selection based on accumulated digits.
        Also auto-selects the matching interaction note checkbox and
        updates the output widget (not just clipboard).

        Behaviour contract
        ------------------
        - pending == ''         → do nothing; stay armed (agent hasn't typed yet).
        - pending not in SLA_MAP → output Txn Code only; no SMS hook; disarm.
        - pending in SLA_MAP    → full output + SMS queue armed; disarm.
        """
        if not self._smart_listener_armed:
            return
        pending = getattr(self, '_sla_pending', '')

        # ── Guard: no digits typed yet → stay armed, do nothing ──────────
        if not pending:
            return

        # Map accumulated digits → SLA text and label
        SLA_MAP = {
            '2':  ("Reversal initiated sub advised on SLA of 2hrs educated on hakikisha.", "2hrs"),
            '12': ("Reversal initiated advised on 12 hrs SLA, hakikisha sms sent.", "12hrs"),
            '72': ("Reversal initiated sub advised on SLA of 72hrs and educated on hakikisha.", "72hrs"),
        }

        valid_sla = pending in SLA_MAP
        output = ""
        sla_label = "Txn Code Only"

        if not valid_sla:
            # Invalid digit sequence → output Txn Code only; no note, no default SLA
            output = self._detected_txn_id
            self._set_status(
                f"Reversal: invalid SLA '{pending}' — output set to Txn Code only"
            )
        else:
            sla_text, sla_label = SLA_MAP[pending]

            # Auto-select the matching checkbox in the interaction notes
            for note_text, var in self.note_vars:
                # Match by checking if the SLA text is (approximately) the note
                if sla_text.lower()[:30] in note_text.lower() or note_text.lower()[:30] in sla_text.lower():
                    var.set(True)
                    # Untick all others (radio-style)
                    for other_text, other_var in self.note_vars:
                        if other_var is not var:
                            other_var.set(False)
                    break

            # Build the full output
            output = f"{self._detected_txn_id}\n{sla_text}"
            self._set_status(f"Reversal output copied ({sla_label}) — Ctrl+V to paste, then SMS auto-loads")

        # Update the output text widget
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert("1.0", output)

        # Copy to clipboard
        self._copy(output)

        # Disarm SLA listener
        self._smart_listener_armed = False
        self._sla_pending = ''
        self._disarm_sla_listener()

        # Arm Sequential Clipboard Queue ONLY when a valid SLA was matched
        # (Txn Code Only path must not queue the Hakikisha SMS)
        if valid_sla:
            self._arm_paste_hook(sla_label)

    def _disarm_sla_listener(self):
        """Remove the SLA key listener."""
        if kb and hasattr(self, '_sla_hook') and self._sla_hook:
            try:
                kb.unhook(self._sla_hook)
            except Exception:
                pass
            self._sla_hook = None

    # ─── SEQUENTIAL CLIPBOARD QUEUE ──────────────────────────────

    def _arm_paste_hook(self, sla_label: str) -> None:
        """Queue Hakikisha SMS for automatic clipboard loading (EDR-safe).

        Uses a timer-based approach instead of keyboard hooks.  After a
        3-second delay (giving the agent time to paste the reversal output
        into the CRM), the Hakikisha SMS is automatically copied to the
        clipboard.

        Args:
            sla_label: Human-readable SLA label for the status bar.
        """
        # HLR hook must yield to Hakikisha
        self._disarm_hlr_paste_hook()
        # Disarm any previously lingering paste timer
        self._disarm_paste_hook()

        self._hakikisha_pending = True
        # 3-second delay: agent pastes reversal output -> hakikisha auto-loads
        self._paste_hook_timeout_id = self.root.after(
            3000, self._load_sms_to_clipboard
        )
        self._set_status(
            f"Reversal output copied ({sla_label}) \u2014 Hakikisha SMS auto-loads in 3s"
        )

    def _load_sms_to_clipboard(self) -> None:
        """Timer callback: load the Hakikisha SMS into the clipboard."""
        self._hakikisha_pending = False
        self._paste_hook_timeout_id = None

        hakikisha_text = ""
        snippet = self.snippet_engine.get_by_code("REVERSAL_HAKIKISHA")
        if snippet:
            hakikisha_text = snippet.get("text", "")

        if not hakikisha_text:
            hakikisha_text = (
                "Jambo, sasa ni rahisi kuhakikisha kwamba pesa zako "
                "zinaenda kwa nambari sahihi na M-PESA. HAKIKISHA kwa "
                "kubonyeza 1 KUKAMILISHA au 2 KUSIMAMISHA kutuma pesa."
            )

        self._copy(hakikisha_text)
        self._last_clipboard = hakikisha_text
        self._set_status("Hakikisha SMS loaded — Ctrl+V to send to customer")

    def _disarm_paste_hook(self) -> None:
        """Cancel any pending Hakikisha timer.  Idempotent."""
        self._hakikisha_pending = False
        if self._paste_hook_timeout_id is not None:
            try:
                self.root.after_cancel(self._paste_hook_timeout_id)
            except Exception:
                pass
            self._paste_hook_timeout_id = None

    # ─── SR SLA LISTENER ────────────────────────────────────

    def _check_sr_clipboard(self, text):
        """Check clipboard for an SR number matching the configured regex.
        If found (and not already armed for this SR), arm the SR SLA listener.

        The listener waits indefinitely — no expiry timer is started here.
        The 1500ms finalize timer is only started after the agent types the
        first SLA digit (in _handle_sr_sla_digit), mirroring the reversal
        smart listener design.
        """
        if not text:
            return
        try:
            m = re.fullmatch(self._sr_regex, text.strip(), re.IGNORECASE)
        except re.error:
            return  # invalid regex — ignore
        if m:
            sr = text.strip().upper()
            if sr != self._detected_sr:
                self._detected_sr = sr
                self._sr_listener_armed = True
                self._sr_sla_pending = ''
                self._set_status(f"SR detected: {sr} — type SLA hours (e.g. 24, 72, 168)")
                self._arm_sr_sla_listener()
                # Cancel any stale finalize timer — do NOT schedule one here;
                # finalize only triggers after the agent types SLA digits.
                if self._sr_sla_timer_id:
                    self.root.after_cancel(self._sr_sla_timer_id)
                    self._sr_sla_timer_id = None

    def _arm_sr_sla_listener(self):
        """Attach keyboard hook to capture SLA digits for SR note."""
        if not kb:
            return
        self._disarm_sr_sla_listener()  # clean up any previous hook

        def _on_sr_key(event):
            if not self._sr_listener_armed:
                return
            key = event.name
            if key.isdigit():
                self.root.after(0, lambda k=key: self._handle_sr_sla_digit(k))

        try:
            self._sr_sla_hook = kb.on_press(_on_sr_key, suppress=False)
        except Exception:
            pass

    def _handle_sr_sla_digit(self, digit):
        """Accumulate SLA digits. Reset 1500ms expiry timer on each keystroke."""
        if not self._sr_listener_armed:
            return
        # Cancel pending finalize/expiry timer
        if self._sr_sla_timer_id:
            self.root.after_cancel(self._sr_sla_timer_id)
        self._sr_sla_pending += digit
        # Schedule finalize after 1500ms of silence
        self._sr_sla_timer_id = self.root.after(1500, self._finalize_sr_sla)

    def _finalize_sr_sla(self):
        """Build SR interaction note in the exact format:
        '<SR> SR raised SLA <digits> hours', copy it, and reset.
        """
        if not self._sr_listener_armed:
            return
        pending = self._sr_sla_pending.strip()
        if not pending or not pending.isdigit():
            self._reset_sr_sla_state()
            return

        sr = self._detected_sr
        # Fixed format as required: "<SR> SR raised SLA <N> hours"
        note = f"{sr} SR raised SLA {pending} hours"

        # Copy to clipboard
        self._copy(note)

        # Show in the output widget
        try:
            self.output_text.delete("1.0", tk.END)
            self.output_text.insert("1.0", note)
        except Exception:
            pass

        self._set_status(f"✓ SR note copied — {sr}, SLA {pending}h")
        self._reset_sr_sla_state()

    def _expire_sr_sla(self):
        """Called when the 1500ms grace period expires with no digit input."""
        if self._sr_listener_armed and not self._sr_sla_pending:
            self._reset_sr_sla_state()
            self._set_status(f"SR listener expired (no SLA typed)")

    def _reset_sr_sla_state(self):
        """Fully disarm and clear all SR SLA listener state."""
        self._sr_listener_armed = False
        self._detected_sr = ''
        self._sr_sla_pending = ''
        if self._sr_sla_timer_id:
            self.root.after_cancel(self._sr_sla_timer_id)
            self._sr_sla_timer_id = None
        self._disarm_sr_sla_listener()

    def _disarm_sr_sla_listener(self):
        """Remove the SR SLA keyboard hook."""
        if kb and self._sr_sla_hook:
            try:
                kb.unhook(self._sr_sla_hook)
            except Exception:
                pass
            self._sr_sla_hook = None

    # ─── GUIDANCE EDITOR (Sprint 4) ──────────────────────────────

    def _save_user_guidance(self):
        """Persist the current guidance list to user_guidance.json.

        Only callable (Save button enabled) after at least one line has been
        added via the Add button in this session — prevents accidental
        duplicate saves from read-only views.
        """
        if not self.current_raw_issue:
            self._set_status("No issue selected — nothing to save")
            return
        if not getattr(self, '_guidance_has_pending_adds', False):
            self._set_status("Nothing to save — use ➕ Add or double-click a note to edit first")
            return

        issue_code = self.current_raw_issue.get('issue_code', '')
        lines = list(self._current_guidance)  # save exactly what's in memory

        user_guidance = self.data_loader.load_json('user_guidance.json')
        if not isinstance(user_guidance, dict):
            user_guidance = {}
        user_guidance[issue_code] = lines
        self.data_loader.save_json('user_guidance.json', user_guidance)

        self._user_guidance = user_guidance
        self._guidance_has_pending_adds = False
        # Disable Save button again until next Add
        try:
            self._guide_save_btn.configure(state=tk.DISABLED)
        except Exception:
            pass
        self._set_status(f"\u2713 Guidance saved for {issue_code} ({len(lines)} notes)")

    def _add_guidance_line(self):
        """Prompt for new guidance text, append it, enable Save, refresh widget."""
        if not self.current_raw_issue:
            self._set_status("Select an issue first")
            return

        from tkinter import simpledialog
        new_line = simpledialog.askstring(
            "Add Guidance Note",
            "Enter the new guidance note:",
            parent=self.root
        )
        if not new_line or not new_line.strip():
            return
        cleaned = new_line.strip()
        if cleaned in self._current_guidance:
            self._set_status("That note already exists — not added")
            return
        self._current_guidance.append(cleaned)
        self._guidance_has_pending_adds = True
        # Enable the Save button now that there's something new
        try:
            self._guide_save_btn.configure(state=tk.NORMAL)
        except Exception:
            pass
        self._filter_guidance()  # refresh display (respects any active filter)
        self._set_status(f"Note added — click 💾 Save to persist")

    def _edit_guidance_line(self, idx: int, original_text: str) -> None:
        """Open a pre-filled dialog to edit an existing guidance note in-place.

        Called on <Double-Button-1> from a guidance tag in _filter_guidance.
        On OK: replaces the note at *idx* in self._current_guidance, marks the
        session dirty (enables 💾 Save), and refreshes the guidance widget.
        On Cancel / no change: does nothing.

        Args:
            idx:           Index of the note in self._current_guidance.
            original_text: Current text of the note (used to pre-fill the dialog).
        """
        from tkinter import simpledialog
        edited = simpledialog.askstring(
            "Edit Guidance Note",
            "Edit the guidance note:",
            initialvalue=original_text,
            parent=self.root,
        )
        if edited is None:          # user cancelled
            return
        edited = edited.strip()
        if not edited or edited == original_text:
            return                  # nothing changed

        # Update in-memory list (guard against stale idx from filtered view)
        if 0 <= idx < len(self._current_guidance):
            self._current_guidance[idx] = edited
        else:
            # idx is a position in the full list but the filter may have shifted it;
            # fall back to replacing by original text value
            try:
                pos = self._current_guidance.index(original_text)
                self._current_guidance[pos] = edited
            except ValueError:
                self._set_status("Could not locate note to edit — try again")
                return

        self._guidance_has_pending_adds = True
        try:
            self._guide_save_btn.configure(state=tk.NORMAL)
        except Exception:
            pass
        self._filter_guidance(keyword=self._guidance_filter_var.get())
        self._set_status(f"Note updated — click 💾 Save to persist")

    # ── Inline filter helpers ─────────────────────────────────────

    def _on_guidance_filter_typed(self, *_):
        """Trace callback — fires on every keystroke in the filter entry.

        The entry is always a plain, empty field (no placeholder text inside).
        An empty string means 'show everything'; any text narrows the list.
        """
        if not hasattr(self, 'guidance_text'):
            return  # widget not yet built
        self._filter_guidance(keyword=self._guidance_filter_var.get())

    def _on_guidance_click(self, event):
        """Copy the full text of the clicked guidance line to the clipboard."""
        widget = self.guidance_text
        try:
            # Identify which line was clicked
            index = widget.index(f"@{event.x},{event.y}")
            line_start = widget.index(f"{index} linestart")
            line_end   = widget.index(f"{index} lineend")
            line_text  = widget.get(line_start, line_end).strip()
            # Strip the leading "– " bullet prefix
            if line_text.startswith("\u2013 "):
                line_text = line_text[2:]
            if line_text:
                self._increment_guidance(line_text)
                self._log_action('CLICK_GUIDANCE', line_text[:30])
                self._copy(line_text)
                self._set_status(f"Copied guidance: {line_text[:70]}")
        except Exception:
            pass

    def _increment_guidance(self, note_text: str) -> None:
        """Increment the click-count for a guidance note and persist to history.json.

        Used by _on_guidance_click to track which notes agents use most often.
        The counts power the smart-sort in _filter_guidance so high-frequency
        notes automatically rise to the top of the Guidance panel.

        Args:
            note_text: The raw guidance note string that was clicked.
        """
        usage = self._history.setdefault('guidance_usage', {})
        usage[note_text] = usage.get(note_text, 0) + 1
        self.data_loader.save_json('history.json', self._history)

    def _log_action(self, action: str, details: str = "") -> None:
        """Append one telemetry event to the in-progress session buffer.

        Intentionally lightweight: a single list.append so it never blocks
        the Tkinter mainloop.  The buffer is only flushed to disk inside
        _on_copy_output, meaning only *completed* workflows are persisted.

        Args:
            action:  Short uppercase verb that identifies the event type
                     (e.g. 'SEARCH', 'SELECT_ISSUE', 'PASTE_CRM').
            details: Optional free-text payload, kept to ≤ 60 chars by
                     callers to limit file-size growth.
        """
        self._current_session.append({
            'time':    time.time(),
            'action':  action,
            'details': details,
        })

    def _load_user_guidance(self, issue_code):
        """Load user-edited guidance overrides for an issue, if any."""
        if not self._user_guidance:
            self._user_guidance = self.data_loader.load_json('user_guidance.json')
            if not isinstance(self._user_guidance, dict):
                self._user_guidance = {}
        return self._user_guidance.get(issue_code, [])

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

    def _apply_context_menu_recursive(self, widget):
        """Walk a widget tree and attach the right-click menu to every Entry/Text."""
        if isinstance(widget, (ttk.Entry, tk.Entry, tk.Text, scrolledtext.ScrolledText)):
            self._make_context_menu(widget)
        for child in widget.winfo_children():
            self._apply_context_menu_recursive(child)

    # ─── RIGHT-CLICK CONTEXT MENU ────────────────────────────────

    def _make_context_menu(self, widget):
        """Bind a right-click Cut / Copy / Paste context menu to *widget*.

        Works for tk.Entry, ttk.Entry, tk.Text, and scrolledtext.ScrolledText.
        The menu is created on-demand each time to ensure it always reflects
        the widget's current state (e.g. selection, clipboard content).

        Args:
            widget: Any Tkinter text-input widget to attach the menu to.
        """
        def _show_menu(event):
            menu = tk.Menu(self.root, tearoff=0)

            # Determine which operations are valid right now
            has_sel = False
            try:
                if isinstance(widget, (tk.Text, scrolledtext.ScrolledText)):
                    has_sel = bool(widget.tag_ranges(tk.SEL))
                else:
                    has_sel = bool(widget.selection_present())
            except Exception:
                pass

            has_clip = False
            try:
                clip = self.root.clipboard_get()
                has_clip = bool(clip)
            except Exception:
                pass

            is_readonly = False
            try:
                state = str(widget.cget('state'))
                is_readonly = (state == tk.DISABLED)
            except Exception:
                pass

            # Cut
            menu.add_command(
                label="Cut",
                accelerator="Ctrl+X",
                state=tk.NORMAL if (has_sel and not is_readonly) else tk.DISABLED,
                command=lambda: widget.event_generate("<<Cut>>")
            )
            # Copy
            menu.add_command(
                label="Copy",
                accelerator="Ctrl+C",
                state=tk.NORMAL if has_sel else tk.DISABLED,
                command=lambda: widget.event_generate("<<Copy>>")
            )
            # Paste
            menu.add_command(
                label="Paste",
                accelerator="Ctrl+V",
                state=tk.NORMAL if (has_clip and not is_readonly) else tk.DISABLED,
                command=lambda: widget.event_generate("<<Paste>>")
            )
            menu.add_separator()
            # Select All
            menu.add_command(
                label="Select All",
                accelerator="Ctrl+A",
                command=lambda: (
                    widget.tag_add(tk.SEL, "1.0", tk.END)
                    if isinstance(widget, (tk.Text, scrolledtext.ScrolledText))
                    else widget.select_range(0, tk.END)
                )
            )

            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

        widget.bind("<Button-3>", _show_menu, add="+")

    # ─── CONTEXTUAL HELP — "ASK ME HOW" (Cheat Sheet) ───────────

    def _get_resource_path(self, relative_path: str) -> str:
        """
        Safely resolve resource paths for both local development and PyInstaller/MSIX
        executable environments.
        """
        try:
            # PyInstaller creates a temp folder and stores path in _MEIPASS
            base_path = sys._MEIPASS
        except AttributeError:
            # Running as normal Python script
            base_path = os.path.dirname(os.path.abspath(__file__))
            
        return os.path.join(base_path, relative_path)

    def _show_cheat_sheet(self) -> None:
        """
        Open a floating, non-blocking Toplevel displaying the SIM-swap cheat
        sheet PNG (or a clean text fallback if the image is missing).

        Design notes
        ------------
        - Non-blocking: uses tk.Toplevel, not a modal dialog.
        - Always-on-top: attributes('-topmost', True) keeps it above CRM windows.
        - Non-resizable: prevents the image from being distorted.
        - GC-safe: the PhotoImage reference is pinned to the label widget so
          Python's garbage collector cannot destroy it while the window is open.
        - Graceful fallback: if the PNG is missing, a readable text guide is
          displayed instead of crashing the application.
        """
        if self._help_window is not None and self._help_window.winfo_exists():
            self._help_window.lift()
            self._help_window.focus_force()
            return

        popup = tk.Toplevel(self.root)
        self._help_window = popup
        popup.title("💡 Ask me how — SIM Swap Cheat Sheet")
        popup.geometry("620x820")
        popup.resizable(False, False)
        popup.attributes("-topmost", True)
        popup.configure(bg="#F8F9FA")
        # ── Header bar ────────────────────────────────────────────────
        header = tk.Frame(popup, bg="#1A73E8", pady=8)
        header.pack(fill=tk.X)
        tk.Label(
            header,
            text="💡  SIM Swap — Step-by-Step Cheat Sheet",
            font=("Arial", 12, "bold"),
            fg="white",
            bg="#1A73E8",
        ).pack(padx=16)

        # ── Image area ────────────────────────────────────────────────
        img_path = self._get_resource_path(os.path.join("assets", "sim_swap_guide.png"))

        content_frame = tk.Frame(popup, bg="#F8F9FA")
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        if _PIL_AVAILABLE:
            try:
                pil_img = Image.open(img_path)
                
                target_w, target_h = 600, 740
                orig_w, orig_h = pil_img.size
                ratio = min(target_w / orig_w, target_h / orig_h)
                new_w = int(orig_w * ratio)
                new_h = int(orig_h * ratio)
                
                pil_img = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(pil_img)

                img_label = tk.Label(content_frame, image=photo, bg="#FFFFFF", width=target_w, height=target_h)
                img_label.pack()
                # ── GC pin: keep a reference on the widget itself ────
                img_label.image = photo

            except FileNotFoundError:
                self._cheat_sheet_text_fallback(content_frame)
            except Exception:
                self._cheat_sheet_text_fallback(content_frame)
        else:
            # Pillow not installed — show text guide
            self._cheat_sheet_text_fallback(content_frame)

        # ── Close button ──────────────────────────────────────────────
        tk.Button(
            popup,
            text="Close",
            command=popup.destroy,
            relief="flat",
            bg="#E8F0FE",
            fg="#1A73E8",
            activebackground="#C5D8FB",
            font=("Arial", 10, "bold"),
            padx=20,
            pady=6,
            cursor="hand2",
        ).pack(pady=(0, 12))

    def _cheat_sheet_text_fallback(self, parent: tk.Widget) -> None:
        """
        Render a clean plain-text cheat sheet when the PNG image is unavailable.

        Displayed when:
          - ``assets/sim_swap_guide.png`` does not exist.
          - Pillow (PIL) is not installed.

        Args:
            parent: The parent frame in which to render the text widget.
        """
        notice = tk.Label(
            parent,
            text=(
                "\u26a0\ufe0f  Cheat sheet image not found.\n"
                "Attempting to load text guide fallback."
            ),
            font=("Arial", 10),
            fg="#B8860B",
            bg="#FFF9E6",
            justify=tk.LEFT,
            padx=12,
            pady=8,
            relief="flat",
            wraplength=560,
        )
        notice.pack(fill=tk.X, pady=(0, 10))

        txt_path = self._get_resource_path(os.path.join("assets", "sim_swap_guide.txt"))
        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                guide_lines = f.read()
        except FileNotFoundError:
            guide_lines = (
                "ERROR: Fallback text file not found.\n\n"
                "Please ensure 'assets/sim_swap_guide.png' or 'assets/sim_swap_guide.txt' "
                "exists in the application directory."
            )
        except Exception as e:
            guide_lines = f"ERROR: Could not load fallback text guide: {str(e)}"

        txt = tk.Text(
            parent,
            font=("Consolas", 10),
            bg="white",
            fg="#202124",
            relief="flat",
            wrap=tk.WORD,
            padx=14,
            pady=10,
            state=tk.NORMAL,
            height=28,
        )
        txt.insert(tk.END, guide_lines)
        txt.configure(state=tk.DISABLED)

        sb = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        txt.pack(fill=tk.BOTH, expand=True)

    def _on_close(self):
        """Save state and close the application."""
        # Remove global hotkey hook
        if kb and self._hotkey_hook:
            try:
                kb.remove_hotkey(self._hotkey_hook)
            except Exception:
                pass

        # Disarm Sequential Clipboard Queue hooks
        self._disarm_paste_hook()
        self._disarm_hlr_paste_hook()

        # Unregister all remaining keyboard hooks
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

    def _open_issue_editor(self):
        """Open the graphical Issue Editor."""
        try:
            from editor_ui import IssueEditorUI
        except ImportError:
            messagebox.showerror("Error", "Issue Editor module not found.")
            return

        def on_saved():
            self._set_status("Reloading data...")
            # Reload issues into search engine
            issues_raw = self.data_loader.load_json('issues.json')
            self.issue_engine.issues = (
                issues_raw.get('issues', []) if isinstance(issues_raw, dict) else issues_raw
            )
            # Reload user guidance overrides
            ug = self.data_loader.load_json('user_guidance.json')
            self._user_guidance = ug if isinstance(ug, dict) else {}
            # Reload resolution engine if it exists
            if hasattr(self, 'resolution_engine'):
                res_raw = self.data_loader.load_json('resolutions.json')
                res_list = res_raw.get('resolutions', []) if isinstance(res_raw, dict) else res_raw
                self.resolution_engine.resolutions = res_list
            self._set_status("Data reloaded — new issue available in search.")
            self._on_clear()

        IssueEditorUI(self.root, self.data_loader, on_saved)


def main():
    # ── High-DPI awareness (Windows only) ──────────────────────────────
    # Must be called before tk.Tk() so the OS maps logical → physical
    # pixels correctly, eliminating the blurry "480p" scaling artefact.
    try:
        import ctypes
        # Windows 8.1+ (Per-Monitor DPI aware)
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            # Windows Vista / 7 fallback
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass  # Non-Windows or older OS — no action needed

    root = tk.Tk()
    app = AgentHelperUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
