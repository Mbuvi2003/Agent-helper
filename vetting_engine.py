"""
Vetting Engine for Agent Helper.
Extracts and validates customer vetting data.
"""

import re
from typing import Dict, List, Tuple
from text_utils import extract_vetting_fields_from_text

class VettingEngine:
    """Extract and validate customer vetting information."""
    
    # Standard vetting fields
    VETTING_FIELDS = [
        'name', 'id', 'yob', 'msisdn', 'serial_no', 'contact_no',
        'mpesa_balance', 'airtime_balance', 'fuliza_limit',
        'mshwari_limit', 'kcb_limit', 'registration_date',
        'last_bundle_purchase', '2fdns', '2txn', 'storo_target'
    ]
    
    # Required fields for different issue types
    REQUIRED_BY_ISSUE = {
        'SIM_SWAP': ['name', 'id', 'yob'],
        'MPESA_STARTKEY_PIN': ['name', 'id', 'yob'],
        'PUK': ['name', 'id', 'yob'],
        'LOAN_ISSUES': ['name', 'id'],
    }
    
    def extract_from_text(self, text: str) -> Dict:
        """Extract vetting fields from pasted text."""
        return extract_vetting_fields_from_text(text)
    
    def extract_from_form(self, form_data: Dict) -> Dict:
        """Extract vetting fields from form input."""
        extracted = {}
        for field in self.VETTING_FIELDS:
            if field in form_data and form_data[field]:
                extracted[field] = str(form_data[field]).strip()
        return extracted
    
    def validate(self, extracted_fields: Dict, issue_code: str = None) -> Dict:
        """
        Validate extracted vetting data.
        Returns validation status and missing fields.
        """
        has_required = False
        missing = []
        
        # Determine required fields for the issue
        required_fields = self.REQUIRED_BY_ISSUE.get(issue_code, ['name', 'id'])
        
        # Check which required fields are present
        for field in required_fields:
            if field not in extracted_fields or not extracted_fields[field]:
                missing.append(field)
            else:
                has_required = True
        
        # Determine vetting status
        if not extracted_fields:
            vetting_status = 'NO_DATA'
        elif missing:
            vetting_status = 'INCOMPLETE'
        else:
            vetting_status = 'COMPLETE'
        
        # Validate specific fields
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
    
    def _validate_field_formats(self, fields: Dict) -> List[str]:
        """Validate field formats."""
        errors = []
        
        # Validate ID (should be digits)
        if 'id' in fields:
            if not re.match(r'^\d+$', str(fields['id'])):
                errors.append('id_invalid_format')
        
        # Validate YOB (should be 4 digits, reasonable year)
        if 'yob' in fields:
            if not re.match(r'^\d{4}$', str(fields['yob'])):
                errors.append('yob_invalid_format')
            else:
                year = int(fields['yob'])
                if year < 1900 or year > 2024:
                    errors.append('yob_invalid_range')
        
        # Validate MSISDN (phone number)
        if 'msisdn' in fields:
            msisdn = str(fields['msisdn']).replace('+', '').replace('-', '')
            if not re.match(r'^254\d{9}$|\d{9,10}$', msisdn):
                errors.append('msisdn_invalid_format')
        
        return errors
    
    def get_status_color(self, status: str) -> str:
        """Get a UI color for vetting status."""
        colors = {
            'COMPLETE': 'green',
            'INCOMPLETE': 'orange',
            'NO_DATA': 'gray',
            'INVALID_FORMAT': 'red'
        }
        return colors.get(status, 'gray')
