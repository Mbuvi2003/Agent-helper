"""
Data loader and persistence module for Agent Helper.
Handles loading, validating, and saving JSON data files.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Any, Optional

class DataLoader:
    """Load and manage local JSON data files."""
    
    def __init__(self, data_folder: str = "data"):
        """Initialize data loader with folder path."""
        self.data_folder = Path(data_folder)
        self.data_folder.mkdir(exist_ok=True)
        
    def load_json(self, filename: str) -> Dict[str, Any]:
        """Load JSON file with safe fallback."""
        filepath = self.data_folder / filename
        try:
            if filepath.exists():
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load {filename}: {e}")
        return {}
    
    def save_json(self, filename: str, data: Dict[str, Any]) -> bool:
        """Save JSON file with safe handling."""
        filepath = self.data_folder / filename
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except IOError as e:
            print(f"Error saving {filename}: {e}")
            return False
    
    def load_all(self) -> Dict[str, Any]:
        """Load all data files."""
        return {
            'issues': self.load_json('issues.json'),
            'snippets': self.load_json('snippets.json'),
            'resolutions': self.load_json('resolutions.json'),
            'settings': self.load_json('settings.json'),
            'history': self.load_json('history.json'),
            'favorites': self.load_json('favorites.json')
        }
