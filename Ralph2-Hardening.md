# Ralph2 Hardening: Robustness and Milestone Management

## Context

Ralph2 core functionality is complete and passing all tests. This spec addresses two needs: (1) hardening the implementation for production reliability, and (2) adding milestone completion semantics so the Planner can properly close out specs and organize remaining work.

---

## User Experience

### CLI Commands (unchanged)

Existing commands work as before. The new behavior is internal to the Planner's termination logic.

### New Planner Behavior on DONE

When the Planner declares DONE:
1. Planner reads all open children under the root work item
2. Planner categorizes remaining work into logical groups
3. Planner creates new parent work items for each category
4. Planner reparents open children to appropriate new parents using `trc reparent`
5. Planner closes the original root work item
6. Run terminates with status `completed`

---

## Acceptance Criteria

### Milestone Completion

- [ ] WHEN Planner declares DONE, THEN all open children of the root work item are reparented to new category parents
- [ ] WHEN Planner declares DONE, THEN the original root work item is closed via `trc close`
- [ ] WHEN categorizing remaining work, THEN Planner creates at most 5 category parents (prevents over-fragmentation)
- [ ] WHEN a child work item cannot be categorized, THEN it is reparented to a "Backlog" category
- [ ] WHEN no open children remain, THEN root work item is closed without creating category parents

### Error Handling Hardening

- [ ] WHEN `trc show` fails for non-"not found" reasons, THEN error is logged and handled explicitly (not silently continued)
- [ ] WHEN planner/executor output parsing fails to extract required fields, THEN fallback values are used with warning logged
- [ ] WHEN git worktree creation partially succeeds (branch exists, worktree fails), THEN cleanup is guaranteed
- [ ] WHEN database close() is called on already-closed connection, THEN no exception is raised
- [ ] WHEN multiple Ralph2 instances run in parallel, THEN worktree paths include run_id to prevent conflicts

### Code Quality

- [ ] Magic strings ("EXECUTOR_SUMMARY:", "VERIFIER_ASSESSMENT:", "DECISION:") extracted to shared constants module
- [ ] Agent output streaming logic extracted to shared utility in `agents/__init__.py`
- [ ] Git operations extracted to `GitBranchManager` class with guaranteed cleanup
- [ ] `Ralph2Runner.run()` broken into smaller methods (each < 50 lines)
- [ ] Database operations use transaction boundaries for multi-step operations

### Validation

- [ ] `parse_feedback_item()` validates priority is 0-4, defaults to P2 for invalid values
- [ ] `root_work_item_id` format validated before subprocess calls
- [ ] Feedback work item creation checks for duplicates before creating

### Test Coverage

- [ ] Unit tests exist for: feedback.py, trace.py, project.py, state/models.py
- [ ] Worktree/merge/conflict resolution logic has test coverage for all branches

---

## Technical Constraints

- Must use existing Trace primitives (`trc reparent`, `trc close`, `trc create`)
- Must not change CLI interface
- Must maintain backward compatibility with existing runs/databases
- Milestone completion logic lives in Planner, not in runner

---

## Assets

- Existing implementation: `src/ralph2/`
- Open work items: `trc tree ralph-1700o9` (items marked `[open]`)
- Trace CLI reference: `trc --help`, `trc reparent --help`
