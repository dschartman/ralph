# The SODA Loop

**S**ense → **O**rient → **D**ecide → **A**ct

A conceptual model for agentic iteration loops. Describes the logical flow of activities independent of how agents are organized or implemented.

---

## Origins: The OODA Loop

SODA is derived from John Boyd's **OODA loop** (Observe-Orient-Decide-Act), developed for military decision-making.

Boyd, a US Air Force Colonel, created OODA to explain how fighter pilots gain advantage in combat. The core insight: **the side that cycles through the loop faster wins**. If you can observe, orient, decide, and act faster than your opponent, they become reactive—always responding to your last move while you're already executing the next.

```
OODA: Observe → Orient → Decide → Act → (loop)
```

**Observe**: Gather information from the environment.

**Orient**: The critical phase. Interpret observations through mental models, experience, and context. Boyd considered this the most important step—it's where meaning is made from raw data.

**Decide**: Choose a course of action based on orientation.

**Act**: Execute. This changes the environment, creating new information to observe.

The loop is continuous. Each action changes reality, requiring fresh observation.

### Why OODA Matters Beyond Combat

OODA became influential in business strategy, sports, emergency response, and anywhere rapid adaptation under uncertainty matters. The framework emphasizes:

- **Speed of cycling** beats perfection of any single decision
- **Fresh observation** prevents acting on stale assumptions
- **Orientation is where judgment lives** — raw data is meaningless without interpretation

### From OODA to SODA

SODA adapts OODA for autonomous software development:

| OODA | SODA | Adaptation |
|------|------|------------|
| Observe | Sense | "Sense" better describes reading state from defined sources (git, trace, db) rather than passive environmental observation |
| Orient | Orient | Unchanged — still where all judgment and assessment happens |
| Decide | Decide | Unchanged — choose to continue, stop, or request help |
| Act | Act | Unchanged — modify reality through code and commits |

The key extension: SODA includes **human input as a participant in the loop**, not as an external controller. When the system is STUCK, it requests human input, which flows into the next SENSE/ORIENT cycle.

---

## Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                   RUN                                           │
│                                                                                 │
│   ┌────────────┐                                                                │
│   │ BOOTSTRAP  │  (one-time per project)                                        │
│   └─────┬──────┘                                                                │
│         ▼                                                                       │
│   ┌────────────┐                                                                │
│   │ MILESTONE  │  (per spec)                                                    │
│   └─────┬──────┘                                                                │
│         ▼                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐       │
│   │                        ITERATION LOOP                               │       │
│   │                                                                     │       │
│   │      SENSE ──► ORIENT ──► DECIDE ──► ACT ───┐                      │       │
│   │        ▲                     │               │                      │       │
│   │        │                  DONE/STUCK         │                      │       │
│   │        │                     │               │                      │       │
│   │        │                     ▼               │                      │       │
│   │        │                   EXIT              │                      │       │
│   │        │                                     │                      │       │
│   │        └─────────────────────────────────────┘                      │       │
│   │                                                                     │       │
│   └─────────────────────────────────────────────────────────────────────┘       │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## BOOTSTRAP Phase

One-time setup per project. Only happens on first run.

```
BOOTSTRAP
 │
 ├── Resolve/create project ID
 └── Initialize SQLite database
```

---

## MILESTONE Phase

Setup for each new spec. Creates the context for iteration.

```
MILESTONE
 │
 ├── Load spec (document, string, or structured input)
 ├── Create milestone branch
 └── Create root trace work item
```

---

## SENSE Phase

**Purpose:** Report what systems say. Pure information gathering, no judgment or verification.

SENSE collects claims from various sources. It does not verify whether those claims are true—that's ORIENT's job.

