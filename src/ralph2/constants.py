"""Shared constants for Ralph2 agent output parsing.

This module centralizes magic strings used for parsing agent outputs to prevent
parsing failures from typos and ensure consistency across the codebase.
"""

# Agent output markers
EXECUTOR_SUMMARY_MARKER = "EXECUTOR_SUMMARY:"
VERIFIER_ASSESSMENT_MARKER = "VERIFIER_ASSESSMENT:"
DECISION_MARKER = "DECISION:"

# Regex pattern for parsing planner decisions
# Matches: DECISION: [CONTINUE | DONE | STUCK]
# Case-insensitive, allows optional whitespace after colon
DECISION_PATTERN = r'DECISION:\s*(CONTINUE|DONE|STUCK)'
