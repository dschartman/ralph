# Agent Orchestration Model

> **Document Scope:** This is a conceptual architecture document. It defines *what* the system does and *how components interact* at a conceptual level. It intentionally omits implementation details such as interfaces, schemas, prompts, and technical mechanisms. Those belong in system architecture and implementation documents that build upon this foundation.

---

This document defines the conceptual architecture for agentic software engineering: how agents interact, their responsibilities, and the flow of the system.

For the foundational theory, see [Understanding Ralph](./understanding-ralph.md).

---

## Overview

The system operates on a core insight: **LLMs in agentic loops are stateless within invocations.** They can do genuine work, but cannot maintain continuity of intention across context boundaries.

The orchestration model provides external scaffolding for the executive functions the model cannot provide internally. It does this through:

1. **Separation of concerns** — distinct agents with distinct responsibilities
2. **Centralized state** — work tracking as the system of record
3. **Objective contracts** — consistent formats for agent interaction
4. **Iteration** — patient repetition toward a stable goal

---

## Three Layers

The system operates across three distinct layers:

```
┌─────────────────────────────────────────────────────────────┐
│                     WORK TRACKING                           │
│                                                             │
│  What needs to be done and what's the status                │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                      SYSTEM STATE                           │
│                   (system operation)                        │
│                                                             │
│  How the system is operating                                │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                       CODEBASE                              │
│                   (objective reality)                       │
│                                                             │
│  The actual code and git history                            │
└─────────────────────────────────────────────────────────────┘
```

### Work Tracking

The work tracker is the system of record for all work. It contains:

- **Milestone** — the spec, represented as the root work item
- **Work items** — breakdown of the spec into actionable tasks
- **Status** — open, in-progress, done, blocked
- **Feedback items** — findings from specialists
- **Priority** — High, Medium, Low
- **Comments** — notes, verdicts, context

The spec lives in the work tracker. Work breakdown lives there. Feedback lives there. This unifies tracking into a single system.

### System State (System Operation)

System state tracks how the orchestration is operating:

- **Run ID** — which run we're on
- **Iteration number** — which iteration within the run
- **Agent outputs** — what each agent produced per invocation
- **Learnings** — accumulated efficiency knowledge
- **Run history** — past runs and their outcomes

This is separate from work tracking because it's about the system, not the work.

### Learnings

Learnings are efficiency knowledge accumulated across iterations. The concept:

- At the end of their work, agents are asked: *"What do you wish you had known before starting that would have made your job easier?"*
- These reflections become learnings
- The Planner curates learnings at the start of each iteration
- Curated learnings are provided to Executors, Verifier, and Specialists
- Efficiency compounds: what one agent discovers, future agents benefit from

Learnings are distinct from work items. Work items track *what needs to be done*. Learnings track *how to do things better*.

### Codebase (Objective Reality)

The codebase is ground truth:

- The actual code files
- Git history
- Test results
- Build artifacts

Agents observe the codebase to assess current state. Executors modify the codebase to make progress.

---

## Unified Model: Spec Lives in Work Tracking

The spec is the milestone. All work is organized beneath it:

```
MILESTONE ← This IS the spec
│
├── Work Item 1 (from Planner breakdown)
│   ├── Sub-task 1a
│   └── Sub-task 1b
│
├── Work Item 2
│   └── Status: blocked
│   └── Comment: "Need API credentials"
│
├── Feedback: Tech debt in auth (from Code Reviewer)
│   └── Priority: Medium
│   └── Type: maintainability
│
└── Feedback: Edge case not handled (from Adversarial Tester)
    └── Priority: Low
    └── Type: edge-case
```

This means:
- No separate spec file and work tracker
- Spec and its completion status live in the same place
- Verifier checks the milestone, not an external file
- Feedback becomes potential future work items naturally

---

## Milestone Lifecycle

Milestones are bounded convergence targets with accumulated backlog.

1. **Input**: User provides a spec
2. **Creation**: Spec enters work tracker as a milestone
3. **Breakdown**: Planner decomposes milestone into work items
4. **Iteration**: Executors work, feedback accumulates, Planner directs
5. **Completion**: Verifier confirms spec is met, Planner declares DONE
6. **Handoff**: Unfinished and deprioritized work remains as backlog. Human reviews and decides on the next milestone.

