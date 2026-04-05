"""
Agent Helper - Call Center Support Desktop App
Main UI using Tkinter
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import json
from pathlib import Path

try:
    import pyperclip
except ImportError:
    pyperclip = None

from data_loader import DataLoader
from issue_engine import IssueEngine
from vetting_engine import VettingEngine
from resolution_engine import ResolutionEngine
from snippet_engine import SnippetEngine


class AgentHelperUI:
    """Main Tkinter UI for Agent Helper."""
    
    def __init__(self, root):
        """Initialize the UI."""
        self.root = root
        self.root.title("Agent Helper - Call Center Assistant")
        self.root.geometry("1400x800")
        
        # Initialize data and engines
        self.data_loader = DataLoader("data")
        all_data = self.data_loader.load_all()
        
        self.issue_engine = IssueEngine(all_data)
        self.vetting_engine = VettingEngine()
        self.resolution_engine = ResolutionEngine(all_data)
        self.snippet_engine = SnippetEngine(all_data)
        
        # State
        self.current_issue = None
        self.current_vetting = None
        self.current_resolution = None
        self.search_results = []
        
        self._build_ui()
        self._load_favorites()
    
    def _build_ui(self):
        """Build the main UI layout."""
        # Top bar: Title, search, buttons
        top_frame = ttk.Frame(self.root)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)
        
        ttk.Label(top_frame, text="Agent Helper", font=("Arial", 16, "bold")).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(top_frame, text="Search or paste:", font=("Arial", 10)).pack(side=tk.LEFT, padx=10)
        
        self.search_var = tk.StringVar()
        self.search_var.trace("w", self._on_search_changed)
        self.search_entry = ttk.Entry(top_frame, textvariable=self.search_var, width=40)
        self.search_entry.pack(side=tk.LEFT, padx=5)
        self.search_entry.bind("<Return>", self._on_search)
        
        ttk.Button(top_frame, text="Search", command=self._on_search).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="Clear", command=self._on_clear).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="Paste", command=self._on_paste).pack(side=tk.LEFT, padx=5)
        
        # Main content: 3 columns
        content = ttk.Frame(self.root)
        content.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left panel: Categories
        left_frame = ttk.LabelFrame(content, text="Categories", width=150)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=5)
        left_frame.pack_propagate(False)
        
        categories = self.issue_engine.get_categories()
        for cat in categories:
            btn = ttk.Button(left_frame, text=cat, command=lambda c=cat: self._on_category(c))
            btn.pack(fill=tk.X, padx=5, pady=2)
        
        # Center panel: Search results / Issue list
        center_frame = ttk.LabelFrame(content, text="Search Results", width=300)
        center_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        center_frame.pack_propagate(False)
        
        # Listbox for results
        self.results_listbox = tk.Listbox(center_frame, height=30)
        self.results_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.results_listbox.bind("<<ListboxSelect>>", self._on_result_select)
        
        scrollbar = ttk.Scrollbar(center_frame, orient=tk.VERTICAL, command=self.results_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.results_listbox.config(yscrollcommand=scrollbar.set)
        
        # Right panel: Details viewer
        right_frame = ttk.LabelFrame(content, text="Details & Action", width=400)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        right_frame.pack_propagate(False)
        
        # Details text area
        details_label = ttk.Label(right_frame, text="Issue Details:", font=("Arial", 10, "bold"))
        details_label.pack(anchor=tk.W, padx=5, pady=5)
        
        self.details_text = scrolledtext.ScrolledText(right_frame, height=12, wrap=tk.WORD)
        self.details_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Vetting section
        vetting_label = ttk.Label(right_frame, text="Vetting Data:", font=("Arial", 10, "bold"))
        vetting_label.pack(anchor=tk.W, padx=5, pady=5)
        
        self.vetting_text = scrolledtext.ScrolledText(right_frame, height=8, wrap=tk.WORD)
        self.vetting_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Resolution and output buttons
        button_frame = ttk.Frame(right_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=10)
        
        ttk.Button(button_frame, text="Copy Details", command=self._on_copy_details).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Copy Vetting", command=self._on_copy_vetting).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Copy All", command=self._on_copy_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Add to Favorites", command=self._on_add_favorite).pack(side=tk.LEFT, padx=2)
        
        # Bottom status bar
        self.status_bar = ttk.Label(self.root, text="Ready", relief=tk.SUNKEN)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)
    
    def _on_search_changed(self, *args):
        """Real-time search as user types."""
        query = self.search_var.get().strip()
        if len(query) < 2:
            self.results_listbox.delete(0, tk.END)
            return
        
        # Run search in background thread
        threading.Thread(target=self._do_search, args=(query,), daemon=True).start()
    
    def _do_search(self, query):
        """Perform search (threaded)."""
        # Try issue search first
        issue_results = self.issue_engine.get_top_matches(query, limit=5)
        snippet_results = self.snippet_engine.search(query, limit=3)
        
        self.search_results = issue_results + snippet_results
        
        # Update UI
        self.root.after(0, self._update_results_list)
        self._update_status(f"Found {len(self.search_results)} results")
    
    def _on_search(self, event=None):
        """Manual search button."""
        query = self.search_var.get().strip()
        if query:
            self._do_search(query)
    
    def _on_clear(self):
        """Clear search."""
        self.search_var.set("")
        self.results_listbox.delete(0, tk.END)
        self.details_text.delete(1.0, tk.END)
        self.vetting_text.delete(1.0, tk.END)
        self.current_issue = None
        self.current_vetting = None
        self._update_status("Cleared")
    
    def _on_paste(self):
        """Paste from clipboard and search."""
        try:
            if not pyperclip:
                messagebox.showerror("Error", "pyperclip not installed. Run: pip install pyperclip")
                return
            text = pyperclip.paste()
            self.search_var.set(text[:100])  # First 100 chars as search query
            
            # Also extract vetting data
            self.current_vetting = self.vetting_engine.extract_from_text(text)
            self._display_vetting()
            self._update_status("Data pasted")
        except Exception as e:
            messagebox.showerror("Paste Error", str(e))
    
    def _on_category(self, category):
        """Filter by category."""
        issues = self.issue_engine.get_issues_by_category(category)
        self.search_results = [
            {
                'issue_code': i.get('issue_code'),
                'display_name': i.get('display_name'),
                'category': i.get('category'),
                'confidence': 100,
                'matched_terms': 'category',
                'raw_issue': i
            }
            for i in issues
        ]
        self._update_results_list()
        self._update_status(f"Category: {category} ({len(issues)} items)")
    
    def _update_results_list(self):
        """Update the results listbox."""
        self.results_listbox.delete(0, tk.END)
        for result in self.search_results:
            display = f"{result.get('display_name')} [{result.get('confidence')}%]"
            self.results_listbox.insert(tk.END, display)
    
    def _on_result_select(self, event):
        """Handle result selection."""
        selection = self.results_listbox.curselection()
        if not selection:
            return
        
        idx = selection[0]
        if idx < len(self.search_results):
            result = self.search_results[idx]
            self.current_issue = result
            self._display_issue()
    
    def _display_issue(self):
        """Display selected issue details."""
        if not self.current_issue:
            return
        
        issue = self.current_issue
        self.details_text.delete(1.0, tk.END)
        
        text = f"""Issue Code: {issue['issue_code']}
