"""Milestone completion logic for Ralph2.

When a spec milestone is complete (Planner declares DONE), this module handles:
1. Reading all open children under the root work item
2. Categorizing remaining work into logical groups (max 5 categories)
3. Creating new parent work items for each category
4. Reparenting open children using 'trc reparent'
5. Closing the original root work item
"""

import subprocess
import re
from typing import List, Dict, Optional


def _get_open_children(work_item_id: str, project_root: str) -> List[Dict[str, str]]:
    """
    Get all open child work items under a parent.

    Args:
        work_item_id: Parent work item ID
        project_root: Project root directory

    Returns:
        List of dicts with 'id', 'title', 'description' keys
    """
    # Use trc tree to get all children
    result = subprocess.run(
        ["trc", "tree", work_item_id],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False
    )

    if result.returncode != 0:
        return []

    # Parse tree output to find open children
    # Format: "   ├─ ○ work-item-id - Title [open]"
    # or:     "   └─ ○ work-item-id - Title [open]"
    open_children = []
    lines = result.stdout.split('\n')

    for line in lines:
        if '[open]' in line:
            # Extract work item ID - pattern: "○ id - title [open]"
            # Match the tree branch characters and extract the ID
            match = re.search(r'[├└]─\s+○\s+([a-z0-9\-]+)\s+-', line)
            if match:
                child_id = match.group(1)
                # Skip the root itself
                if child_id != work_item_id:
                    # Get title - everything between "-" and "[open]"
                    title_match = re.search(r'-\s+(.+?)\s+\[open\]', line)
                    title = title_match.group(1).strip() if title_match else ""

                    # Get full details including description
                    details_result = subprocess.run(
                        ["trc", "show", child_id],
                        cwd=project_root,
                        capture_output=True,
                        text=True,
                        check=False
                    )

                    description = ""
                    if details_result.returncode == 0:
                        # Extract description from output
                        desc_match = re.search(r'Description:\s*\n(.+?)(?=\n\n|\nDependencies:|\nComments:|\Z)',
                                             details_result.stdout, re.DOTALL)
                        if desc_match:
                            description = desc_match.group(1).strip()

                    open_children.append({
                        'id': child_id,
                        'title': title,
                        'description': description
                    })

    return open_children


def _categorize_work_items(work_items: List[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
    """
    Categorize work items into logical groups.

    Uses simple keyword matching on titles and descriptions.
    Maximum of 5 categories to prevent over-fragmentation.

    Args:
        work_items: List of work item dicts with 'id', 'title', 'description'

    Returns:
        Dict mapping category name to list of work items in that category
    """
    if not work_items:
        return {}

    categories: Dict[str, List[Dict[str, str]]] = {
        "Features": [],
        "Bug Fixes": [],
        "Refactoring": [],
        "Documentation": [],
        "Backlog": []  # Catch-all for uncategorizable items
    }

    # Keywords for each category
    feature_keywords = ['feature', 'add', 'implement', 'create', 'build']
    bug_keywords = ['bug', 'fix', 'issue', 'broken', 'error', 'crash']
    refactor_keywords = ['refactor', 'cleanup', 'extract', 'simplify', 'reorganize']
    docs_keywords = ['doc', 'documentation', 'guide', 'readme', 'comment']

    for item in work_items:
        text = (item['title'] + ' ' + item['description']).lower()

        # Try to categorize based on keywords
        if any(kw in text for kw in feature_keywords):
            categories["Features"].append(item)
        elif any(kw in text for kw in bug_keywords):
            categories["Bug Fixes"].append(item)
        elif any(kw in text for kw in refactor_keywords):
            categories["Refactoring"].append(item)
        elif any(kw in text for kw in docs_keywords):
            categories["Documentation"].append(item)
        else:
            # Uncategorizable - goes to backlog
            categories["Backlog"].append(item)

    # Remove empty categories
    categories = {k: v for k, v in categories.items() if v}

    return categories


def _create_category_parent(category_name: str, project_root: str) -> str:
    """
    Create a new parent work item for a category.

    Args:
        category_name: Name of the category
        project_root: Project root directory

    Returns:
        Work item ID of the created parent
    """
    description = f"Remaining {category_name.lower()} work from completed milestone"

    result = subprocess.run(
        ["trc", "create", category_name, "--description", description],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=True
    )

    # Extract work item ID from output
    output = result.stdout.strip()
    last_line = output.split('\n')[-1].strip()

    if last_line.startswith("Created "):
        # Extract the ID between "Created " and ":"
        work_item_id = last_line.split()[1].rstrip(":")
    else:
        # Fallback: try to extract ID-like pattern from last line
        match = re.search(r'([a-z0-9]+-[a-z0-9]+)', last_line)
        if match:
            work_item_id = match.group(1)
        else:
            raise RuntimeError(f"Could not extract work item ID from output: {last_line}")

    return work_item_id


def _reparent_work_item(work_item_id: str, new_parent_id: str, project_root: str):
    """
    Reparent a work item to a new parent.

    Args:
        work_item_id: Work item to reparent
        new_parent_id: New parent work item ID
        project_root: Project root directory
    """
    subprocess.run(
        ["trc", "reparent", work_item_id, new_parent_id],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=True
    )


def _close_work_item(work_item_id: str, project_root: str):
    """
    Close a work item.

    Args:
        work_item_id: Work item to close
        project_root: Project root directory
    """
    subprocess.run(
        ["trc", "close", work_item_id],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=True
    )


def complete_milestone(root_work_item_id: str, project_root: str) -> List[str]:
    """
    Complete a milestone by categorizing and reparenting remaining work.

    When a spec milestone is complete (Planner declares DONE), this function:
    1. Reads all open children under the root work item
    2. Categorizes remaining work into logical groups (max 5 categories)
    3. Creates new parent work items for each category
    4. Reparents open children using 'trc reparent'
    5. Closes the original root work item

    Args:
        root_work_item_id: Root work item ID (spec milestone)
        project_root: Project root directory

    Returns:
        List of new parent work item IDs created

    Raises:
        subprocess.CalledProcessError: If any trace command fails
        RuntimeError: If unable to parse trace command output
    """
    # Get all open children
    open_children = _get_open_children(root_work_item_id, project_root)

    # If no open children, just close the root and return
    if not open_children:
        _close_work_item(root_work_item_id, project_root)
        return []

    # Categorize work items
    categories = _categorize_work_items(open_children)

    # Create parent work items for each category and reparent children
    new_parent_ids = []

    for category_name, items in categories.items():
        # Create category parent
        parent_id = _create_category_parent(category_name, project_root)
        new_parent_ids.append(parent_id)

        # Reparent all items in this category
        for item in items:
            _reparent_work_item(item['id'], parent_id, project_root)

    # Close the root work item
    _close_work_item(root_work_item_id, project_root)

    return new_parent_ids
