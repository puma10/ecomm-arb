---
description: Retrieve context from past sessions before implementing
argument-hint: [task_description]
---

# /recall

Run the `recall` skill to get learned patterns and history.

**Query:** $ARGUMENTS

Execute the direct protocol from `.claude/skills/recall/SKILL.md`:
1. Distilled context: `cm context "{task}" --json`
2. Review rules, anti-patterns, suggested searches
3. Deep dive if needed: `cass search "{query}" --robot`
4. Apply context before implementing

**Key principle:** Always start with `cm context` - it gives distilled patterns, not raw history.
