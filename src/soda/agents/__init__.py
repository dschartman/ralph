"""Soda agents module.

This module provides agent invocation patterns:
- narrow_agent: Single-shot, focused prompts with structured output
- walked_agent: Multi-turn conversations with context persistence
- bookended_agent: Setup + main work + wrap-up patterns
"""

from soda.agents.narrow import NarrowAgent
from soda.agents.walked import WalkedAgent

__all__: list[str] = ["NarrowAgent", "WalkedAgent"]
