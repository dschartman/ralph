"""Soda: Agent infrastructure for Claude Agent SDK.

Soda provides patterns for invoking Claude agents:
- Narrow agents: Single-shot, focused prompts with structured output
- Walked agents: Multi-turn conversations with context persistence
- Bookended agents: Setup + main work + wrap-up patterns
"""

__version__ = "0.1.0"


def hello() -> str:
    """Hello from soda - useful for testing imports."""
    return "Hello from soda!"
