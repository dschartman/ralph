# The High-Leverage Spec Guide

**Philosophy:** Define the Destination, not the Journey.

A good spec functions as a **contract**. It tells the engineering team: "Here is the problem, here is how the user sees it, and here is exactly how we will agree that you are finished."

---

## 1. The Golden Rule

> **"If it cannot be verified, it is not a requirement."**

Every item in the spec must be **measurable**. Vague statements are invalid.

| ❌ Invalid | ✅ Valid |
|-----------|---------|
| "Make it fast" | "Page loads in under 200ms" |
| "Make it user-friendly" | "User can complete signup in 3 clicks" |
| "Should be reliable" | "System handles 1000 concurrent users with <1% error rate" |

---

## 2. The Core Components (The 80%)

These are **mandatory**. Without these, the team cannot start.

### A. The Context (The "Why")

**Purpose:** Give engineers empathy for the user so they can make smart micro-decisions.

**Format:** 1-2 sentences max.

**Example:**
> "Users currently get lost during checkout because they don't know shipping costs. We are adding a shipping calculator so they can see costs upfront."

---

### B. The User Experience (The "Visible")

**Purpose:** Define exactly what the user sees and interacts with.

**Required:** Visual artifacts. Words are often insufficient for UI.

| Artifact | Description |
|----------|-------------|
| **Mockups/Wireframes** | Even a napkin drawing is better than a paragraph |
| **States** | Show the Happy Path, Error State, and Loading State |

**Key Check:** Does the engineer know what happens if they click the button twice?

---

### C. Acceptance Criteria (The "Verification")

**Purpose:** This is the heart of the spec. It maps 1:1 to the Acceptance Tests and Definition of Done.

**Format:** Use behavioral language (Scenario → Action → Result).

**The List:**

| Type | Example |
|------|---------|
| **Happy Path** | "WHEN the user enters a valid zip code, THEN display the shipping rate." |
| **Sad Path** | "WHEN the user enters an invalid zip code, THEN display a red error message saying 'Invalid Zip'." |
| **Edge Case** | "WHEN the API is down, THEN display a 'Try again later' banner." |

> **Why this matters:** This list allows the engineer to write their Integration/E2E tests *before* they write the code.

---

## 3. Technical Constraints (The "Must Haves")

**Purpose:** Define the boundaries. Only include technical details if they are business requirements or architectural mandates.

### ✅ Include

| Type | Example |
|------|---------|
| **Hard requirements** | "Must use Python 3.11" |
| **Tooling mandates** | "Must use uv for package management" |
| **Integration limits** | "Must interface with the Legacy Billing API" |

### ❌ Exclude

| Type | Why |
|------|-----|
| **Implementation preferences** | "Create a class called ShippingCalculator" → Let the team design the code |
| **Internal testing rules** | "Write unit tests using Pytest" → The team already knows the Testing Strategy; don't repeat it |

---

## 4. The "Ready for Dev" Checklist

Before handing this spec to the team, the author must answer **"Yes"** to these three questions:

| Question | What it validates |
|----------|-------------------|
| **Is it Testable?** | Can I write a Pass/Fail test for every requirement listed? |
| **Is it Independent?** | Does the team have all the assets (credentials, designs, API docs) they need to finish without asking for more info? |
| **Is the "Done" State Clear?** | If the team delivers exactly what is written here, will I accept it immediately? |

---

## Template

```markdown
# Feature: [Name]

## Context
[1-2 sentences explaining why this matters to the user]

## User Experience
[Link to mockups/wireframes]

### States
- Happy Path: [description or link]
- Error State: [description or link]
- Loading State: [description or link]

## Acceptance Criteria
- [ ] WHEN [action], THEN [result]
- [ ] WHEN [action], THEN [result]
- [ ] WHEN [edge case], THEN [result]

## Technical Constraints
- Must use [technology/API/tool]
- Must integrate with [system]

## Assets
- [ ] API documentation: [link]
- [ ] Design files: [link]
- [ ] Credentials: [location]
```

---

## Summary

```
┌─────────────────────────────────────────────────────────────┐
│                    THE GOLDEN RULE                          │
│                                                             │
│         "If it cannot be verified, it is not a requirement" │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    CORE COMPONENTS                          │
│                                                             │
│   Context             User Experience      Acceptance       │
│   (The Why)           (The Visible)        Criteria         │
│   1-2 sentences       Mockups + States     (The Verification)│
│   User empathy        What they see        Testable behaviors│
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 TECHNICAL CONSTRAINTS                       │
│                                                             │
│   Include: Hard requirements, tooling mandates, integrations│
│   Exclude: Implementation preferences, internal test rules  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  READY FOR DEV CHECKLIST                    │
│                                                             │
│   ✓ Testable?  ✓ Independent?  ✓ Done State Clear?         │
└─────────────────────────────────────────────────────────────┘
```