The next milestone may incorporate backlog items, address new requirements, or both. The work tracker preserves continuity across milestones.

---

## Agent Roles

### Planner

**Purpose:** Decide what to do next and whether iteration should continue.

**Reads:**
- Milestone (the spec)
- All children (work items, feedback)
- Verifier verdict (comment on milestone)
- Learnings (from system state)

**Writes:**
- New work items as children of milestone
- Priority assignments
- Decisions: CONTINUE, DONE, STUCK

**Incentive:** Velocity. Get to the goal efficiently.

**Key responsibility:** The Planner answers "is continued iteration worth it?" This is a value judgment weighing progress, feedback, and remaining work.

### Executor

**Purpose:** Do the assigned work.

**Reads:**
- Assigned work item
- Context (system prompt)
- Relevant learnings
- Objective standards

**Writes:**
- Status updates (in-progress → done or blocked)
- Comments with blocked reasons
- Sub-tasks discovered during work
- Efficiency notes for learnings

**Writes to codebase:** The actual implementation.

**Incentive:** Quality. Build things that are maintainable and correct.

**Testing:** The Executor owns test-driven development. This means:
- Writing tests before implementation (red-green-refactor)
- Running tests during development
- Ensuring all tests pass before marking work complete

The Executor does not mark work as done until tests pass. This is part of quality engineering, not a separate verification step.

**Isolation:** Executors work in isolation from each other. This enables parallel execution without conflicts.

### Verifier

**Purpose:** Confirm whether the spec has been met. Nothing more.

**Reads:**
- Milestone (the spec)
- Codebase (objective reality)

**Writes:**
- Verdict as comment on milestone

**Incentive:** Correctness. The project truly meets the spec, not just "looks done."

**Testing:** The Verifier's primary responsibility is the verdict: *"Has the spec been met?"*

The Verifier may examine test coverage, assess test quality, or run smoke tests as part of forming that verdict. But running tests is not the Verifier's core job—the core job is completion assessment. The Executor ensures the work is done correctly. The Verifier ensures the spec is satisfied.

**Key constraint:** The Verifier answers only "did we meet the spec?" It does not decide whether iteration should continue — that's the Planner's job.

### Specialists (Feedback Generators)

Specialists are read-only observers that produce prioritized feedback. The system is designed for new specialists to be added without changing the core loop.

**The specialist pattern:**
- **Reads**: Milestone and codebase
- **Writes**: Feedback as work items with priority and category
- **Constraint**: Does not modify the codebase

Any perspective that provides useful feedback can become a specialist. The specific specialists in use are a configuration choice, not an architectural constraint.

**Example specialists:**

| Specialist | Focus | Looks For |
|------------|-------|-----------|
| Code Reviewer | Maintainability | Patterns that cause future pain |
| Test Quality Analyst | Test validity | Tests that actually validate behavior |
| Adversarial Tester | Edge cases | Ways to break things |
| Security Reviewer | Vulnerabilities | Security risks and attack vectors |
| Performance Analyst | Efficiency | Bottlenecks and optimization opportunities |

**All specialists:**
- Read milestone and codebase
- Write feedback as new work items with priority and type
- Run in parallel (read-only observers)
- Identify issues; the Planner decides what to do about them

---

## The Flow

```
┌─────────────────────────────────────────────────────────────┐
│                         PLANNER                             │
│                                                             │
│  Reads: milestone, children, verdict, memory                │
│  Decides: CONTINUE / DONE / STUCK                           │
│  If CONTINUE: creates/assigns work items                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       EXECUTOR(S)                           │
│                  (parallel with isolation)                  │
│                                                             │
│  Each: isolate → work → integrate                           │
│  Updates work item status, writes to codebase               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   FEEDBACK GENERATORS                       │
│                  (parallel, read-only)                      │
│                                                             │
│  Verifier: verdict on milestone (comment)                   │
│  Specialists: feedback items with priority                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                       Back to PLANNER
```

