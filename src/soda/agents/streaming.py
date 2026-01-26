"""Streaming output for SODA agents.

This module provides real-time console output during agent execution,
showing tool calls and progress to keep users informed.

Console UX Design:
==================

Information Architecture (what users see at each phase):
- Phase headers: 📡 SENSE, 🧭 ORIENT, 🎯 DECIDE, ⚙️ ACT
- Tool calls: Indented with arrow, shows tool name and key args
- Tool results: Checkmark on success, X on failure
- Progress: Claim counts, task counts, decision outcomes

Visual Hierarchy:
- Bold: Phase headers
- Dim: Less important details
- Yellow: Tool calls (action being taken)
- Green: Success/completion
- Red: Errors/failures

Verbosity Levels:
- quiet: Only results (no streaming)
- normal: Phase headers + summary (default)
- verbose: Phase headers + tool calls + results
"""

from typing import Any, Callable, Optional

from rich.console import Console

# Shared console for consistent output
console = Console()


def stream_tool_call(
    tool_name: str,
    tool_input: dict[str, Any],
    indent: str = "   ",
) -> None:
    """Print a tool call to the console.

    Args:
        tool_name: Name of the tool being called (e.g., "Read", "Bash")
        tool_input: Input dict with tool parameters
        indent: Indentation prefix (default: 3 spaces)
    """
    # Build tool info string with key parameter preview
    tool_info = f"▶ {tool_name}"

    if tool_name == "Bash" and "command" in tool_input:
        # Show first 60 chars of command
        cmd = tool_input["command"]
        cmd_preview = cmd[:60] + "..." if len(cmd) > 60 else cmd
        tool_info += f": [dim]{cmd_preview}[/dim]"
    elif "file_path" in tool_input:
        # Show file path for Read, Write, Edit
        tool_info += f": [dim]{tool_input['file_path']}[/dim]"
    elif "pattern" in tool_input:
        # Show pattern for Glob, Grep
        tool_info += f": [dim]{tool_input['pattern']}[/dim]"

    console.print(f"{indent}[yellow]{tool_info}[/yellow]")


def stream_tool_result(
    success: bool = True,
    error_message: Optional[str] = None,
    indent: str = "   ",
) -> None:
    """Print a tool result to the console.

    Args:
        success: Whether the tool call succeeded
        error_message: Optional error message if failed
        indent: Indentation prefix (default: 3 spaces)
    """
    if success:
        console.print(f"{indent}  [green]✓[/green]")
    else:
        msg = f"✗ {error_message}" if error_message else "✗"
        console.print(f"{indent}  [red]{msg}[/red]")


def stream_agent_text(
    text: str,
    indent: str = "   ",
) -> None:
    """Print agent text output to the console.

    Shows agent reasoning/thinking in real-time.

    Args:
        text: Text content from the agent
        indent: Indentation prefix (default: 3 spaces)
    """
    # Cyan for agent text (matches tool output style)
    console.print(f"{indent}[cyan]{text}[/cyan]")


class StreamingCallback:
    """Callback class for streaming agent output.

    This class captures tool calls and results during agent execution
    and prints them to the console in real-time.

    Usage:
        callback = StreamingCallback(verbose=True)
        # Pass to NarrowAgent for streaming during execution
    """

    def __init__(self, verbose: bool = False):
        """Initialize the streaming callback.

        Args:
            verbose: If True, also stream agent text output
        """
        self.verbose = verbose
        self._tool_call_count = 0

    def on_tool_call(self, tool_name: str, tool_input: dict[str, Any]) -> None:
        """Called when a tool is invoked.

        Args:
            tool_name: Name of the tool
            tool_input: Input parameters for the tool
        """
        stream_tool_call(tool_name, tool_input)
        self._tool_call_count += 1

    def on_tool_result(
        self,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> None:
        """Called when a tool returns a result.

        Args:
            success: Whether the tool call succeeded
            error_message: Optional error message if failed
        """
        stream_tool_result(success, error_message)

    def on_text(self, text: str) -> None:
        """Called when the agent produces text output.

        Only printed in verbose mode.

        Args:
            text: Text content from the agent
        """
        if self.verbose:
            stream_agent_text(text)

    @property
    def tool_call_count(self) -> int:
        """Return the number of tool calls made."""
        return self._tool_call_count
