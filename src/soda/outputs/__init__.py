"""Soda outputs module.

This module provides output capture functionality:
- JSONL file logging for agent conversations
- Timestamp and metadata capture
- Non-blocking output operations
"""

from soda.outputs.capture import OutputCapture

__all__: list[str] = ["OutputCapture"]
