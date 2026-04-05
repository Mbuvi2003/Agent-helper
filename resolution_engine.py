"""
Resolution Engine for Agent Helper.
Determines valid resolutions based on issue + vetting state.
"""

from typing import Dict, List, Optional

class ResolutionEngine:
    """Apply resolution rules and generate outcomes."""
    
    def __init__(self, resolutions_data: Dict):
        """Initialize with resolutions data."""
        self.resolutions = resolutions_data.get('resolutions', [])
    
    def get_valid_resolutions(self, issue_code: str, vetting_status: str = None) -> List[Dict]:
        """
        Get valid resolution options for a given issue and vetting state.
        """
        valid = []
        
        for resolution in self.resolutions:
            # Match by issue code
            if resolution.get('issue_code') != issue_code:
                continue
            
            # If vetting status provided, apply additional filtering rules
            if vetting_status:
                if issue_code == 'SIM_SWAP':
                    if vetting_status == 'COMPLETE':
                        if resolution.get('resolution_code') in ['SWAP_VETTING_PASSED', 'SWAP_VETTING_FAILED']:
                            valid.append(resolution)
                    elif vetting_status == 'INCOMPLETE' or vetting_status == 'NO_DATA':
                        if resolution.get('resolution_code') in ['SWAP_VETTING_FAILED', 'SWAP_KYC_MISMATCH']:
                            valid.append(resolution)
                else:
                    # For other issues, return all valid resolutions
                    valid.append(resolution)
            else:
                # No vetting filter
                valid.append(resolution)
        
        return valid
    
    def get_resolution(self, resolution_code: str) -> Optional[Dict]:
        """Get specific resolution by code."""
        for resolution in self.resolutions:
            if resolution.get('resolution_code') == resolution_code:
                return resolution
        return None
    
    def resolve(self, issue_code: str, resolution_code: str, vetting_data: Dict = None) -> Dict:
        """
        Apply a resolution and generate output.
        Returns the resolution details with generated text.
        """
        resolution = self.get_resolution(resolution_code)
        
        if not resolution:
            return {'error': 'Resolution not found'}
        
        # Generate final output text
        template = resolution.get('template_text', '')
        
        # Simple template substitution
        output_text = template
        if vetting_data:
            for key, value in vetting_data.items():
                placeholder = f"{{{key}}}"
                output_text = output_text.replace(placeholder, str(value))
        
        return {
            'resolution_code': resolution.get('resolution_code'),
            'display_name': resolution.get('display_name'),
            'issue_code': resolution.get('issue_code'),
            'outcome': resolution.get('outcome'),
            'advice': resolution.get('advice'),
            'next_step': resolution.get('next_step'),
            'template_text': resolution.get('template_text'),
            'final_text': output_text
        }
    
    def get_all_by_issue(self, issue_code: str) -> List[Dict]:
        """Get all resolutions for an issue."""
        return [r for r in self.resolutions if r.get('issue_code') == issue_code]
