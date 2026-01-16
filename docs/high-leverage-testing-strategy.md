# The High-Leverage Testing Strategy

A practical, minimal testing methodology that maximizes value while minimizing cognitive overhead.

---

## 1. The Strategy (The Engine)

This is the only methodology you need to memorize.

### Test-Driven Development (TDD)

**The Rule:** Write the test before the code.

**Why:** It forces you to design the API from the user's perspective (Inputs/Outputs) before worrying about implementation. It naturally creates "testable" code.

**The Flow:**
```
Red (Fail) → Green (Pass) → Refactor (Clean)
```

---

## 2. The Inner Loop (Local Machine)

These tests run on your laptop. They must be **fast**, **deterministic**, and **safe to run 100 times a day**.

### Unit Test

| Attribute | Description |
|-----------|-------------|
| **Scope** | Logic only (Functions/Methods) |
| **Prerequisite** | All dependencies (Databases, APIs) must be Mocked/Stubbed |
| **Safety** | 100% Safe. Zero external side effects |
| **Goal** | Verify the logic handles all permutations (happy path, edge cases, nulls) |

### Isolated Integration Test

| Attribute | Description |
|-----------|-------------|
| **Scope** | Your code + One external component (e.g., Code + DB) |
| **Prerequisite** | Ephemeral Infrastructure (e.g., TestContainers or Docker Compose) |
| **Safety** | Safe. Isolated to your local container |
| **Goal** | Verify your SQL queries or API parsers actually work with the real technology, not just a mock |

> **Critical:** Never run these against a shared/staging database. The test spins up a fresh DB, runs, and destroys it.

---

## 3. The Outer Loop (The Pipeline)

These tests run automatically when you push code. They enforce the rules.

### Continuous Integration (CI)

| Attribute | Description |
|-----------|-------------|
| **Role** | The Enforcer |
| **Action** | Automatically runs the Inner Loop (Unit + Isolated Integration) on every commit |
| **Goal** | Prevents "It works on my machine" from blocking the team |

### End-to-End (E2E) Smoke Test

| Attribute | Description |
|-----------|-------------|
| **Scope** | The Full Stack (Frontend + Backend + Deployed DB) |
| **Prerequisite** | A deployed environment (Staging or Ephemeral Review App) |
| **Safety** | ⚠️ Caution. These run against real environments |
| **Goal** | The "20%" of tests that cover 80% of risk |

> **Important:** Do not test every edge case here. Test the **Critical User Journeys** (e.g., Login → Checkout → Pay). If this passes, the app is likely healthy.

---

## 4. The Gate (The Agreement)

### Definition of Done (DoD)

**Definition:** The checklist that dictates if a ticket is complete.

**The 80/20 Standard:**
- [ ] Inner Loop tests passed (Green)
- [ ] Critical Paths covered by Acceptance Tests
- [ ] Code Reviewed & Merged

### Who Writes Acceptance Tests?

| Role | Responsibility |
|------|----------------|
| **Product Manager** | Defines the **Criteria** (The inputs and expected outputs) |
| **Engineer** | Writes the automated test code (usually an Integration or E2E test) |

---

## FAQ

### Do we need Black Box / Clear Box distinctions?

**No.** If you follow TDD, you are doing both naturally. Adding the definitions adds cognitive load without changing behavior.

### Does TDD cover the strategy?

**Yes.** It is the single highest-leverage habit. If a team does TDD, they get testable code and coverage for free.

### Who writes Acceptance Tests?

The **PM defines What** (Criteria), the **Engineer automates the How** (The Test).

### Do we need CI?

**Yes, absolutely.** CI is the "Police Officer" for the strategy. Without CI, the strategy is just a suggestion. With CI, it is a requirement.

---

## Summary

```
┌─────────────────────────────────────────────────────────────┐
│                     THE STRATEGY                            │
│                                                             │
│                    TDD: Red → Green → Refactor              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    INNER LOOP (Local)                       │
│                                                             │
│   Unit Tests          Isolated Integration Tests            │
│   (Logic only)        (Code + One Real Component)           │
│   Mocked deps         Ephemeral infrastructure              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    OUTER LOOP (Pipeline)                    │
│                                                             │
│   CI (Enforcer)       E2E Smoke Tests                       │
│   Runs inner loop     Critical journeys only                │
│   on every commit     Against real environments             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    THE GATE (Agreement)                     │
│                                                             │
│   Definition of Done: Tests green + Acceptance + Reviewed   │
└─────────────────────────────────────────────────────────────┘
```
