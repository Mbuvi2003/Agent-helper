import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
import uuid

class IssueEditorUI:
    """A graphical editor for data/issues.json."""
    def __init__(self, parent, data_loader, on_save_callback):
        self.top = tk.Toplevel(parent)
        self.top.title("Issue & Guidance Editor")
        self.top.geometry("900x700")
        self.top.minsize(800, 600)
        self.top.transient(parent)
        self.top.grab_set()

        self.data_loader = data_loader
        self.on_save_callback = on_save_callback
        
        self.issues = []
        self._load_data()
        
        self.current_index = -1
        
        self._build_ui()
        self._populate_list()
        
    def _load_data(self):
        issues_raw = self.data_loader.load_json('issues.json')
        self.issues = issues_raw.get('issues', []) if isinstance(issues_raw, dict) else issues_raw
        
    def _build_ui(self):
        # PanedWindow for left list and right editor
        paned = ttk.PanedWindow(self.top, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # --- LEFT: List of issues ---
        left_frame = ttk.Frame(paned, width=250)
        paned.add(left_frame, weight=1)
        
        ttk.Label(left_frame, text="Issues", font=("Arial", 12, "bold")).pack(anchor=tk.W)
        
        list_scroll = ttk.Scrollbar(left_frame)
        list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.listbox = tk.Listbox(left_frame, yscrollcommand=list_scroll.set, exportselection=False)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        list_scroll.config(command=self.listbox.yview)
        
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        
        btn_frame = ttk.Frame(left_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="➕ Add New", command=self._add_new).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(btn_frame, text="🗑️ Delete", command=self._delete_current).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        
        # --- RIGHT: Editor Form ---
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=3)
        
        # Scrollable canvas for the form
        canvas = tk.Canvas(right_frame, highlightthickness=0)
        vsb = ttk.Scrollbar(right_frame, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.form = ttk.Frame(canvas)
        self.form_id = canvas.create_window((0, 0), window=self.form, anchor='nw')
        
        def _on_configure(e):
            canvas.configure(scrollregion=canvas.bbox('all'))
        self.form.bind('<Configure>', _on_configure)
        def _on_canvas_configure(e):
            canvas.itemconfig(self.form_id, width=e.width)
        canvas.bind('<Configure>', _on_canvas_configure)
        
        # Form Fields
        row = 0
        def add_field(label_text, widget):
            nonlocal row
            ttk.Label(self.form, text=label_text, font=("Arial", 9, "bold")).grid(row=row, column=0, sticky=tk.NW, pady=5, padx=5)
            widget.grid(row=row, column=1, sticky=tk.EW, pady=5, padx=5)
            self.form.columnconfigure(1, weight=1)
            row += 1
            return widget
            
        self.var_code = tk.StringVar()
        self.var_name = tk.StringVar()
        self.var_cat = tk.StringVar()
        self.var_vetting = tk.BooleanVar()
        
        code_entry = ttk.Entry(self.form, textvariable=self.var_code)
        add_field("Issue Code (unique):", code_entry)
        
        add_field("Display Name:", ttk.Entry(self.form, textvariable=self.var_name))
        
        # Categories combobox
        cats = sorted(list(set(i.get('category', 'GENERAL') for i in self.issues)))
        self.cat_cb = ttk.Combobox(self.form, textvariable=self.var_cat, values=cats)
        add_field("Category:", self.cat_cb)
        
        self.txt_synonyms = tk.Text(self.form, height=2, width=40, font=("Arial", 9))
        add_field("Synonyms (comma-separated):", self.txt_synonyms)
        
        self.txt_keywords = tk.Text(self.form, height=2, width=40, font=("Arial", 9))
        add_field("Keywords (comma-separated):", self.txt_keywords)
        
        add_field("Requires Vetting?", ttk.Checkbutton(self.form, text="Yes", variable=self.var_vetting))
        
        self.txt_vetting_fields = tk.Text(self.form, height=2, width=40, font=("Arial", 9))
        add_field("Vetting Fields (comma-separated):", self.txt_vetting_fields)
        ttk.Label(self.form, text="e.g. Name, ID, YOB, MPESA, Airtime", foreground="gray").grid(row=row, column=1, sticky=tk.W, padx=5); row+=1
        
        self.txt_notes = scrolledtext.ScrolledText(self.form, height=5, width=40, font=("Arial", 9))
        add_field("Interaction Notes (one per line):", self.txt_notes)
        ttk.Label(self.form, text="These appear as checkboxes for CRM output.", foreground="gray").grid(row=row, column=1, sticky=tk.W, padx=5); row+=1
        
        self.txt_guidance = scrolledtext.ScrolledText(self.form, height=6, width=40, font=("Arial", 9))
        add_field("Guidance / Advice (one per line):", self.txt_guidance)
        
        # Save Buttons
        btn_box = ttk.Frame(self.form)
        btn_box.grid(row=row, column=0, columnspan=2, pady=15)
        
        ttk.Button(btn_box, text="💾 Apply Changes (Memory)", command=self._save_current).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_box, text="✅ Save All to File & Close", command=self._save_all).pack(side=tk.LEFT, padx=5)
        
        self._set_state(tk.DISABLED)

    def _populate_list(self):
        self.listbox.delete(0, tk.END)
        for issue in self.issues:
            self.listbox.insert(tk.END, issue.get('display_name', 'Unnamed'))
            
    def _set_state(self, state):
        for child in self.form.winfo_children():
            try:
                child.configure(state=state)
            except:
                pass
                
    def _on_select(self, event):
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
        new_issue = {
            "issue_code": f"NEW_ISSUE_{uuid.uuid4().hex[:6].upper()}",
            "display_name": "New Issue",
            "category": "GENERAL",
            "synonyms": [],
            "keywords": [],
            "requires_vetting": False,
            "vetting_fields": [],
            "interaction_notes": [],
            "guidance": [],
            "valid_resolutions": []
        }
        self.issues.append(new_issue)
        self._populate_list()
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(len(self.issues) - 1)
        self._on_select(None)
        self.var_name.set("") # prompt them to edit
        
    def _delete_current(self):
        if self.current_index < 0:
            return
        if messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this issue?"):
            del self.issues[self.current_index]
            self.current_index = -1
            self._populate_list()
            self._set_state(tk.DISABLED)

    def _save_current(self):
        if self.current_index < 0:
            return
            
        issue = self.issues[self.current_index]
        
        # Gather data
        issue['issue_code'] = self.var_code.get().strip().upper()
        issue['display_name'] = self.var_name.get().strip()
        issue['category'] = self.var_cat.get().strip().upper()
        
        issue['synonyms'] = [x.strip() for x in self.txt_synonyms.get("1.0", tk.END).strip().split(',') if x.strip()]
        issue['keywords'] = [x.strip() for x in self.txt_keywords.get("1.0", tk.END).strip().split(',') if x.strip()]
        
        issue['requires_vetting'] = self.var_vetting.get()
        issue['vetting_fields'] = [x.strip() for x in self.txt_vetting_fields.get("1.0", tk.END).strip().split(',') if x.strip()]
        
        issue['interaction_notes'] = [x.strip() for x in self.txt_notes.get("1.0", tk.END).strip().split('\n') if x.strip()]
        issue['guidance'] = [x.strip() for x in self.txt_guidance.get("1.0", tk.END).strip().split('\n') if x.strip()]
        
        self.issues[self.current_index] = issue
        self._populate_list()
        self.listbox.selection_set(self.current_index)
        
    def _save_all(self):
        # We need to save to data/issues.json
        import os
        from pathlib import Path
        
        # Try to find where data_loader thinks issues.json is
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
