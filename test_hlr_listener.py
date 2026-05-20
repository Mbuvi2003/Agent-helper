"""
test_hlr_listener.py
====================
Standalone unit tests for the HLR Smart Listener.
Tests pure logic only — no Tkinter, no keyboard library, no hardware.

Run:
    python test_hlr_listener.py
"""

import re
import unittest


# ─── Pure-logic helpers extracted from ui.py ─────────────────────────────────

def extract_digits(text: str) -> str:
    """Strip non-digit characters from *text* (mirrors _poll_clipboard logic)."""
    return re.sub(r'\D', '', text)


def get_hlr_suffix(phone_number: str) -> str:
    """Return last 6 digits of *phone_number* (mirrors _arm_hlr_paste_hook)."""
    digits = re.sub(r'\D', '', phone_number)
    return digits[-6:]


def is_valid_phone(text: str) -> bool:
    """Return True if *text* contains exactly 9 stripped digits (poll_clipboard gate)."""
    return len(extract_digits(text)) == 9


def hlr_arm_allowed(paste_hook_active: bool, reversal_armed: bool) -> bool:
    """
    Return True only when neither higher-priority hook is active.
    Mirrors the two conflict guards in _arm_hlr_paste_hook.
    """
    if paste_hook_active:   # Hakikisha SMS queue wins
        return False
    if reversal_armed:      # Reversal SLA listener wins
        return False
    return True


# ─── Tests ───────────────────────────────────────────────────────────────────

TEST_NUMBER = "757782330"
EXPECTED_SUFFIX = "782330"


class TestHLRSuffixExtraction(unittest.TestCase):
    """Verify correct suffix extraction for the reference number."""

    def test_exact_suffix(self):
        suffix = get_hlr_suffix(TEST_NUMBER)
        self.assertEqual(suffix, EXPECTED_SUFFIX,
                         f"Expected '{EXPECTED_SUFFIX}', got '{suffix}'")

    def test_suffix_length(self):
        suffix = get_hlr_suffix(TEST_NUMBER)
        self.assertEqual(len(suffix), 6)

    def test_suffix_is_digits_only(self):
        suffix = get_hlr_suffix(TEST_NUMBER)
        self.assertTrue(suffix.isdigit(), "Suffix must contain only digits")

    def test_number_with_spaces(self):
        """Numbers copied with spaces (e.g. '757 782 330') must still work."""
        suffix = get_hlr_suffix("757 782 330")
        self.assertEqual(suffix, EXPECTED_SUFFIX)

    def test_number_with_plus_prefix(self):
        """Some CRMs prefix with +254 or country codes."""
        suffix = get_hlr_suffix("+254757782330")
        self.assertEqual(suffix, EXPECTED_SUFFIX)

    def test_number_with_zero_prefix(self):
        """Local format 0757782330 (10 digits) — last 6 must still be correct."""
        suffix = get_hlr_suffix("0757782330")
        self.assertEqual(suffix, EXPECTED_SUFFIX)

    def test_short_number_not_usable(self):
        """A 5-digit string has no valid 6-digit suffix."""
        digits = extract_digits("12345")
        self.assertLess(len(digits), 6)


class TestPhoneDetection(unittest.TestCase):
    """Verify the 9-digit detection gate used in _poll_clipboard."""

    def test_nine_digit_match(self):
        self.assertTrue(is_valid_phone(TEST_NUMBER))

    def test_nine_digit_with_spaces(self):
        self.assertTrue(is_valid_phone("757 782 330"))

    def test_ten_digit_fails_gate(self):
        """10-digit numbers (with leading 0) must NOT trigger the ring buffer."""
        self.assertFalse(is_valid_phone("0757782330"))

    def test_eight_digit_fails(self):
        self.assertFalse(is_valid_phone("75778233"))

    def test_alpha_fails(self):
        self.assertFalse(is_valid_phone("ABC123"))

    def test_txn_id_not_confused(self):
        """M-PESA txn IDs like SIO3LK7Q4D must not trigger phone detection."""
        self.assertFalse(is_valid_phone("SIO3LK7Q4D"))


class TestConflictPrevention(unittest.TestCase):
    """Verify HLR hook yields to higher-priority hooks."""

    def test_arms_when_idle(self):
        """Should arm when no other hook is active."""
        self.assertTrue(hlr_arm_allowed(
            paste_hook_active=False,
            reversal_armed=False,
        ))

    def test_blocked_by_hakikisha(self):
        """Hakikisha SMS queue (paste_hook) must block HLR."""
        self.assertFalse(hlr_arm_allowed(
            paste_hook_active=True,
            reversal_armed=False,
        ))

    def test_blocked_by_reversal(self):
        """Active Reversal SLA listener must block HLR."""
        self.assertFalse(hlr_arm_allowed(
            paste_hook_active=False,
            reversal_armed=True,
        ))

    def test_blocked_by_both(self):
        """Both active — HLR must still be blocked."""
        self.assertFalse(hlr_arm_allowed(
            paste_hook_active=True,
            reversal_armed=True,
        ))

    def test_after_reversal_clears_hlr_can_arm(self):
        """Once reversal disarms, HLR should be allowed."""
        was_blocked = not hlr_arm_allowed(paste_hook_active=False, reversal_armed=True)
        self.assertTrue(was_blocked)
        now_allowed = hlr_arm_allowed(paste_hook_active=False, reversal_armed=False)
        self.assertTrue(now_allowed)


class TestManualOverride(unittest.TestCase):
    """Verify _copy_hlr_suffix manual double-click logic."""

    def test_manual_suffix_from_full_number(self):
        suffix = get_hlr_suffix(TEST_NUMBER)
        self.assertEqual(suffix, EXPECTED_SUFFIX)

    def test_manual_suffix_em_dash_placeholder(self):
        """Em-dash '—' is the default when no number captured yet."""
        digits = extract_digits("—")
        self.assertLess(len(digits), 6,
                        "Em-dash placeholder must not produce a valid suffix")

    def test_manual_suffix_empty(self):
        digits = extract_digits("")
        self.assertLess(len(digits), 6)


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 60)
    if result.wasSuccessful():
        print(f"[PASS] ALL {result.testsRun} TESTS PASSED")
        print(f"    Test number : {TEST_NUMBER}")
        print(f"    HLR suffix  : {get_hlr_suffix(TEST_NUMBER)}")
    else:
        print(f"[FAIL] {len(result.failures)} FAILURE(S), {len(result.errors)} ERROR(S)")
    print("=" * 60)
