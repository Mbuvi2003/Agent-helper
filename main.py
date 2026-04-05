"""
Agent Helper - Main Entry Point
Call Center Productivity Desktop Application
"""

import sys
import os
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from ui import main

if __name__ == "__main__":
    main()
