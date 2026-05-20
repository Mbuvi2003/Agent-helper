"""
Agent Helper — Vetting Engine
==============================
Extracts, validates, and formats customer vetting data for agent interactions.

Data-source strategy
---------------------
``resolve_vetting_data(identifier, raw_text)`` is the primary entry-point.
It checks the CRM adapter first; if the adapter returns ``None`` (no API
configured, or no record found), it falls back transparently to parsing
*raw_text* with the existing regex-based clipboard logic.  The UI and all
output formatters are unaffected regardless of which source is used.

Architectural note
------------------
This module is completely free of Tkinter / UI imports.  It operates on
plain Python dicts and strings, making it directly consumable from a REST
API or CRM webhook adapter without modification.

Security note
-------------
Extracted field values are never passed to the logger.  Only structural
events (field counts, status labels, error codes) are logged.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple

from text_utils import extract_vetting_fields_from_text
from crm_adapter import crm_adapter

_log = logging.getLogger(__name__)


class VettingEngine:
    """
    Extract, validate, and format customer vetting information.

    All public methods accept and return plain dicts / strings; no Tkinter
    or UI dependencies exist in this module.
    """

    # ------------------------------------------------------------------
    # Field catalogue (display order)
    # ------------------------------------------------------------------

    VETTING_FIELDS: List[str] = [
        "Name", "ID", "D.O.B", "YOB", "MSISDN", "Contact No", "Serial No",
        "MPESA", "Airtime", "Fuliza Limit",
        "M-Shwari Limit", "2FDNs", "Registration Date",
        "KCB M-PESA Limit", "2Txn", "Storo Target",
        "Last Bundle Purchase", "Amount",
        "Fraud Location", "CBS Status",
        "Activation Date", "KYC Compliance", "Account No",
    ]

    # ------------------------------------------------------------------
    # Per-issue output field ordering: (output_label, internal_key)
    # ------------------------------------------------------------------

    SIM_SWAP_OUTPUT: List[Tuple[str, str]] = [
        ("serial no",            "Serial No"),
        ("name",                 "Name"),
        ("id",                   "ID"),
        ("yob",                  "YOB"),
        ("mpesa bal",            "MPESA"),
        ("airtime Bal",          "Airtime"),
        ("Fuliza Limit",         "Fuliza Limit"),
        ("M-Shwari Limit",       "M-Shwari Limit"),
        ("2fdns",                "2FDNs"),
        ("Registration date",    "Registration Date"),
        ("KCB M-PESA Limit",     "KCB M-PESA Limit"),
        ("2txn",                 "2Txn"),
        ("Storo Target",         "Storo Target"),
        ("Last Bundle Purchase", "Last Bundle Purchase"),
    ]

    PIN_OUTPUT: List[Tuple[str, str]] = [
        ("name",                 "Name"),
        ("id",                   "ID"),
        ("yob",                  "YOB"),
        ("M-pesa bal",           "MPESA"),
        ("airtime Bal",          "Airtime"),
        ("Fuliza Limit",         "Fuliza Limit"),
        ("2fdns",                "2FDNs"),
        ("M-Shwari Limit",       "M-Shwari Limit"),
        ("Registration date",    "Registration Date"),
        ("KCB M-PESA Limit",     "KCB M-PESA Limit"),
        ("2txn",                 "2Txn"),
        ("storo",                "Storo Target"),
        ("Last Bundle Purchase", "Last Bundle Purchase"),
    ]

    PUK_OUTPUT: List[Tuple[str, str]] = [
        ("name", "Name"),
        ("id",   "ID"),
        ("yob",  "YOB"),
    ]

    RESUMING_OUTPUT: List[Tuple[str, str]] = [
        ("name",                 "Name"),
        ("id",                   "ID"),
        ("mpesa bal",            "MPESA"),
        ("2fdns",                "2FDNs"),
        ("airtime Bal",          "Airtime"),
        ("Fuliza Limit",         "Fuliza Limit"),
        ("M-Shwari Limit",       "M-Shwari Limit"),
        ("KCB M-PESA Limit",     "KCB M-PESA Limit"),
        ("Storo Target",         "Storo Target"),
        ("2txn",                 "2Txn"),
        ("Registration date",    "Registration Date"),
        ("Last Bundle Purchase", "Last Bundle Purchase"),
    ]

    BONGA_OUTPUT: List[Tuple[str, str]] = [
        ("name",                 "Name"),
        ("id",                   "ID"),
        ("mpesa bal",            "MPESA"),
        ("2fdns",                "2FDNs"),
        ("airtime Bal",          "Airtime"),
        ("Fuliza Limit",         "Fuliza Limit"),
        ("M-Shwari Limit",       "M-Shwari Limit"),
        ("KCB M-PESA Limit",     "KCB M-PESA Limit"),
        ("Storo Target",         "Storo Target"),
        ("2txn",                 "2Txn"),
        ("Registration date",    "Registration Date"),
        ("Last Bundle Purchase", "Last Bundle Purchase"),
    ]

    MPESA_AGENT_OUTPUT: List[Tuple[str, str]] = [
        ("Operator ID",            "Operator ID"),
        ("Agent Number",           "Agent Number"),
        ("Agent name",             "Agent Name"),
        ("agent document ID Number", "Agent ID Number"),
    ]

    TILL_SWAP_OUTPUT: List[Tuple[str, str]] = [
        ("org name",     "Org Name"),
        ("store/till no", "Store/Till No"),
        ("org contact",  "Org Contact"),
        ("serial no",    "Serial No"),
    ]

    TILL_PUK_OUTPUT: List[Tuple[str, str]] = [
        ("org name",     "Org Name"),
        ("store/till no", "Store/Till No"),
        ("org contact",  "Org Contact"),
    ]

    TILL_STARTKEY_OUTPUT: List[Tuple[str, str]] = [
        ("Name",                         "Name"),
        ("operator ID",                  "Operator ID"),
        ("yob",                          "YOB"),
        ("ID no",                        "ID"),
        ("Store no/till",                "Store/Till No"),
        ("Account balance",              "Account Balance"),
        ("Recent outgoing transactions", "Recent Outgoing Txn"),
    ]

    # ------------------------------------------------------------------
    # Per-issue vetting configuration
    # ------------------------------------------------------------------

    VETTING_CONFIGS: Dict[str, Dict] = {
        "SIM_SWAP": {
            "pass_header":           ["Sub not in prison site", "Sim swap done vetted on:"],
            "fail_secondary_header": ["Sub advised to confirm details and call back, vetted on:"],
            "fail_primary_header":   ["Failed primary vetting to visit RC for swap"],
            "failed_twice_header":   ["Failed secondary vetting twice, to visit RC for swap"],
            "output_fields":         "SIM_SWAP_OUTPUT",
        },
        "MPESA_STARTKEY_PIN": {
            "pass_header":           ["Sub not in prison site, educated on DIY procedure and sms sent.", "Sub given start-key and vetted on:"],
            "fail_secondary_header": ["Failed secondary vetting, advised to confirm details and call back or visit RC."],
            "fail_primary_header":   ["Failed primary vetting to visit RC for pin reset."],
            "failed_twice_header":   ["Failed secondary vetting twice, to visit RC for start key"],
            "output_fields":         "PIN_OUTPUT",
        },
        "MPESA_PIN_UNLOCK": {
            "pass_header":           ["Sub not in prison site, educated on DIY procedure and sms sent.", "M-pesa pin unlocked and vetted on:"],
            "fail_secondary_header": ["Failed secondary vetting, advised to confirm details and call back or visit RC."],
            "fail_primary_header":   ["Failed primary vetting to visit RC for pin unlock."],
            "output_fields":         "PIN_OUTPUT",
        },
        "PUK": {
            "pass_header":         ["Educated on DIY procedure and sms sent.", "PUK given vetted on:"],
            "fail_primary_header": ["Failed vetting, advised to visit RC for PUK."],
            "output_fields":       "PUK_OUTPUT",
        },
        "RESUMING_LINE": {
            "pass_header":           ["Sub not in prison site", "Line resumed sub vetted on:"],
            "fail_secondary_header": ["Failed secondary vetting, advised to confirm details and call back or visit RC."],
            "fail_primary_header":   ["Failed primary vetting to visit RC for line resumption."],
            "output_fields":         "RESUMING_OUTPUT",
        },
        "BONGA_PIN": {
            "pass_header":           ["Sub not in prison site", "Educated on DIY procedure and sms sent.", "Sub reset for bonga pin vetted on:"],
            "fail_secondary_header": ["Failed secondary vetting, advised to confirm details and call back or visit RC."],
            "fail_primary_header":   ["Failed primary vetting to visit RC for bonga pin reset."],
            "output_fields":         "BONGA_OUTPUT",
        },
        "SUSPENDING_LINE": {
            "pass_header":         ["Lost/stolen Line suspended mpesa as well sub vetted on:"],
            "pass_footer":         ["Apps cleared."],
            "fail_primary_header": ["Failed vetting, advised to visit RC for line suspension."],
            "output_fields":       "PUK_OUTPUT",
        },
        "LINE_UNSUSPENSION": {
            "pass_header":           ["Sub not in prison site", "Line unsuspended, sub vetted on:"],
            "fail_secondary_header": ["Failed secondary vetting, advised to confirm details and call back or visit RC."],
            "fail_primary_header":   ["Failed primary vetting to visit RC for line unsuspension."],
            "failed_twice_header":   ["Failed secondary vetting twice, to visit RC for unsuspension"],
            "output_fields":         "PIN_OUTPUT",
        },
        "MPESA_AGENT": {
            "pass_header":   ["Agent vetted on:"],
            "output_fields": "MPESA_AGENT_OUTPUT",
            "manual_only":   True,
        },
        "TILL_SWAP": {
            "pass_header":         ["Swap done, Vetted on:"],
            "fail_primary_header": ["Failed vetting, advised to visit RC for assistance."],
            "output_fields":       "TILL_SWAP_OUTPUT",
            "manual_only":         True,
        },
        "TILL_PUK": {
            "pass_header":         ["PUK issued, Vetted on:"],
            "fail_primary_header": ["Failed vetting, advised to visit RC for assistance."],
            "output_fields":       "TILL_PUK_OUTPUT",
            "manual_only":         True,
        },
        "TILL_STARTKEY": {
            "pass_header":         ["Start key issued", "vetted on:"],
            "fail_primary_header": ["Failed vetting, advised to visit RC for assistance."],
            "output_fields":       "TILL_STARTKEY_OUTPUT",
            "manual_only":         True,
        },
    }

    # ------------------------------------------------------------------
    # Minimum required fields per issue type
    # ------------------------------------------------------------------

    REQUIRED_BY_ISSUE: Dict[str, List[str]] = {
        "SIM_SWAP":          ["Name", "ID", "YOB"],
        "MPESA_STARTKEY_PIN": ["Name", "ID", "YOB"],
        "MPESA_PIN_UNLOCK":  ["Name", "ID", "YOB"],
        "PUK":               ["Name", "ID", "YOB"],
        "RESUMING_LINE":     ["Name", "ID"],
        "BONGA_PIN":         ["Name", "ID"],
        "SUSPENDING_LINE":   ["Name", "ID", "YOB"],
        "LINE_UNSUSPENSION": ["Name", "ID", "YOB"],
    }

    # Private sentinel keys that must never appear in output
    _INTERNAL_KEYS: frozenset = frozenset({"_source"})

    # ------------------------------------------------------------------
    # Data resolution — CRM adapter → clipboard fallback
    # ------------------------------------------------------------------

    def resolve_vetting_data(
        self,
        identifier: str = "",
        raw_text: str = "",
    ) -> Dict[str, str]:
        """
        Primary entry-point for obtaining vetting data.

        Resolution strategy
        -------------------
        1. Query the CRM adapter with *identifier*.  If a non-``None`` dict
           is returned, use it and attach ``_source = 'crm_api'``.
        2. If the adapter returns ``None`` (no API configured, or no record
           found for this identifier), parse *raw_text* with the existing
           clipboard regex logic and attach ``_source = 'clipboard'``.

        The ``_source`` key is for internal / display use only; it is
        stripped automatically before any output is generated.

        Security: neither the identifier nor any extracted field values are
        logged here.

        Args:
            identifier: Customer MSISDN or account number passed to the
                        CRM adapter.
            raw_text:   Raw clipboard text used when the adapter is inactive.

        Returns:
            Dict of vetting fields (may be empty).  Includes a ``_source``
            key (``'crm_api'`` or ``'clipboard'``) for optional status display.
        """
        api_data: Optional[Dict] = crm_adapter.fetch_customer_data(identifier)

        if api_data is not None:
            _log.info(
                "resolve_vetting_data: sourced from CRM API "
                "(env=%s, fields=%d).",
                crm_adapter.environment,
                len(api_data),
            )
            api_data["_source"] = "crm_api"
            return api_data

        _log.debug(
            "resolve_vetting_data: CRM adapter returned None — "
            "activating clipboard fallback."
        )
        extracted = extract_vetting_fields_from_text(raw_text) if raw_text else {}
        extracted["_source"] = "clipboard"
        return extracted

    # ------------------------------------------------------------------
    # Extraction helpers
    # ------------------------------------------------------------------

    def extract_from_text(self, text: str) -> Dict[str, str]:
        """
        Extract vetting fields directly from *text* (clipboard / paste buffer).

        Prefer ``resolve_vetting_data()`` for new call-sites so that the CRM
        adapter layer is automatically engaged when configured.

        Args:
            text: Raw CRM screen text.

        Returns:
            Dict of extracted vetting fields.
        """
        return extract_vetting_fields_from_text(text)

    def extract_from_form(self, form_data: Dict) -> Dict[str, str]:
        """
        Extract vetting fields from manually entered form data.

        Args:
            form_data: Dict mapping field labels to raw input strings.

        Returns:
            Dict of non-empty, stripped field values present in
            ``VETTING_FIELDS``.
        """
        return {
            field: str(form_data[field]).strip()
            for field in self.VETTING_FIELDS
            if field in form_data and form_data[field]
        }

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(
        self,
        extracted_fields: Dict[str, str],
        issue_code: Optional[str] = None,
    ) -> Dict:
        """
        Validate *extracted_fields* against the requirements for *issue_code*.

        Args:
            extracted_fields: Dict of field label → value from extraction.
            issue_code:       Optional issue code to apply issue-specific
                              required-field rules.

        Returns:
            Dict with keys:
              - ``is_complete``       : bool
              - ``vetting_status``    : ``'COMPLETE'``, ``'INCOMPLETE'``,
                                        ``'NO_DATA'``, or ``'INVALID_FORMAT'``
              - ``missing_fields``    : list of missing required field labels
              - ``extracted_fields``  : the input dict (unmodified)
              - ``validation_errors`` : list of format-error codes
              - ``field_count``       : int
              - ``required_fields``   : list of required field labels applied
        """
        required_fields = self.REQUIRED_BY_ISSUE.get(issue_code, ["Name", "ID"])
        missing = [
            f for f in required_fields
            if f not in extracted_fields or not extracted_fields[f]
        ]

        if not extracted_fields:
            vetting_status = "NO_DATA"
        elif missing:
            vetting_status = "INCOMPLETE"
        else:
            vetting_status = "COMPLETE"

        validation_errors = self._validate_field_formats(extracted_fields)
        if validation_errors and vetting_status == "COMPLETE":
            vetting_status = "INVALID_FORMAT"

        _log.debug(
            "validate: status=%s, missing=%d, errors=%d.",
            vetting_status,
            len(missing),
            len(validation_errors),
        )

        return {
            "is_complete":       len(missing) == 0,
            "vetting_status":    vetting_status,
            "missing_fields":    missing,
            "extracted_fields":  extracted_fields,
            "validation_errors": validation_errors,
            "field_count":       len(extracted_fields),
            "required_fields":   required_fields,
        }

    # ------------------------------------------------------------------
    # Output formatting
    # ------------------------------------------------------------------

    def format_vetting_output(
        self,
        extracted_fields: Dict[str, str],
        serial_no: str = "",
        issue_label: str = "SIM Swap",
        extra_notes: Optional[List[str]] = None,
        issue_code: str = "",
    ) -> str:
        """
        Build copy-ready interaction text from *extracted_fields*.

        Only fields with non-empty values are included.  The ``_source``
        internal key is automatically excluded.

        Args:
            extracted_fields: Dict of vetting field label → value.
            serial_no:        Manually entered serial number (always appended
                              when provided, even if not in extracted_fields).
            issue_label:      Human-readable issue name (informational only).
            extra_notes:      Optional list of header note strings prepended
                              before field values.
            issue_code:       Canonical issue code; ``'PRS'`` triggers strict
                              name/ID/YOB-only formatting.

        Returns:
            Formatted multi-line string ready to copy into the CRM.
        """
        lines: List[str] = []
        fields = {
            k: v for k, v in extracted_fields.items()
            if k not in self._INTERNAL_KEYS
        }

        if issue_code == "PRS":
            for field in ("Name", "ID", "YOB"):
                val = fields.get(field, "")
                if val:
                    lines.append(f"{field}: {val}")
            if extra_notes:
                lines.extend(extra_notes)
            return "\n".join(lines)

        if extra_notes:
            lines.extend(extra_notes)
            lines.append("")

        for field in self.VETTING_FIELDS:
            value = fields.get(field, "")
            if value:
                lines.append(f"{field}: {value}")

        if serial_no and serial_no.strip():
            serial_line = f"Serial No: {serial_no.strip()}"
            if serial_line not in lines:
                insert_idx = 0
                for i, line in enumerate(lines):
                    if line.startswith(("YOB:", "ID:", "Name:")):
                        insert_idx = i + 1
                note_end = 0
                for i, line in enumerate(lines):
                    if line == "":
                        note_end = i + 1
                        break
                insert_idx = max(insert_idx, note_end)
                lines.insert(insert_idx, serial_line)

        return "\n".join(lines)

    def format_vetting_result(
        self,
        fields: Dict[str, str],
        vetting_result: str,
        issue_code: str,
        calling_no: str = "",
        target_no: str = "",
    ) -> str:
        """
        Generate the final interaction output for a vetting outcome.

        Args:
            fields:         Dict of vetting field label → value.
            vetting_result: Outcome code: ``'pass'``, ``'fail_primary'``,
                            ``'fail_secondary'``, or ``'failed_twice'``.
            issue_code:     Canonical issue code (must be in ``VETTING_CONFIGS``).
            calling_no:     Optional calling number (SIM_SWAP only).
            target_no:      Optional target number (SIM_SWAP only).

        Returns:
            Formatted multi-line string, or empty string for unknown issue codes.
        """
        config = self.VETTING_CONFIGS.get(issue_code)
        if not config:
            _log.warning(
                "format_vetting_result: unknown issue_code '%s'.", issue_code
            )
            return ""

        output_fields: List[Tuple[str, str]] = getattr(self, config["output_fields"])
        clean_fields = {
            k: v for k, v in fields.items() if k not in self._INTERNAL_KEYS
        }
        lines: List[str] = []

        if vetting_result == "pass":
            lines.extend(config["pass_header"])
            for output_label, key in output_fields:
                val = clean_fields.get(key, "")
                if val:
                    lines.append(f"{output_label}: {val}")
            if config.get("pass_footer"):
                lines.extend(config["pass_footer"])

        elif vetting_result == "fail_secondary" and config.get("fail_secondary_header"):
            lines.extend(config["fail_secondary_header"])
            for output_label, key in output_fields:
                if key.lower() in ("serial no", "serial_no", "serialno"):
                    continue
                val = clean_fields.get(key, "")
                if val:
                    lines.append(f"{output_label}: {val}")

        elif vetting_result == "failed_twice" and config.get("failed_twice_header"):
            lines.extend(config["failed_twice_header"])
            lines.append("")
            for output_label, key in output_fields:
                if key.lower() in ("serial no", "serial_no", "serialno"):
                    continue
                val = clean_fields.get(key, "")
                if val:
                    lines.append(f"{output_label}: {val}")

        elif vetting_result == "fail_primary":
            lines.extend(config["fail_primary_header"])
            for output_label, key in [("name", "Name"), ("id", "ID"), ("yob", "YOB")]:
                val = clean_fields.get(key, "")
                if val:
                    lines.append(f"{output_label}: {val}")

        return "\n".join(lines)

    def format_dynamic_vetting_result(
        self,
        fields: Dict[str, str],
        result: str,
        resolution_template: str,
        vetting_fields: Optional[List[str]] = None,
    ) -> str:
        """
        Generate output for dynamically created issues (not in ``VETTING_CONFIGS``).

        Builds output as: ``<resolution_template>\\n<vetting field values>``.
        No timestamps or filler text — only the prefix the administrator defined
        plus the extracted field data.

        Args:
            fields:               Dict of vetting field label → value.
            result:               Outcome code: ``'pass'``, ``'fail_secondary'``,
                                  ``'fail_primary'``, or ``'failed_twice'``.
            resolution_template:  Template prefix text as stored in
                                  ``resolutions.json``.
            vetting_fields:       Ordered list of field names to include.
                                  Defaults to all keys in *fields*.

        Returns:
            Formatted multi-line string.
        """
        lines: List[str] = []
        clean_fields = {
            k: v for k, v in fields.items() if k not in self._INTERNAL_KEYS
        }

        if resolution_template:
            lines.append(resolution_template)

        field_order = vetting_fields if vetting_fields else list(clean_fields.keys())

        if result in ("fail_primary", "failed_twice"):
            field_order = [f for f in field_order if f in ("Name", "ID", "YOB")]

        for field in field_order:
            val = clean_fields.get(field, "")
            if val:
                lines.append(f"{field}: {val}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Legacy wrapper
    # ------------------------------------------------------------------

    def format_sim_swap_output(self, fields: Dict[str, str], vetting_result: str) -> str:
        """
        Legacy compatibility wrapper — delegates to ``format_vetting_result``.

        Args:
            fields:         Vetting field dict.
            vetting_result: Outcome code string.

        Returns:
            Formatted output string for SIM_SWAP.
        """
        return self.format_vetting_result(fields, vetting_result, "SIM_SWAP")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _validate_field_formats(self, fields: Dict[str, str]) -> List[str]:
        """
        Check numeric / format constraints on key fields.

        Validates:
          - ``ID``: digits only (after stripping spaces).
          - ``YOB``: exactly 4 digits in the range 1900–2030.

        Security: field values are never passed to the logger.

        Args:
            fields: Extracted vetting field dict.

        Returns:
            List of error-code strings (empty list when all fields are valid).
        """
        errors: List[str] = []

        if "ID" in fields:
            if not re.match(r"^\d+$", str(fields["ID"]).replace(" ", "")):
                errors.append("id_invalid_format")

        if "YOB" in fields:
            yob_str = str(fields["YOB"]).strip()
            if not re.match(r"^\d{4}$", yob_str):
                errors.append("yob_invalid_format")
            else:
                year = int(yob_str)
                if year < 1900 or year > 2030:
                    errors.append("yob_invalid_range")

        return errors

    def get_status_color(self, status: str) -> str:
        """
        Map a vetting status label to a UI colour hint string.

        Args:
            status: Vetting status code string.

        Returns:
            Colour name string suitable for Tkinter ``fg`` / ``background``
            configuration (``'green'``, ``'orange'``, ``'red'``, ``'gray'``).
        """
        _colour_map: Dict[str, str] = {
            "COMPLETE":       "green",
            "INCOMPLETE":     "orange",
            "NO_DATA":        "gray",
            "INVALID_FORMAT": "red",
        }
        return _colour_map.get(status, "gray")
