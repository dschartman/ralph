"""Tests for ralph2 constants module."""

import pytest


def test_output_markers_exist():
    """Test that all required output marker constants exist."""
    from ralph2.constants import (
        EXECUTOR_SUMMARY_MARKER,
        VERIFIER_ASSESSMENT_MARKER,
        DECISION_MARKER,
    )

    assert EXECUTOR_SUMMARY_MARKER == "EXECUTOR_SUMMARY:"
    assert VERIFIER_ASSESSMENT_MARKER == "VERIFIER_ASSESSMENT:"
    assert DECISION_MARKER == "DECISION:"


def test_output_markers_are_strings():
    """Test that all output marker constants are strings."""
    from ralph2.constants import (
        EXECUTOR_SUMMARY_MARKER,
        VERIFIER_ASSESSMENT_MARKER,
        DECISION_MARKER,
    )

    assert isinstance(EXECUTOR_SUMMARY_MARKER, str)
    assert isinstance(VERIFIER_ASSESSMENT_MARKER, str)
    assert isinstance(DECISION_MARKER, str)


def test_output_markers_have_correct_format():
    """Test that output markers have correct format (end with colon)."""
    from ralph2.constants import (
        EXECUTOR_SUMMARY_MARKER,
        VERIFIER_ASSESSMENT_MARKER,
        DECISION_MARKER,
    )

    assert EXECUTOR_SUMMARY_MARKER.endswith(":")
    assert VERIFIER_ASSESSMENT_MARKER.endswith(":")
    assert DECISION_MARKER.endswith(":")


def test_decision_pattern_exists():
    """Test that decision pattern constant exists for regex matching."""
    from ralph2.constants import DECISION_PATTERN

    assert DECISION_PATTERN is not None
    assert isinstance(DECISION_PATTERN, str)


def test_decision_pattern_matches_valid_decisions():
    """Test that decision pattern correctly matches valid decision formats."""
    import re
    from ralph2.constants import DECISION_PATTERN

    valid_cases = [
        "DECISION: CONTINUE",
        "DECISION: DONE",
        "DECISION: STUCK",
        "DECISION:CONTINUE",  # No space
        "decision: continue",  # Lowercase
        "Decision: Done",  # Mixed case
    ]

    for case in valid_cases:
        match = re.search(DECISION_PATTERN, case, re.IGNORECASE)
        assert match is not None, f"Pattern should match: {case}"
        assert match.group(1).upper() in ["CONTINUE", "DONE", "STUCK"]


def test_decision_pattern_does_not_match_invalid():
    """Test that decision pattern rejects invalid decision formats."""
    import re
    from ralph2.constants import DECISION_PATTERN

    invalid_cases = [
        "DECISION: INVALID",  # Invalid decision value
        "DECISION CONTINUE",  # Missing colon
        "CONTINUE",  # Missing DECISION: prefix
    ]

    for case in invalid_cases:
        match = re.search(DECISION_PATTERN, case, re.IGNORECASE)
        assert match is None, f"Pattern should not match: {case}"
