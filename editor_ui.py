import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
import uuid


class IssueEditorUI:
    """Tabbed editor: Issue/Guidance editor + Smart SR Listener settings."""

    def __init__(self, parent, data_loader, on_save_callback):
        self.top = tk.Toplevel(parent)
        self.top.title("Issue & Guidance Editor")
        self.top.geometry("940x740")
        self.top.minsize(800, 600)
        self.top.transient(parent)
        self.top.grab_set()

        self.data_loader = data_loader
        self.on_save_callback = on_save_callback

        self.issues = []
        self._load_data()

        self.current_index = -1

        # ── Notebook: Issue Editor | Settings ──
        nb = ttk.Notebook(self.top)
        nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self._issues_tab = ttk.Frame(nb)
        self._settings_tab = ttk.Frame(nb)
        nb.add(self._issues_tab, text="  📝 Issue / Guidance Editor  ")
        nb.add(self._settings_tab, text="  ⚙ Smart SR Listener  ")

        self._build_issues_ui(self._issues_tab)
        self._build_settings_ui(self._settings_tab)

    # ─────────────────────────────────────────────────────────
    # DATA LOADING
    # ─────────────────────────────────────────────────────────

    def _load_data(self):
        issues_raw = self.data_loader.load_json('issues.json')
        self.issues = (
            issues_raw.get('issues', []) if isinstance(issues_raw, dict) else issues_raw
        )

    # ─────────────────────────────────────────────────────────
    # TAB 1 — ISSUE EDITOR
    # ─────────────────────────────────────────────────────────

    def _build_issues_ui(self, parent):
        paned = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # --- LEFT: issue list ---
        left_frame = ttk.Frame(paned, width=250)
        paned.add(left_frame, weight=1)

        ttk.Label(left_frame, text="Issues", font=("Arial", 12, "bold")).pack(anchor=tk.W, padx=4, pady=(4, 0))

        list_scroll = ttk.Scrollbar(left_frame)
        list_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.listbox = tk.Listbox(left_frame, yscrollcommand=list_scroll.set, exportselection=False)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        list_scroll.config(command=self.listbox.yview)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        btn_frame = ttk.Frame(left_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="➕ Add New", command=self._add_new).pack(
            side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(btn_frame, text="🗑️ Delete", command=self._delete_current).pack(
            side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        # --- RIGHT: editor form ---
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=3)

        canvas = tk.Canvas(right_frame, highlightthickness=0)
        vsb = ttk.Scrollbar(right_frame, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.form = ttk.Frame(canvas)
        self.form_id = canvas.create_window((0, 0), window=self.form, anchor='nw')

        self.form.bind('<Configure>',
                       lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',
                    lambda e: canvas.itemconfig(self.form_id, width=e.width))

        # ── Form fields ──
        row = 0

        def add_field(label_text, widget):
            nonlocal row
            ttk.Label(self.form, text=label_text, font=("Arial", 9, "bold")).grid(
                row=row, column=0, sticky=tk.NW, pady=5, padx=5)
            widget.grid(row=row, column=1, sticky=tk.EW, pady=5, padx=5)
            self.form.columnconfigure(1, weight=1)
            row += 1
            return widget

        self.var_code = tk.StringVar()
        self.var_name = tk.StringVar()
        self.var_cat = tk.StringVar()
        self.var_vetting = tk.BooleanVar()

        add_field("Issue Code (unique):", ttk.Entry(self.form, textvariable=self.var_code))
        add_field("Display Name:", ttk.Entry(self.form, textvariable=self.var_name))

        cats = sorted({i.get('category', 'GENERAL') for i in self.issues})
        self.cat_cb = ttk.Combobox(self.form, textvariable=self.var_cat, values=cats)
        add_field("Category:", self.cat_cb)

        self.txt_synonyms = tk.Text(self.form, height=2, width=40, font=("Arial", 9))
        add_field("Synonyms (comma-separated):", self.txt_synonyms)

        self.txt_keywords = tk.Text(self.form, height=2, width=40, font=("Arial", 9))
        add_field("Keywords (comma-separated):", self.txt_keywords)

        add_field("Requires Vetting?",
                  ttk.Checkbutton(self.form, text="Yes", variable=self.var_vetting))

        self.txt_vetting_fields = tk.Text(self.form, height=2, width=40, font=("Arial", 9))
        add_field("Vetting Fields (comma-separated):", self.txt_vetting_fields)
        ttk.Label(self.form, text="e.g. Name, ID, YOB, MPESA, Airtime",
                  foreground="gray").grid(row=row, column=1, sticky=tk.W, padx=5)
        row += 1

        self.txt_notes = scrolledtext.ScrolledText(self.form, height=5, width=40, font=("Arial", 9))
        add_field("Interaction Notes (one per line):", self.txt_notes)
        ttk.Label(self.form, text="These appear as checkboxes for CRM output.",
                  foreground="gray").grid(row=row, column=1, sticky=tk.W, padx=5)
        row += 1

        self.txt_guidance = scrolledtext.ScrolledText(self.form, height=6, width=40, font=("Arial", 9))
        add_field("Guidance / Advice (one per line):", self.txt_guidance)

        # Save buttons
        btn_box = ttk.Frame(self.form)
        btn_box.grid(row=row, column=0, columnspan=2, pady=15)
        ttk.Button(btn_box, text="💾 Apply Changes (Memory)",
                   command=self._save_current).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_box, text="✅ Save All to File & Close",
                   command=self._save_all).pack(side=tk.LEFT, padx=5)

        self._set_state(tk.DISABLED)
        self._populate_list()

    # ─────────────────────────────────────────────────────────
    # TAB 2 — SMART SR LISTENER SETTINGS
    # ─────────────────────────────────────────────────────────

    def _build_settings_ui(self, parent):
        """Settings panel for the Smart SR Listener feature."""
        # Load current values from settings.json
        sett = self.data_loader.load_json('settings.json')

        outer = ttk.Frame(parent)
        outer.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)

        # ── Header ──
        ttk.Label(outer, text="Smart SR Listener Configuration",
                  font=("Arial", 13, "bold")).grid(row=0, column=0, columnspan=2,
                                                    sticky=tk.W, pady=(0, 4))
        ttk.Label(outer,
                  text=("The SR Listener watches your clipboard. When it detects a string "
                        "matching the SR Regex, it arms a 1500 ms keyboard listener.\n"
                        "Type the SLA hours (e.g. 24, 72, 168) — the note is auto-generated "
                        "from the template and copied to your clipboard."),
                  foreground="gray", wraplength=680, justify=tk.LEFT,
                  font=("Arial", 9)).grid(row=1, column=0, columnspan=2,
                                          sticky=tk.W, pady=(0, 14))

        ttk.Separator(outer, orient=tk.HORIZONTAL).grid(
            row=2, column=0, columnspan=2, sticky=tk.EW, pady=(0, 14))

        def lbl(text, r):
            ttk.Label(outer, text=text, font=("Arial", 10, "bold")).grid(
                row=r, column=0, sticky=tk.NW, pady=6, padx=(0, 12))

        # ── SR Regex field ──
        lbl("SR Regex Pattern:", 3)
        self._var_sr_regex = tk.StringVar(
            value=sett.get('sr_regex', r'1-[A-Z0-9]+'))
        regex_entry = ttk.Entry(outer, textvariable=self._var_sr_regex, width=45,
                                font=("Consolas", 10))
        regex_entry.grid(row=3, column=1, sticky=tk.EW, pady=6)
        ttk.Label(outer,
                  text="Default: 1-[A-Z0-9]+   (use Python re.fullmatch syntax, case-insensitive)",
                  foreground="gray", font=("Arial", 8)).grid(
                      row=4, column=1, sticky=tk.W, padx=2)

        # ── Template field ──
        lbl("Note Template:", 5)
        self._var_sr_template = tk.StringVar(
            value=sett.get('sr_template',
                           'Escalated to backend. SR: [SR], SLA: [SLA] hours.'))
        tmpl_entry = ttk.Entry(outer, textvariable=self._var_sr_template, width=60,
                               font=("Consolas", 10))
        tmpl_entry.grid(row=5, column=1, sticky=tk.EW, pady=6)
        ttk.Label(outer,
                  text="Use [SR] as the SR placeholder and [SLA] as the typed hours placeholder.",
                  foreground="gray", font=("Arial", 8)).grid(
                      row=6, column=1, sticky=tk.W, padx=2)

        outer.columnconfigure(1, weight=1)

        # ── Preview ──
        ttk.Separator(outer, orient=tk.HORIZONTAL).grid(
            row=7, column=0, columnspan=2, sticky=tk.EW, pady=(14, 8))
        ttk.Label(outer, text="Live Preview:", font=("Arial", 10, "bold")).grid(
            row=8, column=0, sticky=tk.NW, pady=6)
        self._preview_var = tk.StringVar()
        preview_lbl = ttk.Label(outer, textvariable=self._preview_var,
                                font=("Consolas", 10), foreground="#1565C0",
                                wraplength=580, justify=tk.LEFT)
        preview_lbl.grid(row=8, column=1, sticky=tk.W, pady=6)

        def _update_preview(*_):
            tmpl = self._var_sr_template.get()
            sample = tmpl.replace('[SR]', '1-ABC12345').replace('[SLA]', '72')
            self._preview_var.set(sample)

        self._var_sr_template.trace_add('write', _update_preview)
        _update_preview()  # show immediately

        # ── Save button ──
        ttk.Separator(outer, orient=tk.HORIZONTAL).grid(
            row=9, column=0, columnspan=2, sticky=tk.EW, pady=(14, 8))
        btn_row = ttk.Frame(outer)
        btn_row.grid(row=10, column=0, columnspan=2, sticky=tk.W, pady=4)
        ttk.Button(btn_row, text="✅ Save SR Settings",
                   command=self._save_sr_settings).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_row, text="↺ Reset to Defaults",
                   command=lambda: (
                       self._var_sr_regex.set(r'1-[A-Z0-9]+'),
                       self._var_sr_template.set(
                           'Escalated to backend. SR: [SR], SLA: [SLA] hours.')
                   )).pack(side=tk.LEFT, padx=4)

        self._sr_status_var = tk.StringVar()
        ttk.Label(outer, textvariable=self._sr_status_var, foreground="green",
                  font=("Arial", 9)).grid(row=11, column=0, columnspan=2,
                                           sticky=tk.W, pady=4)

    def _save_sr_settings(self):
        """Persist SR regex + template to settings.json."""
        import re
        regex = self._var_sr_regex.get().strip()
        template = self._var_sr_template.get().strip()

        # Validate regex
        try:
            re.compile(regex)
        except re.error as exc:
            messagebox.showerror("Invalid Regex",
                                 f"The SR Regex is not valid:\n{exc}")
            return

        if '[SR]' not in template:
            messagebox.showwarning("Missing placeholder",
                                   "The template must contain [SR] as the SR placeholder.")
            return

        sett = self.data_loader.load_json('settings.json')
        if not isinstance(sett, dict):
            sett = {}
        sett['sr_regex'] = regex
        sett['sr_template'] = template

        if self.data_loader.save_json('settings.json', sett):
            self._sr_status_var.set(
                "✓ Saved — restart or reopen the app to apply changes.")
        else:
            messagebox.showerror("Error", "Failed to write settings.json.")

    # ─────────────────────────────────────────────────────────
    # ISSUE EDITOR HELPERS
    # ─────────────────────────────────────────────────────────

    def _populate_list(self):
        self.listbox.delete(0, tk.END)
        for issue in self.issues:
            self.listbox.insert(tk.END, issue.get('display_name', 'Unnamed'))

    def _set_state(self, state):
        for child in self.form.winfo_children():
            try:
                child.configure(state=state)
            except Exception:
                pass

    def _on_select(self, event=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        self.current_index = sel[0]
        issue = self.issues[self.current_index]

        self._set_state(tk.NORMAL)

        self.var_code.set(issue.get('issue_code', ''))
        self.var_name.set(issue.get('display_name', ''))
        self.var_cat.set(issue.get('category', 'GENERAL'))

        self.txt_synonyms.delete("1.0", tk.END)
        self.txt_synonyms.insert("1.0", ", ".join(issue.get('synonyms', [])))

        self.txt_keywords.delete("1.0", tk.END)
        self.txt_keywords.insert("1.0", ", ".join(issue.get('keywords', [])))

        self.var_vetting.set(issue.get('requires_vetting', False))

        self.txt_vetting_fields.delete("1.0", tk.END)
        self.txt_vetting_fields.insert("1.0", ", ".join(issue.get('vetting_fields', [])))

        self.txt_notes.delete("1.0", tk.END)
        self.txt_notes.insert("1.0", "\n".join(issue.get('interaction_notes', [])))

        self.txt_guidance.delete("1.0", tk.END)
        self.txt_guidance.insert("1.0", "\n".join(issue.get('guidance', [])))

    def _add_new(self):
        """Open the step-by-step wizard; on save, append the result to the list."""
        cats = sorted({i.get('category', 'GENERAL') for i in self.issues})
        def _on_wizard_save(issue_dict):
            self.issues.append(issue_dict)
            self._populate_list()
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(len(self.issues) - 1)
            self._on_select(None)
        AddIssueWizard(self.top, cats, self.data_loader, _on_wizard_save)

    def _delete_current(self):
        if self.current_index < 0:
            return
        if messagebox.askyesno("Confirm Delete",
                               "Are you sure you want to delete this issue?"):
            del self.issues[self.current_index]
            self.current_index = -1
            self._populate_list()
            self._set_state(tk.DISABLED)

    def _save_current(self):
        if self.current_index < 0:
            return
        issue = self.issues[self.current_index]
        issue['issue_code'] = self.var_code.get().strip().upper()
        issue['display_name'] = self.var_name.get().strip()
        issue['category'] = self.var_cat.get().strip().upper()
        issue['synonyms'] = [
            x.strip() for x in self.txt_synonyms.get("1.0", tk.END).strip().split(',')
            if x.strip()]
        issue['keywords'] = [
            x.strip() for x in self.txt_keywords.get("1.0", tk.END).strip().split(',')
            if x.strip()]
        issue['requires_vetting'] = self.var_vetting.get()
        issue['vetting_fields'] = [
            x.strip() for x in self.txt_vetting_fields.get("1.0", tk.END).strip().split(',')
            if x.strip()]
        issue['interaction_notes'] = [
            x.strip() for x in self.txt_notes.get("1.0", tk.END).strip().split('\n')
            if x.strip()]
        issue['guidance'] = [
            x.strip() for x in self.txt_guidance.get("1.0", tk.END).strip().split('\n')
            if x.strip()]
        self.issues[self.current_index] = issue
        self._populate_list()
        self.listbox.selection_set(self.current_index)

    def _save_all(self):
        file_path = self.data_loader.data_folder / "issues.json"
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                wrapper = json.load(f)
        except Exception:
            wrapper = {"issues": []}

        wrapper["issues"] = self.issues

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(wrapper, f, indent=2)
            if self.on_save_callback:
                self.on_save_callback()
            self.top.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save:\n{e}")


# ─────────────────────────────────────────────────────────────────────────────
# ADD ISSUE WIZARD  (multi-step frame-switching UI)
# ─────────────────────────────────────────────────────────────────────────────

# Vetting field lists
_PRIMARY_FIELDS = ["Name", "ID", "YOB"]
_FULL_EXTRA_FIELDS = [
    "MPESA", "Airtime", "Fuliza Limit", "M-Shwari Limit",
    "2FDNs", "Registration Date", "KCB M-PESA Limit",
    "2Txn", "Storo Target", "Last Bundle Purchase",
]
_FULL_FIELDS = _PRIMARY_FIELDS + _FULL_EXTRA_FIELDS

# Standard vetting outcomes
_VETTING_OUTCOMES = [
    ("pass",           "Pass — action done, vetted on:"),
    ("fail_secondary", "Fail Secondary — advise to confirm & call back"),
    ("fail_primary",   "Fail Primary — advise to visit RC"),
    ("failed_twice",   "Failed Twice — visit RC (escalated)"),
]


class AddIssueWizard:
    """Step-by-step Toplevel wizard for creating a new issue.

    Steps
    -----
    1  Issue name + category
    2  Vetting type  (Non-Vettable | Primary | Full)
    3  Vetting outcomes  [skipped for Non-Vettable]
    4  Pre-interaction template  [skipped for Non-Vettable]
    5  Guidance notes  → Save
    """

    ACCENT   = "#1565C0"
    BG_STEP  = "#F0F4FF"

    def __init__(self, parent, existing_categories, data_loader, on_save):
        self._on_save = on_save
        self._data_loader = data_loader

        self.win = tk.Toplevel(parent)
        self.win.title("Add New Issue — Wizard")
        self.win.geometry("640x520")
        self.win.minsize(540, 440)
        self.win.transient(parent)
        self.win.grab_set()
        self.win.resizable(True, True)

        # ── Data collected across steps ──
        self._data = {
            "name": tk.StringVar(),
            "category": tk.StringVar(value="GENERAL"),
            "vetting_type": tk.StringVar(value="none"),
            "outcomes": {},
            "template": tk.StringVar(),
            "guidance": "",
        }
        self._outcome_rows = {}  # populated by _build_step3

        self._cats = existing_categories or ["GENERAL"]

        # ── Step sequence maps ──
        # Non-vettable skips steps 3 & 4
        self._seq_none    = [0, 1, 4]   # indices into self._steps
        self._seq_vetting = [0, 1, 2, 4] # step 3 now holds per-outcome templates; step 4 removed from vetting
        self._seq = self._seq_vetting   # start assumption
        self._seq_pos = 0               # position within current sequence

        # ── Chrome: header + progress + content + nav ──
        self._build_chrome()

        # ── Build all step frames (hidden until needed) ──
        self._steps = [
            self._build_step1(),
            self._build_step2(),
            self._build_step3(),
            self._build_step4(),
            self._build_step5(),
        ]

        # Show first step
        self._show_step(self._seq[0])

    # ── Chrome ───────────────────────────────────────────────

    def _build_chrome(self):
        # Header bar
        hdr = tk.Frame(self.win, bg=self.ACCENT)
        hdr.pack(fill=tk.X)
        self._title_var = tk.StringVar()
        tk.Label(hdr, textvariable=self._title_var, bg=self.ACCENT, fg="white",
                 font=("Arial", 13, "bold"), pady=10, padx=16).pack(side=tk.LEFT)

        # Step indicator (dots row)
        dot_row = tk.Frame(self.win, bg="#E8EAF6")
        dot_row.pack(fill=tk.X)
        self._dots = []
        labels = ["Name", "Vetting", "Outcomes", "Template", "Guidance"]
        for i, lbl in enumerate(labels):
            f = tk.Frame(dot_row, bg="#E8EAF6")
            f.pack(side=tk.LEFT, expand=True)
            dot = tk.Label(f, text="●", font=("Arial", 10), bg="#E8EAF6",
                           fg="#BDBDBD", pady=4)
            dot.pack()
            tk.Label(f, text=lbl, font=("Arial", 7), bg="#E8EAF6",
                     fg="#9E9E9E").pack()
            self._dots.append(dot)

        # Content area (steps are packed here)
        self._content = tk.Frame(self.win, bg=self.BG_STEP)
        self._content.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        # Nav bar: Back | step counter | Next/Save
        nav = tk.Frame(self.win, bg="#ECEFF1", pady=8)
        nav.pack(fill=tk.X, side=tk.BOTTOM)
        self._back_btn = ttk.Button(nav, text="◀ Back", command=self._go_back)
        self._back_btn.pack(side=tk.LEFT, padx=12)
        self._step_lbl = tk.Label(nav, text="", bg="#ECEFF1",
                                  font=("Arial", 8), fg="#757575")
        self._step_lbl.pack(side=tk.LEFT, expand=True)
        self._next_btn = ttk.Button(nav, text="Next ▶", command=self._go_next)
        self._next_btn.pack(side=tk.RIGHT, padx=12)

        # Error/hint label
        self._err_var = tk.StringVar()
        tk.Label(self.win, textvariable=self._err_var, fg="#C62828",
                 font=("Arial", 8), bg=self.BG_STEP).pack(side=tk.BOTTOM, pady=2)

    # ── Step builders ────────────────────────────────────────

    def _step_frame(self):
        f = tk.Frame(self._content, bg=self.BG_STEP, padx=24, pady=20)
        return f

    def _build_step1(self):
        f = self._step_frame()
        tk.Label(f, text="What is the issue called?", bg=self.BG_STEP,
                 font=("Arial", 11, "bold")).pack(anchor=tk.W, pady=(0, 6))
        tk.Label(f, text="Enter a clear display name (e.g. 'M-PESA PIN Unlock').",
                 bg=self.BG_STEP, font=("Arial", 9), fg="#555").pack(anchor=tk.W)
        ttk.Entry(f, textvariable=self._data["name"], width=42,
                  font=("Arial", 11)).pack(anchor=tk.W, pady=(12, 18))

        tk.Label(f, text="Category:", bg=self.BG_STEP,
                 font=("Arial", 9, "bold")).pack(anchor=tk.W)
        cb = ttk.Combobox(f, textvariable=self._data["category"],
                          values=self._cats, width=30)
        cb.pack(anchor=tk.W, pady=(4, 0))
        return f

    def _build_step2(self):
        f = self._step_frame()
        tk.Label(f, text="How is this issue vented?", bg=self.BG_STEP,
                 font=("Arial", 11, "bold")).pack(anchor=tk.W, pady=(0, 10))

        options = [
            ("none",    "Non-Vettable",
             "No customer identity check needed.\nSkips to Guidance directly."),
            ("primary", "Primary Vetting  (Name, ID, YOB)",
             "3-field check. Enables Pass / Fail outcomes."),
            ("full",    "Full Vetting  (Primary + all M-PESA fields)",
             "Complete vetting. Enables all outcomes."),
        ]
        for val, title, desc in options:
            row = tk.Frame(f, bg=self.BG_STEP, pady=6)
            row.pack(fill=tk.X)
            rb = tk.Radiobutton(row, variable=self._data["vetting_type"],
                                value=val, bg=self.BG_STEP,
                                activebackground=self.BG_STEP,
                                command=self._on_vetting_changed)
            rb.pack(side=tk.LEFT, anchor='n', padx=(0, 6))
            tk.Label(row, text=title, bg=self.BG_STEP,
                     font=("Arial", 10, "bold")).pack(anchor=tk.W)
            tk.Label(row, text=desc, bg=self.BG_STEP,
                     font=("Arial", 8), fg="#555",
                     justify=tk.LEFT).pack(anchor=tk.W, padx=(0, 0))
        return f

    def _build_step3(self):
        """Per-outcome panel: each outcome gets a checkbox, a prefix entry and a template box."""
        outer = self._step_frame()
        tk.Label(outer, text="Define each Vetting Outcome", bg=self.BG_STEP,
                 font=("Arial", 11, "bold")).pack(anchor=tk.W, pady=(0, 2))
        tk.Label(outer,
                 text=("Tick the outcomes that apply. For each, set the display prefix "
                       "(e.g. 'M-PESA PIN - Vetting Passed') and the exact text "
                       "that will be copied to the agent's clipboard."),
                 bg=self.BG_STEP, font=("Arial", 8), fg="#555",
                 wraplength=560, justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 8))

        # Scrollable canvas so many outcomes don't overflow
        canvas = tk.Canvas(outer, bg=self.BG_STEP, highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_inner = tk.Frame(canvas, bg=self.BG_STEP)
        scroll_id = canvas.create_window((0, 0), window=scroll_inner, anchor='nw')
        scroll_inner.bind('<Configure>',
                         lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',
                    lambda e: canvas.itemconfig(scroll_id, width=e.width))

        # _outcome_rows: key → {enabled: BoolVar, prefix: StringVar, template: Text}
        self._outcome_rows = {}

        _OUTCOME_DEFAULTS = {
            "pass":           ("Vetting Passed",          ""),
            "fail_secondary": ("Fail Secondary",          "Vetting failed secondary. Sub advised to confirm details and call back."),
            "fail_primary":   ("Fail Primary",            "Vetting failed. Sub advised to visit nearest Retail Center with valid ID."),
            "failed_twice":   ("Failed Twice",            "Sub failed vetting twice. Directed to Retail Center for manual verification."),
        }

        for key, (_, default_label) in zip(
                [k for k, _ in _VETTING_OUTCOMES], _VETTING_OUTCOMES):
            default_prefix, default_tmpl = _OUTCOME_DEFAULTS[key]
            enabled_var = tk.BooleanVar(value=True)
            prefix_var  = tk.StringVar(value=default_prefix)

            # Outer card frame
            card = tk.Frame(scroll_inner, bg="#FFFFFF",
                            relief=tk.RIDGE, bd=1)
            card.pack(fill=tk.X, pady=4, padx=2)

            # Header row: checkbox + label
            hdr = tk.Frame(card, bg="#FFFFFF")
            hdr.pack(fill=tk.X, padx=6, pady=(4, 2))
            tk.Checkbutton(
                hdr, variable=enabled_var, bg="#FFFFFF",
                activebackground="#FFFFFF",
                font=("Arial", 9, "bold"),
                text=default_label,
            ).pack(side=tk.LEFT)

            # Body: prefix + template (only visible when enabled)
            body = tk.Frame(card, bg="#FFFFFF")
            body.pack(fill=tk.X, padx=10, pady=(0, 6))

            tk.Label(body, text="Display Prefix:", bg="#FFFFFF",
                     font=("Arial", 8, "bold")).grid(row=0, column=0, sticky=tk.W, pady=2)
            ttk.Entry(body, textvariable=prefix_var, width=48,
                      font=("Arial", 9)).grid(row=0, column=1, sticky=tk.EW, padx=(6, 0), pady=2)

            tk.Label(body, text="Template text:", bg="#FFFFFF",
                     font=("Arial", 8, "bold")).grid(row=1, column=0, sticky=tk.NW, pady=2)
            tmpl_box = tk.Text(body, height=3, width=48, font=("Consolas", 8),
                               wrap=tk.WORD, relief=tk.SOLID, bd=1)
            tmpl_box.insert("1.0", default_tmpl)
            tmpl_box.grid(row=1, column=1, sticky=tk.EW, padx=(6, 0), pady=2)
            body.columnconfigure(1, weight=1)

            # Toggle body visibility on checkbox
            def _toggle(b=body, v=enabled_var):
                if v.get():
                    b.pack(fill=tk.X, padx=10, pady=(0, 6))
                else:
                    b.pack_forget()
            enabled_var.trace_add('write', lambda *_, t=_toggle: t())

            self._outcome_rows[key] = {
                "enabled": enabled_var,
                "prefix":  prefix_var,
                "tmpl":    tmpl_box,
            }
            # Also keep compat reference in _data["outcomes"]
            self._data["outcomes"][key] = enabled_var

        return outer

    def _build_step4(self):
        f = self._step_frame()
        tk.Label(f, text="Pre-interaction note template", bg=self.BG_STEP,
                 font=("Arial", 11, "bold")).pack(anchor=tk.W, pady=(0, 4))
        tk.Label(f,
                 text=("This text appears at the top of the interaction output.\n"
                       "Use [VETTING] as a placeholder — it is replaced by the vetting result block."),
                 bg=self.BG_STEP, font=("Arial", 9), fg="#555",
                 justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 10))
        self._template_text = scrolledtext.ScrolledText(
            f, height=7, width=52, font=("Consolas", 9), wrap=tk.WORD)
        self._template_text.pack(fill=tk.BOTH, expand=True)
        return f

    def _build_step5(self):
        f = self._step_frame()
        tk.Label(f, text="Guidance / Advice notes", bg=self.BG_STEP,
                 font=("Arial", 11, "bold")).pack(anchor=tk.W, pady=(0, 4))
        tk.Label(f,
                 text="One line per snippet. Click-to-copy in the main app.",
                 bg=self.BG_STEP, font=("Arial", 9), fg="#555").pack(anchor=tk.W, pady=(0, 10))
        self._guidance_text = scrolledtext.ScrolledText(
            f, height=9, width=52, font=("Consolas", 9), wrap=tk.WORD)
        self._guidance_text.pack(fill=tk.BOTH, expand=True)
        return f

    # ── Navigation ───────────────────────────────────────────

    def _on_vetting_changed(self):
        vt = self._data["vetting_type"].get()
        self._seq = self._seq_none if vt == "none" else self._seq_vetting

    def _show_step(self, step_idx):
        # Hide all
        for s in self._steps:
            s.pack_forget()
        # Show current
        self._steps[step_idx].pack(fill=tk.BOTH, expand=True)
        self._err_var.set("")

        # Refresh progress dots
        pos = self._seq.index(step_idx) if step_idx in self._seq else -1
        for i, dot in enumerate(self._dots):
            if i == step_idx:
                dot.configure(fg=self.ACCENT)
            elif i in self._seq and self._seq.index(i) < pos:
                dot.configure(fg="#66BB6A")
            else:
                dot.configure(fg="#BDBDBD")

        # Header title
        titles = [
            "Step 1 — Issue Name",
            "Step 2 — Vetting Type",
            "Step 3 — Vetting Outcomes",
            "Step 4 — Interaction Template",
            "Step 5 — Guidance Notes",
        ]
        self._title_var.set(titles[step_idx])
        n = len(self._seq)
        self._step_lbl.configure(text=f"Step {pos+1} of {n}")

        # Back button
        self._back_btn.configure(state=tk.NORMAL if pos > 0 else tk.DISABLED)

        # Next/Save button
        is_last = (pos == len(self._seq) - 1)
        self._next_btn.configure(
            text="💾 Save Issue" if is_last else "Next ▶",
            command=self._do_save if is_last else self._go_next,
        )

    def _go_next(self):
        cur = self._seq[self._seq_pos]
        # Validate before advancing
        if cur == 0:
            if not self._data["name"].get().strip():
                self._err_var.set("⚠ Please enter an issue name.")
                return
        # Re-read sequence (may have changed if vetting type just picked)
        self._on_vetting_changed()
        if self._seq_pos < len(self._seq) - 1:
            self._seq_pos += 1
            self._show_step(self._seq[self._seq_pos])

    def _go_back(self):
        if self._seq_pos > 0:
            self._seq_pos -= 1
            self._show_step(self._seq[self._seq_pos])

    # ── Save ─────────────────────────────────────────────────

    def _do_save(self):
        name = self._data["name"].get().strip()
        if not name:
            self._err_var.set("⚠ Issue name cannot be empty.")
            return

        vt = self._data["vetting_type"].get()
        requires_vetting = vt in ("primary", "full")
        vetting_fields = (
            _PRIMARY_FIELDS if vt == "primary" else
            _FULL_FIELDS    if vt == "full"    else []
        )

        # Interaction notes = display labels for enabled outcomes
        interaction_notes = [
            label for key, label in _VETTING_OUTCOMES
            if requires_vetting and self._outcome_rows.get(key, {}).get("enabled", tk.BooleanVar()).get()
        ] if requires_vetting else []

        guidance_lines = [
            ln.strip()
            for ln in self._guidance_text.get("1.0", tk.END).strip().splitlines()
            if ln.strip()
        ]

        issue_code = name.upper().replace(" ", "_")[:30]
        category   = self._data["category"].get().strip().upper() or "GENERAL"

        issue_dict = {
            "issue_code": issue_code,
            "display_name": name,
            "category": category,
            "synonyms": [name.lower()],
            "keywords": [w.lower() for w in name.split()[:4]],
            "requires_vetting": requires_vetting,
            "vetting_fields": vetting_fields,
            "interaction_notes": interaction_notes,
            "guidance": guidance_lines,
            "valid_resolutions": [],
        }

        try:
            self._save_issues(issue_dict)
            if requires_vetting:
                self._save_resolutions(issue_code, name)
            if guidance_lines:
                self._save_user_guidance(issue_code, guidance_lines)
        except Exception as exc:
            messagebox.showerror("Save Error", str(exc))
            return

        self._on_save(issue_dict)
        self.win.destroy()

    # ── JSON persistence ──────────────────────────────────────

    def _save_issues(self, issue_dict):
        raw = self._data_loader.load_json('issues.json')
        wrapper = raw if isinstance(raw, dict) else {"issues": raw}
        wrapper.setdefault("issues", []).append(issue_dict)
        if not self._data_loader.save_json('issues.json', wrapper):
            raise IOError("Failed to write issues.json")

    def _save_resolutions(self, issue_code, display_name):
        """Write one resolution entry per enabled outcome using per-outcome prefix + template."""
        _OUTCOME_META = {
            "pass":           ("PASS",    "approved"),
            "fail_secondary": ("FAIL2",   "escalated"),
            "fail_primary":   ("FAIL1",   "escalated"),
            "failed_twice":   ("FAIL_2X", "escalated"),
        }
        raw = self._data_loader.load_json('resolutions.json')
        wrapper = raw if isinstance(raw, dict) else {"resolutions": raw}
        resolutions = wrapper.setdefault("resolutions", [])

        for key, _ in _VETTING_OUTCOMES:
            row = self._outcome_rows.get(key, {})
            if not row.get("enabled", tk.BooleanVar()).get():
                continue
            suffix, outcome_lbl = _OUTCOME_META[key]
            prefix = row["prefix"].get().strip() or key.replace("_", " ").title()
            # Exact text from the template box — no date, no modification
            tmpl = row["tmpl"].get("1.0", tk.END).strip()
            resolutions.append({
                "resolution_code": f"{issue_code}_{suffix}",
                "display_name":    f"{display_name} - {prefix}",
                "issue_code":      issue_code,
                "outcome":         outcome_lbl,
                "advice":          tmpl,
                "next_step":       "",
                "template_text":   tmpl,
                "append_vetting":  True,
            })

        if not self._data_loader.save_json('resolutions.json', wrapper):
            raise IOError("Failed to write resolutions.json")

    def _save_user_guidance(self, issue_code, guidance_lines):
        raw = self._data_loader.load_json('user_guidance.json')
        ug = raw if isinstance(raw, dict) else {}
        ug[issue_code] = guidance_lines
        if not self._data_loader.save_json('user_guidance.json', ug):
            raise IOError("Failed to write user_guidance.json")

