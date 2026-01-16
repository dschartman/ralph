"""Feedback processing: Convert specialist feedback to Trace work items."""

import re
import subprocess
from typing import List, Dict, Optional
from pathlib import Path


def parse_feedback_item(feedback: str) -> Dict[str, any]:
    """
    Parse a feedback item to extract priority and title.

    Priority markers: [P0], [P1], [P2], [P3], [P4]
    - P0 (Critical): Security vulnerabilities, critical bugs, data loss risks
    - P1 (High): Maintainability blockers, significant technical debt
    - P2 (Medium): Code quality improvements, test coverage gaps (default)
    - P3 (Low): Style issues, minor refactorings, documentation gaps
    - P4 (Backlog): Nice-to-have improvements

    Args:
        feedback: Feedback item string (e.g., "[P1] Add error handling")

    Returns:
        dict with keys:
            - title (str): Feedback title without priority marker
            - priority (int): Priority level 0-4 (defaults to 2 if not specified)
    """
    # Default priority is Medium (2)
    priority = 2
    title = feedback.strip()

    # Extract priority marker if present
    priority_match = re.match(r'\[P([0-4])\]\s*(.*)', title)
    if priority_match:
        priority = int(priority_match.group(1))
        title = priority_match.group(2).strip()

    return {
        "title": title,
        "priority": priority
    }


def create_work_items_from_feedback(
    feedback_items: List[str],
    specialist_name: str,
    root_work_item_id: str,
    project_root: str
) -> List[str]:
    """
    Create Trace work items from specialist feedback.

    Args:
        feedback_items: List of feedback item strings
        specialist_name: Name of the specialist that generated feedback
        root_work_item_id: Parent work item ID (spec root)
        project_root: Path to project root (for trc commands)

    Returns:
        List of created work item IDs
    """
    created_ids = []

    for feedback in feedback_items:
        # Skip empty or whitespace-only items
        if not feedback or not feedback.strip():
            continue

        # Parse feedback item
        parsed = parse_feedback_item(feedback)
        title = parsed["title"]
        priority = parsed["priority"]

        # Skip if title is empty after parsing
        if not title:
            continue

        # Create description that includes source specialist
        description = f"Feedback from {specialist_name}:\n\n{title}"

        try:
            # Create work item using trc
            result = subprocess.run(
                [
                    "trc", "create",
                    title,
                    "--description", description,
                    "--priority", str(priority),
                    "--parent", root_work_item_id
                ],
                cwd=project_root,
                check=True,
                capture_output=True,
                text=True
            )

            # Extract work item ID from output (format: "Created <id>: <title>")
            output = result.stdout.strip()
            # Split by colon and get the first part after "Created "
            if output.startswith("Created "):
                parts = output[8:].split(":", 1)  # Remove "Created " and split
                work_item_id = parts[0].strip()
                created_ids.append(work_item_id)

        except subprocess.CalledProcessError as e:
            # Log error but continue processing other items
            print(f"Warning: Failed to create work item for '{title}': {e.stderr}")
            continue
        except Exception as e:
            # Handle any other errors
            print(f"Warning: Failed to create work item for '{title}': {e}")
            continue

    return created_ids
