"""
Agent Helper — CRM Adapter
============================
Plug-and-play interface between Agent Helper and any external CRM or REST API.

Design principles (Daraja SDK-inspired)
----------------------------------------
- Credentials are loaded once at startup from the .env file via python-dotenv.
  Nothing is hard-coded.
- ``fetch_customer_data(identifier)`` is the single stable public method.
  The rest of the application must call only this method; all network logic
  lives inside private helpers.
- Connecting a real API in the future requires changes only to
  ``_fetch_from_api()`` and ``_parse_api_response()``.  Zero changes to
  ``ui.py``, ``vetting_engine.py``, or any other module.

Security requirements
---------------------
- Credentials (API key, base URL) are stored only in the private ``_api_key``
  and ``_base_url`` attributes and are never passed to the logger.
- Customer identifiers (MSISDNs) are logged only at DEBUG level and only
  as a count / presence indicator — never as a raw value.
- The mock database used during development is replaced entirely when a real
  API is connected; it contains no production data.
"""

import logging
import os
from typing import Optional

_log = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv as _load_dotenv
    _DOTENV_AVAILABLE = True
except ImportError:
    _DOTENV_AVAILABLE = False
    _log.warning(
        "crm_adapter: python-dotenv is not installed. "
        "Run `pip install python-dotenv` to enable .env support."
    )

# Values that indicate a placeholder / unconfigured credential
_PLACEHOLDER_VALUES: frozenset = frozenset(
    {"", "your_api_key_here", "https://api.your-crm-provider.com/v1"}
)


class CRMAdapter:
    """
    Abstraction layer for all external CRM / REST API communication.

    Import the module-level singleton ``crm_adapter`` rather than
    instantiating this class directly::

        from crm_adapter import crm_adapter
        data = crm_adapter.fetch_customer_data(identifier)
    """

    def __init__(self) -> None:
        """Initialise attribute defaults and load configuration."""
        self._api_key: str = ""
        self._base_url: str = ""
        self._timeout: int = 10
        self._environment: str = "development"
        self._is_configured: bool = False
        self._load_config()

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def _load_config(self) -> None:
        """
        Load credentials from the .env file, then from OS environment variables.

        The .env file is resolved relative to this module's directory so the
        adapter works correctly regardless of the current working directory.

        Security: credential values are never passed to the logger.
        """
        if _DOTENV_AVAILABLE:
            env_path = os.path.join(os.path.dirname(__file__), ".env")
            loaded = _load_dotenv(dotenv_path=env_path, override=False)
            _log.debug(
                "crm_adapter._load_config: .env %s.",
                "loaded" if loaded else "not found — using OS environment",
            )

        self._api_key     = os.getenv("CRM_API_KEY", "").strip()
        self._base_url    = os.getenv("CRM_BASE_URL", "").strip()
        self._timeout     = int(os.getenv("CRM_TIMEOUT_SECONDS", "10"))
        self._environment = os.getenv("CRM_ENVIRONMENT", "development").strip()

        self._is_configured = (
            self._api_key not in _PLACEHOLDER_VALUES
            and self._base_url not in _PLACEHOLDER_VALUES
        )

        if self._is_configured:
            _log.info(
                "crm_adapter: configured — environment='%s'.", self._environment
            )
        else:
            _log.info(
                "crm_adapter: no live API configured. "
                "fetch_customer_data() will return None (clipboard fallback active)."
            )

    def reload_config(self) -> None:
        """
        Re-read the .env file at runtime.

        Useful after the user updates credentials through a settings panel
        without restarting the application.
        """
        _log.info("crm_adapter: reloading configuration.")
        self._load_config()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def fetch_customer_data(self, identifier: str) -> Optional[Dict]:
        """
        Fetch vetting data for *identifier* (MSISDN or account number).

        Args:
            identifier: Customer MSISDN or account number.

        Returns:
            Dict of vetting field labels → values compatible with
            ``VettingEngine.VETTING_FIELDS`` when data is available;
            ``None`` when no API is configured or no record is found
            (signals the caller to activate the clipboard-parse fallback).
        """
        if not identifier or not identifier.strip():
            _log.debug("crm_adapter.fetch_customer_data: empty identifier — skipped.")
            return None

        if not self._is_configured:
            return None

        return self._fetch_from_api(identifier.strip())

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _fetch_from_api(self, identifier: str) -> Optional[Dict]:
        """
        Internal method that executes the CRM API call.

        **Current state** — returns mock data so the full application stack
        can be exercised end-to-end without a live API.

        **To connect a real API**, replace the body of this method only::

            import requests
            headers = {"Authorization": f"Bearer {self._api_key}"}
            url = f"{self._base_url}/customers/{identifier}"
            try:
                response = requests.get(url, headers=headers,
                                        timeout=self._timeout)
                response.raise_for_status()
                return self._parse_api_response(response.json())
            except requests.RequestException as exc:
                _log.error("crm_adapter: API request failed — %s", exc)
                return None  # triggers clipboard fallback automatically

        Security: the identifier value is never logged here.

        Args:
            identifier: Stripped customer identifier (MSISDN / account number).

        Returns:
            Vetting data dict or ``None``.
        """
        _log.debug("crm_adapter._fetch_from_api: performing mock lookup.")

        # ----------------------------------------------------------------
        # MOCK DATABASE — replace entirely when connecting a real API.
        # Keys must match VettingEngine.VETTING_FIELDS for auto-mapping.
        # ----------------------------------------------------------------
        _mock_db: Dict[str, Dict] = {
            "0712345678": {
                "Name":    "Jane Doe",
                "ID":      "12345678",
                "YOB":     "1990",
                "MSISDN":  "0712345678",
                "MPESA":   "2500",
                "Airtime": "50",
            },
            "0798765432": {
                "Name":         "John Mwangi",
                "ID":           "87654321",
                "YOB":          "1985",
                "MSISDN":       "0798765432",
                "MPESA":        "800",
                "Airtime":      "0",
                "Fuliza Limit": "5000",
            },
        }

        data = _mock_db.get(identifier)
        if data is None:
            _log.debug("crm_adapter: no mock record found — returning None.")
        return data

    def _parse_api_response(self, raw: Dict) -> Optional[Dict]:
        """
        Transform a raw CRM API JSON payload into the VettingEngine field format.

        Customise the ``_key_map`` to match your specific CRM's response schema.

        Args:
            raw: Parsed JSON response dict from the CRM API.

        Returns:
            Mapped vetting dict, or ``None`` if *raw* is empty or no keys
            matched the mapping.
        """
        if not raw:
            return None

        _key_map: Dict[str, str] = {
            "full_name":       "Name",
            "national_id":     "ID",
            "year_of_birth":   "YOB",
            "phone_number":    "MSISDN",
            "mpesa_balance":   "MPESA",
            "airtime_balance": "Airtime",
            "fuliza_limit":    "Fuliza Limit",
        }

        mapped = {
            vetting_key: raw[crm_key]
            for crm_key, vetting_key in _key_map.items()
            if crm_key in raw and raw[crm_key]
        }
        return mapped or None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_configured(self) -> bool:
        """``True`` when real API credentials are loaded and non-placeholder."""
        return self._is_configured

    @property
    def environment(self) -> str:
        """Active environment label: ``development``, ``staging``, or ``production``."""
        return self._environment


# ---------------------------------------------------------------------------
# Module-level singleton — import this instance, not the class directly
# ---------------------------------------------------------------------------
from typing import Dict  # noqa: E402  (needed for _mock_db type annotation above)
crm_adapter = CRMAdapter()
