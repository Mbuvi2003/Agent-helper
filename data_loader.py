"""
Agent Helper — Data Loader
===========================
Handles all JSON data persistence for issues, snippets, resolutions,
settings, history, and favourites.

MSIX / Path Safety
------------------
Write operations target %LOCALAPPDATA%\\AgentHelper\\data so the app
functions correctly inside the MSIX sandbox without requiring elevated
permissions.  Read operations first check the writable LOCALAPPDATA
location, then fall back to the bundled read-only data directory shipped
inside the package — enabling first-run seeding of default data.
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path resolution helpers
# ---------------------------------------------------------------------------

_APP_NAME = "AgentHelper"


def _get_writable_data_dir() -> Path:
    """
    Return the writable data directory for the current platform.

    - Windows MSIX sandbox  : %LOCALAPPDATA%\\AgentHelper\\data
    - Dev / non-packaged    : <project_root>\\data
    """
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        writable = Path(local_app_data) / _APP_NAME / "data"
    else:
        # Fallback for non-Windows or missing env var
        writable = Path.home() / ".agenthelper" / "data"

    writable.mkdir(parents=True, exist_ok=True)
    return writable


def _get_bundled_data_dir() -> Path:
    """
    Return the read-only bundled data directory.

    - PyInstaller --onefile  : sys._MEIPASS/data  (temp extraction dir)
    - PyInstaller --onedir   : <exe_dir>/data
    - Dev environment        : <project_root>/data
    """
    if getattr(sys, "frozen", False):
        # _MEIPASS is set by onefile builds; fall back to exe dir for onedir
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).parent
    return base / "data"


def _seed_writable_dir(writable_dir: Path, bundled_dir: Path) -> None:
    """
    First-run seeding: copy any bundled data file that does not yet
    exist in the writable directory.  This ensures the app works
    identically to the Store version on a clean machine.
    """
    import shutil
    if not bundled_dir.exists():
        return
    for src in bundled_dir.iterdir():
        if src.is_file():
            dst = writable_dir / src.name
            if not dst.exists():
                try:
                    shutil.copy2(src, dst)
                    _log.info("DataLoader: seeded '%s' to writable dir.", src.name)
                except OSError as exc:
                    _log.warning("DataLoader: could not seed '%s' — %s", src.name, exc)


# ---------------------------------------------------------------------------
# DataLoader
# ---------------------------------------------------------------------------

class DataLoader:
    """
    Load and persist JSON data files for Agent Helper.

    Read strategy  : writable LOCALAPPDATA dir first, then bundled fallback.
    Write strategy : always writes to the writable LOCALAPPDATA dir.

    This dual-path approach ensures:
      - MSIX sandbox compliance (no writes to the install directory).
      - Seamless first-run experience (bundled defaults are auto-seeded).
    """

    def __init__(self, base_path: str = None) -> None:
        """Resolve and initialise both data directory paths."""
        self._writable_dir: Path = _get_writable_data_dir()

        if base_path:
            if getattr(sys, "frozen", False):
                meipass = getattr(sys, "_MEIPASS", None)
                base = Path(meipass) if meipass else Path(sys.executable).parent
                self._bundled_dir = base / base_path
            else:
                self._bundled_dir = Path(base_path).resolve()
        else:
            self._bundled_dir: Path = _get_bundled_data_dir()

        # Seed writable dir from bundled defaults on first run
        _seed_writable_dir(self._writable_dir, self._bundled_dir)

        _log.info(
            "DataLoader initialised. Writable: %s | Bundled: %s",
            self._writable_dir,
            self._bundled_dir,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def load_json(self, filename: str) -> Dict[str, Any]:
        """
        Load a JSON file by name.

        Checks the writable directory first; falls back to the bundled
        read-only directory if the file does not yet exist in the writable
        location.

        Args:
            filename: File name, e.g. ``"issues.json"``.

        Returns:
            Parsed dict, or an empty dict on error / missing file.
        """
        for directory in (self._writable_dir, self._bundled_dir):
            filepath = directory / filename
            if filepath.exists():
                try:
                    with open(filepath, "r", encoding="utf-8") as fh:
                        return json.load(fh)
                except (json.JSONDecodeError, IOError) as exc:
                    _log.error(
                        "DataLoader: failed to parse '%s' from %s — %s",
                        filename,
                        directory,
                        exc,
                    )
                    return {}

        _log.debug("DataLoader: '%s' not found in any data directory.", filename)
        return {}

    def save_json(self, filename: str, data: Dict[str, Any]) -> bool:
        """
        Serialise *data* and write it to the writable data directory.

        Args:
            filename: Target file name, e.g. ``"settings.json"``.
            data:     Serialisable dict.

        Returns:
            ``True`` on success, ``False`` on I/O error.
        """
        filepath = self._writable_dir / filename
        try:
            with open(filepath, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
            _log.debug("DataLoader: saved '%s'.", filename)
            return True
        except IOError as exc:
            _log.error("DataLoader: could not save '%s' — %s", filename, exc)
            return False

    def load_all(self) -> Dict[str, Any]:
        """
        Load all standard application data files in a single call.

        Unwraps inner wrapper keys (``issues``, ``snippets``, ``resolutions``)
        so callers receive plain lists.

        Returns:
            Dict with keys: ``issues``, ``snippets``, ``resolutions``,
            ``settings``, ``history``, ``favorites``.
        """
        issues_raw = self.load_json("issues.json")
        snippets_raw = self.load_json("snippets.json")
        resolutions_raw = self.load_json("resolutions.json")

        return {
            "issues": (
                issues_raw.get("issues", [])
                if isinstance(issues_raw, dict)
                else issues_raw
            ),
            "snippets": (
                snippets_raw.get("snippets", [])
                if isinstance(snippets_raw, dict)
                else snippets_raw
            ),
            "resolutions": (
                resolutions_raw.get("resolutions", [])
                if isinstance(resolutions_raw, dict)
                else resolutions_raw
            ),
            "settings": self.load_json("settings.json"),
            "history": self.load_json("history.json"),
            "favorites": self.load_json("favorites.json"),
        }
