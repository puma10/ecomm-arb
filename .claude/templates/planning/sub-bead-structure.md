# Sub-Bead Structure (ADaPT Pattern)

> **Key insight (ADaPT, 2025):** Sub-beads are created **only when execution fails**, not during upfront planning. Don't over-decompose—let execution reveal what's actually hard.

## When to Create Sub-Beads

**Create sub-beads ONLY when:**
1. Parent bead has failed after 3 repair iterations
2. You can identify a **specific** sub-problem that caused the failure
3. The sub-problem is isolatable (can be tested independently)

**Do NOT create sub-beads:**
- During initial planning ("just in case")
- Because the bead "looks complex"
- Before attempting execution
- For the entire bead (only for the failing part)

---

## The ADaPT Flow

```
Parent Bead Execution:
├── Iteration 1: Attempt → Fail
├── Iteration 2: Repair → Fail
├── Iteration 3: Repair → Fail
└── STOP: Do not continue iterating

Analysis:
├── What specific sub-problem caused failure?
├── Can it be isolated and tested independently?
└── What tests would prove the sub-problem is solved?

Sub-Bead Creation:
├── Create sub-bead for ONLY the failing component
├── Write tests that isolate the sub-problem
├── Execute sub-bead (same TDD flow)
└── When sub-bead closes, resume parent bead
```

---

## Sub-Bead Template

```markdown
# Sub-Bead: [parent-id].[n] - [Specific Problem]

## Why This Sub-Bead Exists (ADaPT)

**Parent bead:** [parent-id]
**Failure after iteration:** 3
**Specific failure:** [What exactly failed - test name, error message, behavior]
**Isolation rationale:** [Why this can be solved independently]

## Tests That Prove Sub-Problem Solved

```python
# These tests isolate the specific sub-problem
# When these pass, the parent bead can resume

def test_specific_failure_case():
    """This test reproduces the exact failure from parent bead"""
    # Full test code

def test_edge_case_that_broke():
    """Edge case that caused parent to fail"""
    # Full test code
```

## Minimal Specification

Only include what's needed to solve this specific sub-problem:

- **Edit locus:** [Exact files/functions to change]
- **Constraint:** [What must NOT change to avoid breaking parent]
- **Success criteria:** Tests above pass + parent bead can resume

## Verification

- [ ] Sub-bead tests pass
- [ ] `ubs --staged` clean
- [ ] Parent bead can resume execution
```

---

## Naming Convention

Sub-beads inherit parent ID with numeric suffix:

```
user-auth (parent - failed after 3 iterations)
└── user-auth.1 (sub-bead for specific JWT validation failure)
    └── user-auth.1.1 (sub-sub-bead if user-auth.1 also fails)
```

---

## Anti-Patterns

| Anti-Pattern | Why It Fails | Do Instead |
|--------------|--------------|------------|
| Pre-planning sub-beads | Guesses at complexity | Execute parent first |
| Decomposing entire bead | Loses context, creates unnecessary work | Isolate only failing part |
| Creating sub-beads after 1 failure | Premature decomposition | Allow 3 repair iterations |
| Sub-beads without tests | No verification of fix | Tests isolate the sub-problem |
| Sub-beads that don't reference parent failure | Loses traceability | Always cite parent failure |

---

## Evidence Base

- `research/038-adapt.md`: Decompose only when execution fails
- `research/011-agentless.md`: Simple pipelines beat complex agents
- `research/053-feedback-loop-security.md`: Security degrades with >3 iterations
