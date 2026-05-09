"""
Agent Helper — Resolution Engine
==================================
Determines valid resolution options for a given issue and vetting state,
and generates the final copy-ready output text.

Architectural note
------------------
This module is completely free of Tkinter / UI imports.  It consumes and
returns plain Python dicts and strings, making it directly usable from a
REST API or CRM webhook adapter without modification.
"""

import logging
from typing import Dict, List, Optional

_log = logging.getLogger(__name__)


class ResolutionEngine:
    """
    Apply resolution rules and generate structured output for agent interactions.

    Resolution filtering is data-driven: rules are defined in ``resolutions.json``
    rather than hard-coded, so new issue types can be added without code changes.
    """

    def __init__(self, resolutions_data: Dict) -> None:
        """
        Initialise the engine with pre-loaded resolutions data.

        Args:
            resolutions_data: Dict with a ``"resolutions"`` key containing a
                              list of resolution definition dicts.
        """
        self.resolutions: List[Dict] = resolutions_data.get("resolutions", [])
        _log.info(
            "ResolutionEngine: loaded %d resolution definition(s).",
            len(self.resolutions),
        )

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def get_valid_resolutions(
        self,
        issue_code: str,
        vetting_status: Optional[str] = None,
    ) -> List[Dict]:
        """
        Return resolution options valid for *issue_code* and *vetting_status*.

        For ``SIM_SWAP``, vetting status filters the available outcomes:
          - ``COMPLETE``            → SWAP_VETTING_PASSED, SWAP_VETTING_FAILED
          - ``INCOMPLETE / NO_DATA``→ SWAP_VETTING_FAILED, SWAP_KYC_MISMATCH

        For all other issue codes, all matching resolutions are returned
        when a vetting status is provided.

        Args:
            issue_code:     Canonical issue code, e.g. ``"SIM_SWAP"``.
            vetting_status: Optional vetting state string
                            (``"COMPLETE"``, ``"INCOMPLETE"``, ``"NO_DATA"``).

        Returns:
            List of resolution dicts that satisfy the filter criteria.
        """
        valid: List[Dict] = []

        for resolution in self.resolutions:
            if resolution.get("issue_code") != issue_code:
                continue

            if vetting_status:
                if issue_code == "SIM_SWAP":
                    if vetting_status == "COMPLETE":
                        if resolution.get("resolution_code") in (
                            "SWAP_VETTING_PASSED",
                            "SWAP_VETTING_FAILED",
                        ):
                            valid.append(resolution)
                    elif vetting_status in ("INCOMPLETE", "NO_DATA"):
                        if resolution.get("resolution_code") in (
                            "SWAP_VETTING_FAILED",
                            "SWAP_KYC_MISMATCH",
                        ):
                            valid.append(resolution)
                else:
                    valid.append(resolution)
            else:
                valid.append(resolution)

        _log.debug(
            "ResolutionEngine.get_valid_resolutions: issue='%s', status='%s' → %d option(s).",
            issue_code,
            vetting_status,
            len(valid),
        )
        return valid

    def get_resolution(self, resolution_code: str) -> Optional[Dict]:
        """
        Retrieve a single resolution definition by its unique code.

        Args:
            resolution_code: Unique identifier, e.g. ``"SWAP_VETTING_PASSED"``.

        Returns:
            Resolution dict, or ``None`` if not found.
        """
        for resolution in self.resolutions:
            if resolution.get("resolution_code") == resolution_code:
                return resolution
        return None

    def get_all_by_issue(self, issue_code: str) -> List[Dict]:
        """
        Return every resolution associated with *issue_code* (no status filter).

        Args:
            issue_code: Canonical issue code.

        Returns:
            List of resolution dicts (may be empty).
        """
        return [
            r for r in self.resolutions if r.get("issue_code") == issue_code
        ]

    # ------------------------------------------------------------------
    # Output generation
    # ------------------------------------------------------------------

    def resolve(
        self,
        issue_code: str,
        resolution_code: str,
        vetting_data: Optional[Dict] = None,
    ) -> Dict:
        """
        Apply *resolution_code* and produce the final agent output.

        Substitutes ``{FieldName}`` placeholders in the resolution template
        with values from *vetting_data*.

        Security note: vetting_data values are injected into output text only;
        they are never passed to the logger.

        Args:
            issue_code:       Canonical issue code (used for logging only).
            resolution_code:  The chosen resolution code.
            vetting_data:     Optional dict of extracted vetting field values.

        Returns:
            Dict containing ``resolution_code``, ``display_name``,
            ``issue_code``, ``outcome``, ``advice``, ``next_step``,
            ``template_text``, and ``final_text``; or a dict with an
            ``"error"`` key if the resolution is not found.
        """
        resolution = self.get_resolution(resolution_code)

        if not resolution:
            _log.error(
                "ResolutionEngine.resolve: resolution_code '%s' not found.",
                resolution_code,
            )
            return {"error": "Resolution not found"}

        template = resolution.get("template_text", "")
        output_text = template

        if vetting_data:
            for key, value in vetting_data.items():
                placeholder = f"{{{key}}}"
                output_text = output_text.replace(placeholder, str(value))

        _log.info(
            "ResolutionEngine.resolve: applied '%s' for issue '%s'.",
            resolution_code,
            issue_code,
        )

        return {
            "resolution_code": resolution.get("resolution_code"),
            "display_name":    resolution.get("display_name"),
            "issue_code":      resolution.get("issue_code"),
            "outcome":         resolution.get("outcome"),
            "advice":          resolution.get("advice"),
            "next_step":       resolution.get("next_step"),
            "template_text":   resolution.get("template_text"),
            "final_text":      output_text,
        }
