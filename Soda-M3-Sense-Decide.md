# Soda Milestone 3: SENSE + DECIDE

## Context

SENSE and DECIDE are the deterministic orchestrator phases of the SODA loop. SENSE gathers claims from systems without judgment. DECIDE routes based on ORIENT's structured output. Neither requires agent reasoning.

## Acceptance Criteria

### SENSE: Code State

- [ ] WHEN sensing code state, THEN current branch name is included in claims
- [ ] WHEN sensing code state, THEN uncommitted changes (staged/unstaged count) are included
- [ ] WHEN sensing code state, THEN commits since milestone base are listed (hash, message, timestamp)
- [ ] WHEN sensing code state, THEN files changed since milestone base are listed
- [ ] WHEN sensing code state, THEN diff summary (lines added/removed) is included
- [ ] WHEN milestone base is empty (new project), THEN code state reports "no base commit"

### SENSE: Work State

- [ ] WHEN sensing work state, THEN open tasks under milestone root are listed with ID, title, status
- [ ] WHEN sensing work state, THEN blocked tasks are flagged with blocker reason
- [ ] WHEN sensing work state, THEN closed tasks are listed separately
- [ ] WHEN sensing work state, THEN recent comments (last 10) on milestone tasks are included
- [ ] WHEN no milestone root exists, THEN work state reports "no root work item"

### SENSE: Project State

- [ ] WHEN sensing project state, THEN current iteration number is included
- [ ] WHEN sensing project state, THEN recent iteration history (last 5) is included with intent and outcome
- [ ] WHEN sensing project state, THEN last agent summaries (executor, verifier) are included
- [ ] WHEN no prior iterations exist, THEN project state reports "first iteration"

### SENSE: Human Input

- [ ] WHEN human input is pending, THEN it is included in claims with type and content
- [ ] WHEN no human input is pending, THEN human input section is empty
- [ ] WHEN human input includes spec modification, THEN it is flagged as spec_modified

### SENSE: Learnings

- [ ] WHEN sensing learnings, THEN memory.md content is included in claims
- [ ] WHEN memory.md doesn't exist, THEN learnings section is empty

### SENSE: Output Structure

- [ ] WHEN SENSE completes, THEN output is a structured Claims object with all sections
- [ ] WHEN SENSE completes, THEN output includes timestamp and iteration number
- [ ] WHEN any source fails to read, THEN that section includes error message (does not halt SENSE)

### DECIDE: Routing Logic

- [ ] WHEN ORIENT output has `spec_satisfied: true`, THEN DECIDE returns DONE
- [ ] WHEN ORIENT output has `spec_satisfied: false` AND `actionable_work_exists: true`, THEN DECIDE returns CONTINUE
- [ ] WHEN ORIENT output has `spec_satisfied: false` AND `actionable_work_exists: false`, THEN DECIDE returns STUCK
- [ ] WHEN ORIENT output has `spec_satisfied: "unverifiable"` AND `actionable_work_exists: false`, THEN DECIDE returns STUCK
- [ ] WHEN ORIENT output has `spec_satisfied: "unverifiable"` AND `actionable_work_exists: true`, THEN DECIDE returns CONTINUE

### DECIDE: Output Structure

- [ ] WHEN DECIDE completes, THEN output includes decision (DONE | STUCK | CONTINUE)
- [ ] WHEN DECIDE returns STUCK, THEN output includes reason from ORIENT gaps
- [ ] WHEN DECIDE returns DONE, THEN output includes final assessment summary

## Technical Constraints

- SENSE and DECIDE must be pure orchestrator code (no agent invocations)
- SENSE must complete in under 5 seconds for typical repositories
- Claims structure must be serializable to JSON for passing to ORIENT
- DECIDE logic must be deterministic (same input always produces same output)

## Data Structures

### Claims (SENSE Output)

```python
@dataclass
class Claims:
    timestamp: datetime
    iteration_number: int
    code_state: CodeStateClaims
    work_state: WorkStateClaims
    project_state: ProjectStateClaims
    human_input: HumanInputClaims | None
    learnings: str
```

### Decision (DECIDE Output)

```python
@dataclass
class Decision:
    outcome: Literal["DONE", "STUCK", "CONTINUE"]
    reason: str | None  # Required for STUCK
    summary: str | None  # Required for DONE
```

## Assets

- SODA Loop documentation: `docs/soda-loop.md`
- Ralph2 runner for reference: `src/ralph2/runner.py`

## Definition of Done

- [ ] All acceptance criteria have passing tests
- [ ] SENSE produces complete Claims from all sources
- [ ] SENSE handles missing/error sources gracefully
- [ ] DECIDE routing logic is correct for all input combinations
- [ ] Data structures are defined and validated with Pydantic
