# Phase Document Template

Use this structure when creating phase documents during Phase 2 breakdown.

> **2025 Reality Check:** Plan size should match project complexity. A simple phase might only need sections 0, 1, 2, 7, 10. Include other sections only when they reduce guessing.

## TDD-First: Tests Before Implementation

**Critical:** Section 2 (Tests) comes before Section 6 (Implementation). This is intentional.

```
AlphaCodium Flow (45.97% improvement):
1. SPEC: Define what "done" looks like (Sections 0-1)
2. TESTS: Write tests that verify "done" (Section 2) ← BEFORE implementation
3. IMPLEMENT: Code to pass tests (Section 6)
4. RUN: Execute tests
5. REPAIR: Fix failures (max 3 iterations)
```

## Sections (Include What Reduces Guessing)

| # | Section | When to Include | Fail If Missing |
|---|---------|-----------------|-----------------|
| 0 | **North Star Card** | Always | Agents lose the goal |
| 1 | **Context & Motivation** | Always | Agent won't understand the purpose |
| 2 | **Tests FIRST** | Always (TDD) | No verification = no "done" |
| 3 | **Architecture Decisions** | When choices exist | Agent will make different choices |
| 4 | **System Integration Map** | When >2 components | Agent won't understand data flow |
| 5 | **Prerequisites** | When dependencies exist | Agent will hit blockers |
| 6 | **Detailed Specification** | When complex data/validation | Agent will guess wrong |
| 7 | **Implementation Guidance** | When patterns matter | Agent will put code in wrong places |
| 8 | **Verification Checklist** | Always | No definition of done |
| 9 | **Cross-References** | When dependencies exist | Agent won't understand ordering |
| 10 | **Acceptance Criteria** | Always | Unclear completion state |
| 11 | **Calibration** | At integration boundaries | Drift compounds unchecked |

---

## Template

```markdown
# Phase N: [Title]

## 0. North Star Card

[Copy the North Star Card verbatim from the master plan]

Alignment note: [One sentence explaining how this phase advances the North Star]

## 1. Context & Motivation

### WHY This Exists
[2-3 sentences explaining the purpose]

### What Happens If Built Wrong
- [Consequence 1]
- [Consequence 2]

## 2. TESTS FIRST (Write Before Implementation)

> **Why first:** TDD yields 45.97% pass@1 improvement. Tests define "done" before implementation begins.

### Tests That Prove Phase Complete

```python
# Write these FIRST - before any implementation code

class TestHappyPath:
    async def test_success_scenario(self, client):
        """Primary success path - must pass for phase to close"""
        # Full test implementation - not placeholders

class TestEdgeCases:
    async def test_boundary_condition(self, client):
        """Boundary conditions"""
        # Full test implementation

class TestErrorHandling:
    async def test_failure_mode(self, client):
        """Expected failure modes"""
        # Full test implementation
```

### Test Coverage Checklist
- [ ] Happy path covered
- [ ] Edge cases covered
- [ ] Error conditions covered
- [ ] Security-relevant inputs validated

## 3. Architecture Decisions (Include When Choices Exist)

| Decision | Choice | Alternatives | Rationale |
|----------|--------|--------------|-----------|
| [Decision point] | [What we chose] | [Other options] | [Why this choice] |

## 4. System Integration Map (Include When >2 Components)

```
┌─────────────┐    ┌─────────────┐
│  Component  │───▶│  Component  │
└─────────────┘    └─────────────┘
```

## 5. Prerequisites (Include When Dependencies Exist)

- [ ] [Dependency 1] — [why needed]
- [ ] [Dependency 2] — [why needed]

## 6. Detailed Specification (Include When Complex Data/Validation)

### Data Structures

```python
class ExampleModel:
    field: Type  # Description
```

### Inputs/Outputs

| Field | Type | Validation | Description |
|-------|------|------------|-------------|

### Error Conditions

| Error | Cause | Handling |
|-------|-------|----------|

## 7. Implementation Guidance (Include When Patterns Matter)

### File Locations

```
app/
├── module/
│   └── implementation.py
└── tests/
    └── test_module.py
```

### Anti-Patterns

- ❌ [Don't do this] — [why]

## 8. Verification Checklist (Always Include)

### Tests
- [ ] All tests written FIRST (before implementation)
- [ ] All tests passing
- [ ] Edge cases covered

### Security (P13 Gate)
- [ ] `ubs --staged` clean
- [ ] No hardcoded secrets
- [ ] User input validated

### Quality
- [ ] Code reviewed (P14 for P0 requirements)

## 9. Cross-References (Include When Dependencies Exist)

- **Depends On:** Phase [N-1]
- **Enables:** Phase [N+1]
- **Beads:** [bead-ids]

## 10. Acceptance Criteria (Always Include)

- [ ] [Observable, testable criterion 1]
- [ ] [Observable, testable criterion 2]
- [ ] All tests passing
- [ ] `ubs --staged` clean

## 11. Calibration (Include At Integration Boundaries)

### Calibration Point: YES / NO

### What To Verify Before Proceeding

| Check | Question |
|-------|----------|
| **Goal Alignment** | Are we still building what the user actually wants? |
| **Foundation Solid** | Is this robust enough to build the rest on? |
| **Integration Risk** | Any friction points that will compound? |

### Blockers For Next Phase

Do NOT proceed until:
- [ ] All tests passing
- [ ] `ubs --staged` clean
- [ ] Calibration complete (if YES above)
```

---

## Size Verification

After creating a phase document, verify:

Treat these as coarse heuristic guardrails, not hard rules.

| Metric | Heuristic | If Off |
|--------|-----------|--------|
| Total lines | Aim ~500-1000 | If too large: split. If too small: confirm nothing is missing. |
| Code blocks | Enough to remove ambiguity | Add concrete imports/types/examples where “guessing” would occur. |
| Test code | Enough to cover `AC-*` end-to-end | Replace “TODO tests” with executable tests for critical paths. |
| Tables | Use where structure helps | Decisions/errors/contracts often benefit from tables. |
