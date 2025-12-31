---
description: Claim and work on beads safely with proper coordination
argument-hint: [bead_id or focus_area]
---

# /advance

Run the `advance` skill to manage the full bead lifecycle.

**Focus:** $ARGUMENTS

Execute the direct protocol from `.claude/skills/advance/SKILL.md`:
1. Close out previous work (if any) — tests, ubs, commit, announce
2. Discover available tasks (bv --robot-triage, bd ready)
3. Verify no conflicts (file reservations, inbox, dependencies)
4. Claim task + all sub-beads + reserve files + announce `[CLAIMED]`
5. Get context from memory (cm context)
6. Work using TDD-first (tests before implementation)
7. Security gate (ubs --staged before every commit)
8. Max 3 iterations — stop, spike, escalate if stuck
