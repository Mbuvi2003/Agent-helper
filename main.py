"""
Agent Helper — Main Entry Point
Call Center Productivity Desktop Application

Bootstraps the logging subsystem and launches the Tkinter UI.
All path resolution is dynamic; no absolute paths are used.
"""

import logging
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging bootstrap
# Configured once here; all modules obtain a child logger via getLogger(__name__).
# SECURITY: log messages must never contain PII, MSISDNs, or clipboard content.
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

_log = logging.getLogger("agent_helper.main")

# ---------------------------------------------------------------------------
# Ensure the project root is importable regardless of working directory.
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))

from ui import main  # noqa: E402  (import after sys.path mutation is intentional)

if __name__ == "__main__":
    _log.info("Agent Helper starting.")
    main()
