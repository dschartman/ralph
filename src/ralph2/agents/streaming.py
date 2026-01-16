"""Shared streaming utility for agent output processing.

This module provides a common function for streaming agent messages to the terminal,
ensuring consistent behavior across all Ralph2 agents (planner, executor, verifier, specialist).
"""

from typing import List, Any

from claude_agent_sdk.types import AssistantMessage, TextBlock, ToolUseBlock, ToolResultBlock


def stream_agent_output(message: Any, output_list: List[str]) -> List[str]:
    """Process an agent message and stream it to the terminal.

    This function handles different message types from the Claude Agent SDK:
    - AssistantMessage with TextBlock: Prints text in cyan, appends to output_list
    - AssistantMessage with ToolUseBlock: Prints tool info in yellow
    - ToolResultBlock: Prints a green checkmark

    Args:
        message: A message from the Claude Agent SDK (AssistantMessage, ToolResultBlock, etc.)
        output_list: List to append text content to for full output collection

    Returns:
        The updated output_list with any new text content appended
    """
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                print(f"\033[36m{block.text}\033[0m")  # Cyan for text
                output_list.append(block.text)
            elif isinstance(block, ToolUseBlock):
                tool_info = f"▶ {block.name}"
                if hasattr(block, 'input') and block.input:
                    if 'command' in block.input:
                        tool_info += f": {block.input['command'][:80]}"
                    elif 'file_path' in block.input:
                        tool_info += f": {block.input['file_path']}"
                print(f"\033[33m{tool_info}\033[0m")  # Yellow for tools
    elif isinstance(message, ToolResultBlock):
        print(f"\033[32m  ✓\033[0m")  # Green checkmark for results

    return output_list