```
SENSE
 │
 ├── CODE_STATE (what git says)
 │    ├── Current branch
 │    ├── Uncommitted changes (staged/unstaged)
 │    ├── Commits since milestone base
 │    ├── Files changed since base
 │    └── Diff summary
 │
 ├── WORK_STATE (what Trace says)
 │    ├── Root work item (spec, acceptance criteria)
 │    ├── Open tasks
 │    ├── Closed tasks
 │    ├── Blocked tasks
 │    └── Recent comments and progress notes
 │
 ├── PROJECT_STATE (what the DB says)
 │    ├── Current iteration number
 │    ├── Prior iteration outcomes
 │    └── Last agent outputs (summaries, learnings)
 │
 └── HUMAN_INPUT (if any)
      ├── Corrections from previous STUCK
      ├── Priority overrides
      ├── Spec modifications (requirements changed)
      └── New constraints or clarifications
```

**Inputs:**
- Git repository
- Trace database
- Project database
- Human input queue (if any)

**Outputs:**
- Claims from each system, not yet verified
  - "Git says: 3 files changed since base"
  - "Trace says: task X is closed"
  - "DB says: iteration 3, last outcome CONTINUE"
  - "Human says: skip task Y, not important"

**Key distinction:** SENSE reports claims. ORIENT verifies claims against the codebase (which cannot lie). Trace can say a task is closed; only the code proves whether it's actually done.

---

## ORIENT Phase

**Purpose:** Verify claims and assess position relative to the goal. All judgment happens here.

ORIENT takes the claims from SENSE and verifies them against the codebase—the one source that cannot lie. Trace may say a task is closed; ORIENT checks if the code actually implements it.

```
ORIENT
 │
 ├── VERIFY_CLAIMS (ground to reality)
 │    ├── Verify task status (is "closed" actually done in code?)
 │    ├── Verify blockers (is blocker still blocking?)
 │    │    └── If unblocked: task becomes eligible for current iteration
 │    ├── Verify learnings (do they match observed reality?)
 │    │    └── If learning conflicts with reality: invalidate it
 │    ├── Incorporate human overrides (including spec changes)
 │    └── Resolve discrepancies between claims and codebase
 │
 ├── ASSESS_SPEC_SATISFACTION
 │    ├── Extract acceptance criteria from spec (use latest if modified)
 │    ├── Evaluate test quality (do tests actually test the spec?)
 │    ├── Run tests as one verification method
 │    ├── Read code for implementation proof
 │    ├── Determine: satisfied | not_satisfied | unverifiable
 │    └── Identify gaps (what's missing)
 │
 ├── APPLY_CONSTRAINT_FILTERS
 │    ├── Security (no vulnerabilities introduced)
 │    ├── Code quality (follows project standards)
 │    ├── Test quality (tests are meaningful, not just passing)
 │    ├── Performance (if applicable to this work)
 │    └── Prioritize findings (creates remediation tasks, not STUCK)
 │
 ├── UPDATE_TASK_BREAKDOWN
 │    ├── Close verified-complete tasks
 │    ├── Create tasks for identified gaps
 │    ├── Create remediation tasks for constraint failures
 │    ├── Unblock tasks where blocker resolved
 │    └── Reprioritize based on verified reality
 │
 └── PLAN_ITERATION (if spec not satisfied)
      ├── Select tasks for this iteration (including newly unblocked)
      ├── Order tasks for serial execution
      └── Define iteration intent
```

**Inputs:**
- Claims from SENSE (what git/Trace/DB/human say)
- Spec (the goal)
- Learnings (efficiency knowledge)
- The codebase itself (for verification)

