"""Feedback processing: Convert specialist feedback to Trace work items."""

import re
import subprocess
from typing import List, Dict, Optional, Set, Any
from pathlib import Path


def _get_existing_work_item_titles(root_work_item_id: str, project_root: str) -> Set[str]:
    """
    Get titles of existing work items under the root.

    Args:
        root_work_item_id: Parent work item ID (spec root)
        project_root: Path to project root (for trc commands)

    Returns:
        Set of existing work item titles (normalized to lowercase for comparison)
    """
    existing_titles = set()

    try:
        # Get children of the root work item
        result = subprocess.run(
            ["trc", "children", root_work_item_id],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False
        )

        if result.returncode == 0 and result.stdout.strip():
            # Parse output - format is typically "id [status] title"
            for line in result.stdout.strip().split('\n'):
                line = line.strip()
                if not line:
                    continue
                # Extract title from output (after the [status] part)
                # Format: "ralph-id123 [open] Title goes here"
                match = re.search(r'\[(?:open|closed)\]\s+(.+)$', line)
                if match:
                    title = match.group(1).strip()
                    existing_titles.add(title.lower())
    except Exception:
        # If we can't get existing items, return empty set and allow creation
        pass

    return existing_titles


def _is_duplicate_feedback(title: str, existing_titles: Set[str]) -> bool:
    """
    Check if a feedback title is a duplicate of existing work items.

    Uses fuzzy matching: if the existing title contains the new title or vice versa.

    Args:
        title: New feedback title
        existing_titles: Set of existing work item titles (lowercase)

    Returns:
        True if duplicate detected, False otherwise
    """
    title_lower = title.lower()

    for existing in existing_titles:
        # Exact match
        if title_lower == existing:
            return True
        # Substring match (either direction)
        if title_lower in existing or existing in title_lower:
            return True

    return False


def parse_feedback_item(feedback: str) -> Dict[str, Any]:
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

    Checks for duplicates before creating work items to avoid redundant entries.

    Args:
        feedback_items: List of feedback item strings
        specialist_name: Name of the specialist that generated feedback
        root_work_item_id: Parent work item ID (spec root)
        project_root: Path to project root (for trc commands)

    Returns:
        List of created work item IDs
    """
    created_ids = []

    # Get existing work items to check for duplicates
    existing_titles = _get_existing_work_item_titles(root_work_item_id, project_root)

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

        # Check for duplicates before creating
        if _is_duplicate_feedback(title, existing_titles):
            print(f"   Skipping duplicate feedback: '{title}'")
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

                # Add to existing titles to prevent duplicates within the same batch
                existing_titles.add(title.lower())

        except subprocess.CalledProcessError as e:
            # Log error but continue processing other items
            print(f"Warning: Failed to create work item for '{title}': {e.stderr}")
            continue
        except Exception as e:
            # Handle any other errors
            print(f"Warning: Failed to create work item for '{title}': {e}")
            continue

    return created_ids