### Iteration Sequence

1. **Planner** assesses state, decides if work should continue
2. If CONTINUE: Planner breaks down work, assigns to Executor(s)
3. **Executor(s)** do assigned work (parallel if multiple)
4. **Feedback Generators** assess result (parallel)
5. All feedback flows to next iteration's Planner
6. Repeat until DONE or STUCK

---

## Agent Communication

Agents communicate through the work tracker in consistent, predictable ways. Each agent has clear responsibilities for what it reads and writes.

### Verifier

**Reads:** Milestone (the spec) and codebase (reality)

**Writes:** Verdict as a comment on the milestone—whether the spec is met or not, with rationale and any gaps identified.

**Key constraint:** The Verifier does not create work items. A verdict is an assessment, not a task.

### Specialists

**Read:** Milestone and codebase

**Write:** Feedback as new work items (children of milestone) with priority and category. Specialists identify issues; the Planner decides what to do about them.

### Executor

**Reads:** Assigned work item, relevant context, and relevant learnings

**Writes:**
- Status updates (open → in-progress → done or blocked)
- Blocking reasons when stuck
- Sub-tasks discovered during work
- Efficiency notes for learnings

**Writes to codebase:** The actual implementation.

### Planner

**Reads:** Everything—milestone, all children (work items, feedback), verifier verdict, learnings

**Writes:**
- New work items as children of milestone
- Priority assignments
- Continue/Done/Stuck decisions
- Curated learnings

---

## Termination States

| State | Trigger | What Happens |
|-------|---------|--------------|
| **DONE** | Verifier confirms spec met | Milestone complete. Feedback preserved. Human reviews for next milestone. |
| **STUCK** | Cannot make progress | System halts. Human investigates. May need to unblock, provide info, or rewrite spec. |

### DONE Flow

1. Verifier confirms spec is met
2. Planner sees verdict, checks for High/Medium feedback items
3. If critical items remain: continue working them
4. When clear: declare DONE
5. All feedback remains as backlog
6. Human reviews, decides on next milestone

### STUCK Flow

1. Planner detects no progress possible:
   - All remaining work is blocked
   - Same failure repeating
   - Spec appears impossible
2. Planner declares STUCK with reason
3. Human intervenes:
   - Provides missing information
   - Grants access
   - Clarifies or rewrites spec
4. Run resumes or new run begins

---

## Input Model

The system accepts specs through stdin or file path. Spec content is the input; how it's provided is an implementation detail.

**On receiving a spec:**

1. Parse input as spec
2. Check for existing milestone that matches:
   - **Identical:** Use existing milestone, continue work
   - **Similar but different:** Update milestone (input is source of truth)
   - **No match:** Create new milestone
3. Begin iteration loop

---

## Priority Model

Specialists assign priority to feedback. The Planner uses priority to make decisions.

| Priority | Meaning | Examples |
|----------|---------|----------|
| **High** | Blocks spec completion or critical stability | Security vulnerability, broken core flow |
| **Medium** | Important for stability, should be addressed | Missing error handling, test coverage gap |
| **Low** | Improvement, not blocking | Code style, minor refactor |

**Planner's priority logic:**
1. High items block DONE — must be addressed
2. Medium items should be addressed before milestone closes
3. Low items go to backlog for future milestones

---

## What This Document Does Not Cover

This is the conceptual architecture. It defines *what* the system does and *how components interact*.

Not covered here (belongs in implementation specs):
- How contracts are enforced technically
- Specific prompt templates for agents
- Database schemas
- API interfaces
- Error handling details

---

## Relationship to Core Principles

This orchestration model implements the principles from [Understanding Ralph](./understanding-ralph.md):

| Principle | How It's Implemented |
|-----------|---------------------|
| Fresh Context | Each agent invocation starts clean |
| Observable Reality | Agents read codebase and work tracker, not internal memory of past iterations |
| Stable Goals | Milestone is the anchor |
| The Loop | Planner → Executor → Feedback → Planner |
| Efficiency Compounds | Learnings accumulate and are curated across iterations |

The loop is the mechanism. The work tracker provides continuity. The agents do the work.
