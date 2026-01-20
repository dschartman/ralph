# Soda Milestone 4: ORIENT

## Context

ORIENT is where all judgment lives. It verifies claims against the codebase, assesses spec satisfaction, updates the task breakdown, and plans the iteration. This is agent work — reasoning that cannot be done deterministically.

## Acceptance Criteria

### Verify Claims

- [ ] WHEN claims say a task is closed, THEN ORIENT verifies the code actually implements it
- [ ] WHEN a task is marked closed but code doesn't implement it, THEN ORIENT flags discrepancy and reopens task
- [ ] WHEN claims say a task is blocked, THEN ORIENT verifies blocker still exists
- [ ] WHEN blocker no longer exists, THEN task is unblocked and becomes eligible for current iteration
- [ ] WHEN learnings conflict with observed reality, THEN learning is flagged for deprecation

### Assess Spec Satisfaction

- [ ] WHEN assessing spec, THEN each acceptance criterion is evaluated individually
- [ ] WHEN all acceptance criteria are satisfied, THEN `spec_satisfied` is `true`
- [ ] WHEN any acceptance criterion is not satisfied, THEN `spec_satisfied` is `false`
- [ ] WHEN acceptance criteria cannot be verified (requires external resources), THEN `spec_satisfied` is `"unverifiable"`
- [ ] WHEN assessing criteria, THEN tests are run as one verification method
- [ ] WHEN assessing criteria, THEN code is read for implementation proof
- [ ] WHEN tests pass but implementation is missing, THEN criterion is not satisfied

### Update Task Breakdown

- [ ] WHEN a task is verified complete, THEN it is closed in Trace with verification comment
- [ ] WHEN a gap is identified, THEN a new task is created in Trace
- [ ] WHEN a task's blocker is resolved, THEN task is updated to unblocked
- [ ] WHEN task priority needs adjustment, THEN task is updated with new priority
- [ ] WHEN subtasks are needed, THEN they are created under parent task

### Plan Iteration

- [ ] WHEN spec is not satisfied, THEN iteration plan includes tasks to work on
- [ ] WHEN planning iteration, THEN tasks are selected based on priority (P0 > P1 > P2)
- [ ] WHEN planning iteration, THEN blocked tasks are excluded
- [ ] WHEN planning iteration, THEN iteration intent is defined (summary of what this iteration will accomplish)
- [ ] WHEN planning iteration, THEN approach is outlined (how tasks will be tackled)

### Pattern Recognition

- [ ] WHEN same criterion has failed 2+ iterations, THEN an investigation task is created instead of retry
- [ ] WHEN same test has failed 2+ iterations, THEN an investigation task is created
- [ ] WHEN iteration history shows repeated intent with no progress, THEN ORIENT flags potential loop
- [ ] WHEN loop is detected, THEN `actionable_work_exists` considers investigation as the action

### Output Structure

- [ ] WHEN ORIENT completes, THEN output includes `spec_satisfied` (true | false | "unverifiable")
- [ ] WHEN ORIENT completes, THEN output includes `actionable_work_exists` (boolean)
- [ ] WHEN ORIENT completes, THEN output includes `task_updates` (list of Trace operations)
- [ ] WHEN ORIENT completes, THEN output includes `gaps` (list of identified gaps with severity)
- [ ] WHEN ORIENT completes, THEN output includes `iteration_plan` (intent, tasks, approach)
- [ ] WHEN ORIENT completes, THEN output includes `learnings` (efficiency knowledge to preserve or deprecate)

## Technical Constraints

- ORIENT uses agent reasoning (not deterministic orchestrator code)
- ORIENT agent has read-only codebase access (Read, Glob, Grep, Bash for running tests)
- ORIENT agent can update Trace (create, close, comment on tasks)
- ORIENT must produce structured output matching the schema
- ORIENT should complete within reasonable token budget (avoid exhaustive file reading)

## Data Structures

### ORIENT Output Schema

```python
@dataclass
class OrientOutput:
    spec_satisfied: Literal[True, False, "unverifiable"]
    actionable_work_exists: bool
    confidence: Literal["high", "medium", "low"]

    task_updates: list[TaskUpdate]  # close, update, block operations
    new_tasks: list[NewTask]        # gaps to create
    gaps: list[Gap]                 # identified gaps with severity

    iteration_plan: IterationPlan   # intent, tasks, approach
    learnings: list[str]            # efficiency knowledge
```

## Agent Pattern

ORIENT may use walked or bookended pattern depending on complexity:

- **Simple case**: Narrow agent with full ORIENT prompt
- **Complex case**: Walked through verify → assess → plan steps
- **Bookended**: Setup (load context) → work (reason) → wrap-up (validate output completeness)

The orchestrator decides which pattern based on claims complexity.

## Assets

- SODA Loop documentation: `docs/soda-loop.md`
- Ralph2 planner for reference: `src/ralph2/agents/planner.py`
- Ralph2 verifier for reference: `src/ralph2/agents/verifier.py`

## Definition of Done

- [ ] All acceptance criteria have passing tests
- [ ] ORIENT produces valid structured output
- [ ] Claim verification works (detects discrepancies between Trace and code)
- [ ] Spec assessment evaluates each criterion
- [ ] Task breakdown updates are applied to Trace
- [ ] Iteration planning selects appropriate tasks
- [ ] Pattern recognition detects repeated failures
