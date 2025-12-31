---
description: Resolve disagreements using test-based adjudication
argument-hint: [approach_A vs approach_B]
---

# /resolve

Run the `resolve` skill for test-based adjudication.

**Scope:** $ARGUMENTS

Execute the subagent protocol from `.claude/skills/resolve/SKILL.md`:
1. Position Extraction: Document each approach with evidence
2. Discriminating Tests: Write tests that pass for one, fail for another
3. Execution: Run tests, observe results
4. Adjudication: Evidence picks winner, no compromise
5. User Report: Present findings (preserve dissent if tests don't discriminate)

**Philosophy:** Tests adjudicate, not rhetoric. Max 2 discussion rounds without tests.
