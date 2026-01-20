"""Output capture module for saving agent outputs to JSONL files.

This module provides the OutputCapture class that saves agent outputs
to JSONL files in the outputs/ directory with timestamp, agent type,
and prompt summary metadata.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class OutputCapture:
    """Captures agent outputs to JSONL files.

    This class provides non-blocking output capture functionality that
    saves agent outputs to JSONL files. All errors are swallowed to
    ensure capture failures don't affect agent operation.

    Attributes:
        output_dir: Directory where JSONL files are saved.

    Example:
        >>> capture = OutputCapture()
        >>> capture.capture(
        ...     agent_type="narrow",
        ...     prompt_summary="Analyze the code",
        ...     output={"result": "success", "findings": [...]}
        ... )
    """

    def __init__(self, output_dir: Path | None = None) -> None:
        """Initialize OutputCapture.

        Args:
            output_dir: Directory for output files. Defaults to 'outputs/'.
        """
        self.output_dir = output_dir if output_dir is not None else Path("outputs")

    def capture(
        self,
        agent_type: str,
        prompt_summary: str,
        output: Any
    ) -> None:
        """Capture agent output to JSONL file.

        Saves the output along with metadata (timestamp, agent type, prompt
        summary) to a JSONL file. This method is non-blocking and swallows
        all errors to ensure capture failures don't affect agent operation.

        Args:
            agent_type: Type of agent (narrow, walked, bookended).
            prompt_summary: Brief summary of the prompt.
            output: The agent output to capture (must be JSON-serializable).

        Returns:
            None. Always returns None, even on error.
        """
        try:
            # Create directory if needed
            self.output_dir.mkdir(parents=True, exist_ok=True)

            # Build the record
            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "agent_type": agent_type,
                "prompt_summary": prompt_summary,
                "output": output,
            }

            # Get the output file path (using date-based filename for organization)
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            output_file = self.output_dir / f"agent_outputs_{date_str}.jsonl"

            # Append to file
            with open(output_file, "a") as f:
                f.write(json.dumps(record) + "\n")

        except Exception:
            # Swallow all errors - capture is non-blocking
            pass

        return None