**Outputs:**
- Verified reality (claims reconciled with codebase)
- Spec satisfaction status (satisfied, partially, not satisfied)
- Constraint filter results (pass/fail with findings)
- Gap list (what's missing)
- Verified blocker status
- Updated task breakdown in Trace
- Iteration plan (tasks selected, ordered, intent defined)

**Why planning lives in ORIENT:** You need to know what you'd be doing before DECIDE can determine if you're stuck. "No viable plan for iteration" = STUCK. Planning must happen before the decision.

**Key insight:** Assessment happens before action, not after. This makes the loop idempotent—running on an already-complete codebase will recognize completion in ORIENT and skip unnecessary action.

### Blockers: Trust but Verify

Blockers originate in ACT (we tried, we couldn't because of X), surface in SENSE (Trace says task is blocked), and get verified in ORIENT. A blocker claim might be stale—the blocking condition may have been resolved.

```
ACT: "Couldn't complete—missing API key"
         │
         ▼
SENSE: "Trace says task blocked: missing API key"
         │
         ▼
ORIENT: "Is API key still missing?" ──► YES: Still blocked
                                    └─► NO: Unblock, immediately eligible
```

**Key behavior:** When ORIENT unblocks a task, it becomes immediately eligible for the current iteration's PLAN_ITERATION. The system doesn't wait for the next cycle—if the blocker is resolved, the work can proceed now.

### Learnings: Trust but Verify

Learnings (efficiency knowledge) can also become stale. If the project structure changes, a learning like "tests are in `tests/`" becomes harmful if tests moved to `src/tests/`.

```
SENSE: "Learning says: tests are in tests/"
         │
         ▼
ORIENT: "Does tests/ exist?" ──► YES: Learning valid
                             └─► NO: Invalidate learning
```

VERIFY_CLAIMS applies to learnings too. If a learning conflicts with observed reality, deprecate it.

### Constraints as Filters

Constraints are not tasks to be completed—they are filters that every decision must pass through.

```
Completed work or proposed change
         │
         ▼
┌─────────────────────────┐
│   Constraint Filters    │
│   (Security?)           │──── FAIL ──► Creates remediation task
│   (Code quality?)       │              (DECIDE: CONTINUE, not STUCK)
│   (Test quality?)       │
│   (Performance?)        │
└─────────┬───────────────┘
          │
        PASS
          │
          ▼
    Acceptable to proceed
```

**On constraint failure:** A failed constraint creates a remediation task in UPDATE_TASK_BREAKDOWN. This means DECIDE will return CONTINUE (there's actionable work: fix the issue), not STUCK. Constraint failures are work to do, not blockers.

APPLY_CONSTRAINT_FILTERS asks: "Does reality pass our quality gates?" not "Did we do quality things?"

---

## DECIDE Phase

**Purpose:** Route based on orientation. Simple decision logic—complexity lives in ORIENT.

```
DECIDE
 │
 ├── DONE
 │    └── Spec is satisfied
 │
 ├── STUCK
 │    ├── All remaining tasks are blocked
 │    ├── Would only repeat previous failed attempts
 │    ├── Cannot determine next action (gap in understanding)
 │    └── Need human input to proceed
 │
 └── CONTINUE
      └── Spec not satisfied AND actionable work exists
```

### Decision Logic

```
Is spec satisfied? ──────────────────────► YES ──► DONE
         │
         NO
         │
         ▼
Is there actionable work? ───────────────► NO ───► STUCK
(not blocked, not repeating failures)
         │
         YES
         │
         ▼
      CONTINUE
```

**Inputs from ORIENT:**
- Spec satisfaction status
- Verified blocker status
- Gap list (remaining work)
- Previous iteration context (to detect repetition)

**Outputs:**
- Decision: DONE | STUCK | CONTINUE

**On DONE:** Quality issues discovered during this run become future milestones. Once spec is satisfied, this run is complete. The human decides what comes next.

**On STUCK:** The system needs human input. This isn't failure—it's a request for guidance. Common causes:
- External blockers (missing credentials, API access, etc.)
- Ambiguity in spec that can't be resolved
- Repeated failures suggesting a gap in understanding

**On CONTINUE:** There's work to do and we can do it. Proceed to ACT.

---

## Human Participation

The human is not outside the loop—the human is a participant within it.

```
SENSE
 ├── Code state (git)
 ├── Work state (trace)
 ├── Project state (db)
 └── Human input (if any)  ◄── corrections, clarifications, constraints

ORIENT
 ├── Verify claims (including human overrides)  ◄── human input incorporated here
 ├── Assess spec satisfaction
 ├── Apply constraint filters
 └── Update task breakdown
```

Human input flows through the same structure as any other signal. The loop remains consistent whether human intervenes or not.

**STUCK as a request for input:**

When DECIDE returns STUCK, the system is requesting human participation:

```
DECIDE
 ├── DONE      → exit (success)
 ├── CONTINUE  → ACT
 └── STUCK     → wait for human input → loop back to SENSE
```

The human provides input (correction, clarification, unblocking information), which becomes part of what SENSE observes in the next cycle. ORIENT incorporates it. The loop continues.

**Fully autonomous runs** are simply runs where no human input was needed—same loop, same structure, just no human signals.

**Human-assisted runs** are runs where STUCK occurred, human provided input, and the loop resumed—same structure, human participated as an input source.

This framing keeps the model consistent regardless of autonomy level.

---

## ACT Phase

**Purpose:** Modify reality. Only entered if DECIDE returns CONTINUE.

```
ACT
 │
 ├── SETUP_WORKSPACE
 │    ├── Create/checkout work branch
 │    └── Establish test baseline
 │         ├── Run full test suite
 │         └── Capture current pass/fail state
 │
 ├── EXECUTE (per task, serial)
 │    │
 │    ├── ORIENT_TO_TASK (mini-SODA at task level)
 │    │    ├── Read assignment from Trace
 │    │    ├── Read learnings for efficiency
 │    │    └── Understand relevant code/context
 │    │
 │    ├── IMPLEMENT
 │    │    ├── [code work] TDD cycle:
 │    │    │    ├── Write failing test
 │    │    │    ├── Write code to pass test
 │    │    │    └── Refactor if needed
 │    │    └── [non-code] Do directly (docs, config, research)
 │    │
 │    ├── VERIFY
 │    │    ├── Run tests
 │    │    ├── Compare to baseline
 │    │    │    └── New failures = must fix or document as blocker
 │    │    └── If blocked: document why in Trace, move on
 │    │
 │    ├── UPDATE_TRACES
 │    │    ├── Comment on completed work
 │    │    ├── Comment on blockers encountered
 │    │    └── Create subtasks if discovered during work
 │    │
 │    ├── COMMIT
 │    │    └── Stage and commit changes with clear message
 │    │
 │    └── CAPTURE_LEARNINGS
 │         ├── Capture discoveries as they happen
 │         └── Reflect at end: "What do you wish you knew?"
 │
 └── FINALIZE
      ├── Merge work branch to milestone branch
      └── Handle conflicts
           └── If unresolvable: document as blocker for next cycle
```

**Inputs:**
- Iteration plan from ORIENT (tasks selected, ordered)
- Learnings (efficiency knowledge)

**Outputs:**
- Modified code (in git, on milestone branch)
- Modified work state (in Trace: comments, status updates, new subtasks)
- New learnings (efficiency knowledge)
- Blocker documentation (if encountered)

### Why Test Baseline Matters

Running tests before making changes establishes what's already broken vs. what you broke:

```
SETUP_WORKSPACE: Run tests → 95 pass, 5 fail (baseline)
         │
         ▼
IMPLEMENT: Make changes
         │
         ▼
VERIFY: Run tests → 93 pass, 7 fail
         │
         ▼
Compare to baseline: 2 NEW failures
         │
         ▼
Must fix or document: These are YOUR responsibility
```

Without a baseline, agents may ignore failures as "not related to my changes" when they actually are.

**Projects without tests:** The baseline is nothing—zero tests, zero failures. This is fine. As tests are added, they become the new baseline. The iterative nature of SODA handles this naturally.

**Flaky tests:** When investigating failures, if the outcome is "this test is flaky," the test should be identified as such (marked, quarantined, or fixed). Flaky tests don't violate the notion of work being done, but they do indicate poor testing practices that should be addressed. A flaky test is a quality issue to remediate, not an excuse to ignore failures.

### EXECUTE as Mini-SODA

Each task execution follows a mini-SODA pattern:

- **Sense:** Read assignment, read learnings, read relevant code
- **Orient:** Understand what needs to be done, plan approach
- **Decide:** (implicit) Proceed with implementation
- **Act:** Implement, test, commit

This fractal structure means SODA applies at both the iteration level and the individual task level.

### Tracer Bullets (Strategy Guidance)

> **Note:** This is a recommended strategy for the ACT phase, not a core mechanism. The SODA loop works regardless of implementation approach, but tracer bullets align well with the model's emphasis on observable progress.

When building new functionality, prefer **tracer bullets** over component-by-component construction.

A tracer bullet is a thin, end-to-end slice through the system that touches all layers:

```
Traditional approach:          Tracer bullet approach:

Build Layer 1 completely      Build thin slice through all layers
         │                              │
         ▼                              ▼
Build Layer 2 completely      ┌─────────────────────┐
         │                    │  UI (minimal)       │
         ▼                    │         │           │
Build Layer 3 completely      │         ▼           │
         │                    │  Logic (minimal)    │
         ▼                    │         │           │
Integrate (hope it works)     │         ▼           │
                              │  Data (minimal)     │
                              └─────────────────────┘
                                        │
                                        ▼
                              Verify slice works end-to-end
                                        │
                                        ▼
                              Thicken each layer incrementally
```

**Why tracer bullets matter for SODA:**

1. **Early constraint validation** — A vertical slice tests all constraints (security, performance, integration) immediately, not after significant investment.

2. **Tests have a foundation** — End-to-end scaffolding provides the structure for meaningful tests. You can write integration tests from the start.

3. **Reality changes faster** — Each iteration modifies observable reality in ways that SENSE can detect. Progress is visible, not hidden inside incomplete components.

4. **Blockers surface early** — Integration issues, architectural problems, and constraint violations appear in the first iteration, not after weeks of component work.

**Application:** When ORIENT's PLAN_ITERATION selects work, prefer tasks that extend or thicken existing tracer bullets over tasks that build isolated components.

---

## Learnings

Learnings are practical efficiency knowledge that accumulates across iterations. They help future work be more efficient by capturing what was discovered.

**Examples:**
- "Tests live in `tests/`, run with `uv run pytest tests/`"
- "The API client is in `src/client/api.py`"
- "Use `trc ready` to see unblocked tasks"

**Characteristics:**
- Generated by any phase doing work (primarily ACT, but ORIENT can generate them too)
- Consumed by any phase doing work
- Accumulated in memory file
- Project-specific and actionable

**Validation and Curation:**
- **Validation:** ORIENT's VERIFY_CLAIMS checks learnings against observed reality. If a learning conflicts with what SENSE reports (e.g., "tests are in `tests/`" but they're actually in `src/tests/`), the learning is invalidated.
- **Curation:** Learnings may also be curated to remove duplicates. This can happen during ORIENT or at the start of ACT.

---

## Execution Mode

Tasks execute serially, one at a time:

```
ORIENT: PLAN_ITERATION
        "Tasks A, B, C selected for iteration"
                        │
                        ▼
                     DECIDE
                   (CONTINUE)
                        │
                        ▼
ACT: SETUP_WORKSPACE
        Create work branch
        Establish test baseline
                        │
                        ▼
     EXECUTE_A ──► EXECUTE_B ──► EXECUTE_C
     (same branch)
                        │
                        ▼
ACT: FINALIZE
        Work already on branch
        No merge needed
                        │
                        ▼
                 (loop to SENSE)
```

Use a dedicated work branch for each iteration. This enforces good source control practices and allows easy rollback if needed. The isolation provided by work branches and clean commits means the architecture *could* support parallel execution in the future, but serial execution is the only supported mode currently.

---

## Data Flow

```
                    ┌─────────────────────────────────────────┐
                    │              LEARNINGS                  │
                    │    (accumulated efficiency knowledge)   │
                    └────────────────────┬────────────────────┘
                                         │
                         ┌───────────────┼───────────────┐
                         │               │               │
                         ▼               ▼               ▼
                    ┌─────────┐    ┌──────────┐    ┌─────────┐
 reality ─────────► │  SENSE  │───►│  ORIENT  │───►│ DECIDE  │
 (git, trace, db)   └─────────┘    └──────────┘    └────┬────┘
                                         │              │
                         ┌───────────────┘              │
                         │                              │
                         ▼                              ▼
                    ┌─────────┐                   ┌───────────┐
                    │   ACT   │◄──── CONTINUE ────│  DONE or  │
                    └────┬────┘                   │   STUCK   │
                         │                        └───────────┘
                         │
              ┌──────────┴──────────┐
              │                     │
              ▼                     ▼
         modify reality       generate learnings
         (git, trace)         (memory file)
```

---

## State and Storage

| What | Where | Description |
|------|-------|-------------|
| Code | Git working tree | Source files, tests, config |
| Code history | Git commits | What changed and when |
| Task breakdown | Trace | Work items, hierarchy, comments |
| Task status | Trace | Open, closed, blocked |
| Iteration history | Project DB | Outputs from prior iterations |
| Learnings | Memory file | Accumulated efficiency knowledge |
| Spec | Input (file/string) | The goal we're working toward |

---

## Activity Reference

| Activity | Phase | Responsibility |
|----------|-------|----------------|
| Read code state | SENSE | Report what git says (branch, changes, commits, diff) |
| Read work state | SENSE | Report what Trace says (tasks, status, comments) |
| Read project state | SENSE | Report what DB says (iteration, outcomes, outputs) |
| Read human input | SENSE | Report what human says (corrections, overrides, constraints) |
| Verify claims | ORIENT | Ground claims from SENSE against codebase reality |
| Assess spec satisfaction | ORIENT | Evaluate acceptance criteria with tests and code review |
| Apply constraint filters | ORIENT | Pass work through quality gates (security, quality, tests) |
| Update task breakdown | ORIENT | Close verified tasks, create gap tasks, update blockers |
| Plan iteration | ORIENT | Select tasks, define iteration intent |
| Decide outcome | DECIDE | Route based on spec satisfaction and actionable work |
| Setup workspace | ACT | Create work branch, establish test baseline |
| Orient to task | ACT | Read assignment, learnings, and relevant context (mini-SODA) |
| Implement | ACT | TDD cycle (write test, write code, refactor) or non-code work |
| Verify | ACT | Run tests, compare to baseline, document blockers |
| Update traces | ACT | Comment on completed work, blockers, create subtasks |
| Commit | ACT | Stage and commit changes with clear message |
| Capture learnings | ACT | Record discoveries and reflect on efficiency knowledge |
| Finalize | ACT | Merge work branch, handle conflicts |

---

## Design Principles

1. **Assessment before action** — All judgment happens in ORIENT, before deciding whether to act. This makes the loop idempotent.

2. **Codebase as arbiter** — SENSE reports claims from systems (git, Trace, DB). ORIENT verifies those claims against the codebase, which cannot lie. Trace saying "done" means nothing until the code proves it.

3. **Learnings flow throughout** — Efficiency knowledge is generated and consumed by any phase doing work.

4. **Clear phase boundaries** — SENSE observes, ORIENT judges, DECIDE chooses, ACT modifies.

5. **Isolation through work branches** — Each iteration operates on a dedicated work branch, enabling clean rollback and good source control practices.

6. **Constraints are filters, not tasks** — Quality requirements (security, performance, coverage) are gates that work must pass, not checkboxes to complete.

7. **Tracer bullets over components** — Build thin end-to-end slices first, then thicken. This surfaces integration issues and validates constraints early.

---

## Scope Boundaries

SODA operates on well-scoped systems and components. If the codebase becomes too large for an agent to effectively assess, that's not a limitation of SODA—it's a signal that the system needs architectural decoupling.

**The principle:** A well-designed system has reasonable inputs, reasonable outputs, and expected behavior. An agent should be able to assess such a system within a single iteration's ORIENT phase. When this becomes impossible due to scale, the system is likely doing too much.

**When limits are reached:**
- The human participant can help identify natural seams for decomposition
- SODA can then operate on each component independently
- This is the natural growth pattern: build a component, reach limits, decompose, continue

This boundary is a feature, not a limitation. It enforces good architectural practices by making monolithic designs uncomfortable to work with.
