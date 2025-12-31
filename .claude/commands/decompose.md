---
description: Decompose a phase plan into atomic beads
argument-hint: <phase-description-or-id>
---

# /decompose

Run the `decompose` skill to break down a phase into beads.

**Phase:** $ARGUMENTS

Execute the subagent protocol from `.claude/skills/decompose/SKILL.md`:
1. Understand the phase (goal, files, dependencies, deliverables)
2. Create content manifest (LOSSLESS - list everything)
3. Create beads (parent + sub-beads, full code, North Star in each)
4. Set dependencies (schema → implementation → tests)
5. Validate with `bv --robot-suggest`, `bv --robot-plan`

**Key principle:** Manifest is source of truth. Create Beads reads manifest, not phase doc.