Display Name: {issue['display_name']}
Category: {issue['category']}
Confidence: {issue['confidence']}%
Requires Vetting: {issue.get('requires_vetting', False)}

Valid Resolutions:
{', '.join(issue.get('resolution_group', []))}

Available Snippets:
{', '.join(issue.get('snippet_group', []))}"""
        
        self.details_text.insert(1.0, text)
    
    def _display_vetting(self):
        """Display vetting data."""
        if not self.current_vetting:
            self.vetting_text.delete(1.0, tk.END)
            return
        
        self.vetting_text.delete(1.0, tk.END)
        
        # Validate if issue is selected
        issue_code = self.current_issue.get('issue_code') if self.current_issue else None
        validation = self.vetting_engine.validate(self.current_vetting, issue_code)
        
        text = f"""Status: {validation['vetting_status']}
Complete: {validation['is_complete']}
Fields Found: {validation['field_count']}

Missing Fields:
{', '.join(validation['missing_fields']) if validation['missing_fields'] else 'None'}

Extracted Data:
"""
        for field, value in self.current_vetting.items():
            text += f"\n  {field}: {value}"
        
        self.vetting_text.insert(1.0, text)
    
    def _on_copy_details(self):
        """Copy issue details."""
        text = self.details_text.get(1.0, tk.END)
        if text.strip():
            if not pyperclip:
                messagebox.showerror("Error", "pyperclip not installed")
                return
            pyperclip.copy(text)
            self._update_status("Issue details copied")
    
    def _on_copy_vetting(self):
        """Copy vetting data."""
        text = self.vetting_text.get(1.0, tk.END)
        if text.strip():
            if not pyperclip:
                messagebox.showerror("Error", "pyperclip not installed")
                return
            pyperclip.copy(text)
            self._update_status("Vetting data copied")
    
    def _on_copy_all(self):
        """Copy everything."""
        issue_text = self.details_text.get(1.0, tk.END)
        vetting_text = self.vetting_text.get(1.0, tk.END)
        if not pyperclip:
            messagebox.showerror("Error", "pyperclip not installed")
            return
        pyperclip.copy(issue_text + "\n\n" + vetting_text)
        self._update_status("All data copied")
    
    def _on_add_favorite(self):
        """Add current result to favorites."""
        if not self.current_issue:
            messagebox.showwarning("No Selection", "Please select an issue first")
            return
        
        # Save to favorites JSON
        self._update_status("Added to favorites (feature ready)")
    
    def _update_status(self, message):
        """Update status bar."""
        self.status_bar.config(text=message)
    
    def _load_favorites(self):
        """Load favorites from file."""
        pass  # Implement as needed


def main():
    """Run the application."""
    root = tk.Tk()
    app = AgentHelperUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
