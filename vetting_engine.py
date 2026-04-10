"""
Vetting Engine for Agent Helper.
Extracts and validates customer vetting data from pasted CRM screens.
Generates copy-ready interaction text with only filled fields.
"""

import re
from datetime import datetime
from typing import Dict, List, Tuple
from text_utils import extract_vetting_fields_from_text

class VettingEngine:
    """Extract and validate customer vetting information."""

    # All possible vetting fields in display order
    VETTING_FIELDS = [
        'Name', 'ID', 'D.O.B', 'YOB', 'MSISDN', 'Contact No', 'Serial No',
        'MPESA', 'Airtime', 'Fuliza Limit',
        'M-Shwari Limit', '2FDNs', 'Registration Date',
        'KCB M-PESA Limit', '2Txn', 'Storo Target',
        'Last Bundle Purchase', 'Amount',
        'Fraud Location', 'CBS Status',
        'Activation Date', 'KYC Compliance', 'Account No',
    ]

    # SIM Swap output format: (output_label, internal_key)
    SIM_SWAP_OUTPUT = [
        ('serial no', 'Serial No'),
        ('name', 'Name'),
        ('id', 'ID'),
        ('yob', 'YOB'),
        ('mpesa bal', 'MPESA'),
        ('airtime Bal', 'Airtime'),
        ('Fuliza Limit', 'Fuliza Limit'),
        ('M-Shwari Limit', 'M-Shwari Limit'),
        ('2fdns', '2FDNs'),
        ('Registration date', 'Registration Date'),
        ('KCB M-PESA Limit', 'KCB M-PESA Limit'),
        ('2txn', '2Txn'),
        ('Storo Target', 'Storo Target'),
        ('Last Bundle Purchase', 'Last Bundle Purchase'),
    ]

    PIN_OUTPUT = [
        ('name', 'Name'),
        ('id', 'ID'),
        ('yob', 'YOB'),
        ('M-pesa bal', 'MPESA'),
        ('airtime Bal', 'Airtime'),
        ('Fuliza Limit', 'Fuliza Limit'),
        ('2fdns', '2FDNs'),
        ('M-Shwari Limit', 'M-Shwari Limit'),
        ('Registration date', 'Registration Date'),
        ('KCB M-PESA Limit', 'KCB M-PESA Limit'),
        ('2txn', '2Txn'),
        ('storo', 'Storo Target'),
        ('Last Bundle Purchase', 'Last Bundle Purchase'),
    ]

    PUK_OUTPUT = [
        ('name', 'Name'),
        ('id', 'ID'),
        ('yob', 'YOB'),
    ]

    RESUMING_OUTPUT = [
        ('name', 'Name'),
        ('id', 'ID'),
        ('mpesa bal', 'MPESA'),
        ('2fdns', '2FDNs'),
        ('airtime Bal', 'Airtime'),
        ('Fuliza Limit', 'Fuliza Limit'),
        ('M-Shwari Limit', 'M-Shwari Limit'),
        ('KCB M-PESA Limit', 'KCB M-PESA Limit'),
        ('Storo Target', 'Storo Target'),
        ('2txn', '2Txn'),
        ('Registration date', 'Registration Date'),
        ('Last Bundle Purchase', 'Last Bundle Purchase'),
    ]

    BONGA_OUTPUT = [
        ('name', 'Name'),
        ('id', 'ID'),
        ('mpesa bal', 'MPESA'),
        ('2fdns', '2FDNs'),
        ('airtime Bal', 'Airtime'),
        ('Fuliza Limit', 'Fuliza Limit'),
        ('M-Shwari Limit', 'M-Shwari Limit'),
        ('KCB M-PESA Limit', 'KCB M-PESA Limit'),
        ('Storo Target', 'Storo Target'),
        ('2txn', '2Txn'),
        ('Registration date', 'Registration Date'),
        ('Last Bundle Purchase', 'Last Bundle Purchase'),
    ]

    MPESA_AGENT_OUTPUT = [
        ('Operator ID', 'Operator ID'),
        ('Agent Number', 'Agent Number'),
        ('Agent name', 'Agent Name'),
        ('agent document ID Number', 'Agent ID Number'),
    ]

    TILL_SWAP_OUTPUT = [
        ('org name', 'Org Name'),
        ('store/till no', 'Store/Till No'),
        ('org contact', 'Org Contact'),
        ('serial no', 'Serial No'),
    ]

    TILL_PUK_OUTPUT = [
        ('org name', 'Org Name'),
        ('store/till no', 'Store/Till No'),
        ('org contact', 'Org Contact'),
    ]

    TILL_STARTKEY_OUTPUT = [
        ('Name', 'Name'),
        ('operator ID', 'Operator ID'),
        ('yob', 'YOB'),
        ('ID no', 'ID'),
        ('Store no/till', 'Store/Till No'),
        ('Account balance', 'Account Balance'),
        ('Recent outgoing transactions', 'Recent Outgoing Txn'),
    ]

    # Per-issue vetting config: headers for pass/fail_secondary/fail_primary + output fields
    VETTING_CONFIGS = {
        'SIM_SWAP': {
            'pass_header': ["Sub not in prison site", "Sim swap done vetted on:"],
            'fail_secondary_header': ["Sub advised to confirm details and call back, vetted on:"],
            'fail_primary_header': ["Failed primary vetting to visit RC for swap"],
            'output_fields': 'SIM_SWAP_OUTPUT',
        },
        'MPESA_STARTKEY_PIN': {
            'pass_header': ["Sub not in prison site, educated on DIY procedure and sms sent.", "Sub given start-key and vetted on:"],
            'fail_secondary_header': ["Failed secondary vetting, advised to confirm details and call back or visit RC."],
            'fail_primary_header': ["Failed primary vetting to visit RC for pin reset."],
            'output_fields': 'PIN_OUTPUT',
        },
        'MPESA_PIN_UNLOCK': {
            'pass_header': ["Sub not in prison site, educated on DIY procedure and sms sent.", "M-pesa pin unlocked and vetted on:"],
            'fail_secondary_header': ["Failed secondary vetting, advised to confirm details and call back or visit RC."],
            'fail_primary_header': ["Failed primary vetting to visit RC for pin unlock."],
            'output_fields': 'PIN_OUTPUT',
        },
        'PUK': {
            'pass_header': ["Educated on DIY procedure and sms sent.", "PUK given vetted on:"],
            'fail_primary_header': ["Failed vetting, advised to visit RC for PUK."],
            'output_fields': 'PUK_OUTPUT',
        },
        'RESUMING_LINE': {
            'pass_header': ["Sub not in prison site", "Line resumed sub vetted on:"],
            'fail_secondary_header': ["Failed secondary vetting, advised to confirm details and call back or visit RC."],
            'fail_primary_header': ["Failed primary vetting to visit RC for line resumption."],
            'output_fields': 'RESUMING_OUTPUT',
        },
        'BONGA_PIN': {
            'pass_header': ["Sub not in prison site", "Educated on DIY procedure and sms sent.", "Sub reset for bonga pin vetted on:"],
            'fail_secondary_header': ["Failed secondary vetting, advised to confirm details and call back or visit RC."],
            'fail_primary_header': ["Failed primary vetting to visit RC for bonga pin reset."],
            'output_fields': 'BONGA_OUTPUT',
        },
        'SUSPENDING_LINE': {
            'pass_header': ["Lost/stolen Line suspended mpesa as well sub vetted on:"],
            'pass_footer': ["Mpesa APP, Safaricom APP profile cleared."],
            'fail_primary_header': ["Failed vetting, advised to visit RC for line suspension."],
            'output_fields': 'PUK_OUTPUT',
        },
        'MPESA_AGENT': {
            'pass_header': ["Agent vetted on:"],
            'output_fields': 'MPESA_AGENT_OUTPUT',
            'manual_only': True,
        },
        'TILL_SWAP': {
            'pass_header': ["Swap done, Vetted on:"],
            'fail_primary_header': ["Failed vetting, advised to visit RC for assistance."],
            'output_fields': 'TILL_SWAP_OUTPUT',
            'manual_only': True,
        },
        'TILL_PUK': {
            'pass_header': ["PUK issued, Vetted on:"],
            'fail_primary_header': ["Failed vetting, advised to visit RC for assistance."],
            'output_fields': 'TILL_PUK_OUTPUT',
            'manual_only': True,
        },
        'TILL_STARTKEY': {
            'pass_header': ["Start key issued", "vetted on:"],
            'fail_primary_header': ["Failed vetting, advised to visit RC for assistance."],
            'output_fields': 'TILL_STARTKEY_OUTPUT',
            'manual_only': True,
        },
    }

    # Minimum required fields per issue type (use display labels)
    REQUIRED_BY_ISSUE = {
        'SIM_SWAP': ['Name', 'ID', 'YOB'],
        'MPESA_STARTKEY_PIN': ['Name', 'ID', 'YOB'],
        'MPESA_PIN_UNLOCK': ['Name', 'ID', 'YOB'],
        'PUK': ['Name', 'ID', 'YOB'],
        'RESUMING_LINE': ['Name', 'ID'],
        'BONGA_PIN': ['Name', 'ID'],
        'SUSPENDING_LINE': ['Name', 'ID', 'YOB'],
    }

    def extract_from_text(self, text: str) -> Dict:
        """Extract vetting fields from pasted CRM screen text."""
        return extract_vetting_fields_from_text(text)

    def extract_from_form(self, form_data: Dict) -> Dict:
        """Extract vetting fields from form input."""
        extracted = {}
        for field in self.VETTING_FIELDS:
            if field in form_data and form_data[field]:
                extracted[field] = str(form_data[field]).strip()
        return extracted

    def validate(self, extracted_fields: Dict, issue_code: str = None) -> Dict:
        """Validate extracted vetting data."""
        missing = []
        required_fields = self.REQUIRED_BY_ISSUE.get(issue_code, ['Name', 'ID'])

        for field in required_fields:
            if field not in extracted_fields or not extracted_fields[field]:
                missing.append(field)

        if not extracted_fields:
            vetting_status = 'NO_DATA'
        elif missing:
            vetting_status = 'INCOMPLETE'
        else:
            vetting_status = 'COMPLETE'

        validation_errors = self._validate_field_formats(extracted_fields)
        if validation_errors and vetting_status == 'COMPLETE':
            vetting_status = 'INVALID_FORMAT'

        return {
            'is_complete': len(missing) == 0,
            'vetting_status': vetting_status,
            'missing_fields': missing,
            'extracted_fields': extracted_fields,
            'validation_errors': validation_errors,
            'field_count': len(extracted_fields),
            'required_fields': required_fields
        }

    def format_vetting_output(self, extracted_fields: Dict, serial_no: str = "",
                               issue_label: str = "SIM Swap",
                               extra_notes: List[str] = None) -> str:
        """
        Build copy-ready interaction text.
        Only includes fields that have values.
        Adds serial_no (manually entered) and interaction notes on top.
        """
        lines = []

        # Interaction notes on top
        if extra_notes:
            for note in extra_notes:
                lines.append(note)
            lines.append("")

        # Only output fields that have a value
        for field in self.VETTING_FIELDS:
            value = extracted_fields.get(field, "")
            if value:
                lines.append(f"{field}: {value}")

        # Serial number (always include if provided — entered manually)
        if serial_no and serial_no.strip():
            # Insert serial after Name/ID/YOB if they exist, otherwise at the end
            serial_line = f"Serial No: {serial_no.strip()}"
            if serial_line not in lines:
                # Find best position (after YOB or at start of list)
                insert_idx = 0
                for i, line in enumerate(lines):
                    if line.startswith("YOB:") or line.startswith("ID:") or line.startswith("Name:"):
                        insert_idx = i + 1
                # Skip past notes section
                note_end = 0
                for i, line in enumerate(lines):
                    if line == "":
                        note_end = i + 1
                        break
                insert_idx = max(insert_idx, note_end)
                lines.insert(insert_idx, serial_line)

        return "\n".join(lines)

    def format_sim_swap_output(self, fields: Dict, vetting_result: str) -> str:
        """Legacy wrapper — delegates to format_vetting_result."""
        return self.format_vetting_result(fields, vetting_result, 'SIM_SWAP')

    def format_vetting_result(self, fields: Dict, vetting_result: str, issue_code: str) -> str:
        """
        Generate interaction output based on vetting result for any vetting issue.

        vetting_result: 'pass', 'fail_primary', 'fail_secondary'
        issue_code: e.g. 'SIM_SWAP', 'MPESA_STARTKEY_PIN'
        """
        config = self.VETTING_CONFIGS.get(issue_code)
        if not config:
            return ""

        output_fields = getattr(self, config['output_fields'])
        lines = []

        if vetting_result == 'pass':
            lines.extend(config['pass_header'])
            for output_label, key in output_fields:
                val = fields.get(key, '')
                if val:
                    lines.append(f"{output_label}: {val}")
            if config.get('pass_footer'):
                lines.extend(config['pass_footer'])

        elif vetting_result == 'fail_secondary' and config.get('fail_secondary_header'):
            lines.extend(config['fail_secondary_header'])
            for output_label, key in output_fields:
                val = fields.get(key, '')
                if val:
                    lines.append(f"{output_label}: {val}")

        elif vetting_result == 'fail_primary':
            lines.extend(config['fail_primary_header'])
            for output_label, key in [('name', 'Name'), ('id', 'ID'), ('yob', 'YOB')]:
                val = fields.get(key, '')
                if val:
                    lines.append(f"{output_label}: {val}")

        return "\n".join(lines)

    def _validate_field_formats(self, fields: Dict) -> List[str]:
        """Validate field formats."""
        errors = []
        if 'ID' in fields:
            if not re.match(r'^\d+$', str(fields['ID']).replace(' ', '')):
                errors.append('id_invalid_format')
        if 'YOB' in fields:
            yob_str = str(fields['YOB']).strip()
            if not re.match(r'^\d{4}$', yob_str):
                errors.append('yob_invalid_format')
            else:
                year = int(yob_str)
                if year < 1900 or year > 2026:
                    errors.append('yob_invalid_range')
        return errors

    def get_status_color(self, status: str) -> str:
        """Get a UI color for vetting status."""
        return {'COMPLETE': 'green', 'INCOMPLETE': 'orange',
                'NO_DATA': 'gray', 'INVALID_FORMAT': 'red'}.get(status, 'gray')
