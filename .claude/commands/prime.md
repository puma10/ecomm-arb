---
description: New agent startup checklist (Agent Mail + Beads)
argument-hint: [task_focus]
---

# /prime

Run the `prime` skill to initialize a new agent session.

**Focus:** $ARGUMENTS

Execute the direct protocol from `.claude/skills/prime/SKILL.md`:
1. Register with Agent Mail (macro_start_session)
2. Orient (read AGENTS.md, CLAUDE.md, check CASS history)
3. Coordinate (check inbox, discover agents, send greeting if needed)
4. Discover work (git state, ready tasks, bv recommendations)
5. Output startup summary with recommended task

**Design:** Direct execution, no subagents. Simple command sequences.
