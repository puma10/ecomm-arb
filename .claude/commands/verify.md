---
description: Security scanning with UBS before commits
argument-hint: [--staged | path/to/file]
---

# /verify

Run the `verify` skill for security scanning.

**Target:** $ARGUMENTS

Execute security scan from `.claude/skills/verify/SKILL.md`:

```bash
# Pre-commit (MANDATORY)
ubs --staged

# Specific file
ubs path/to/file

# Working tree changes
ubs --diff
```

**Key principle:** `ubs --staged` is mandatory before every commit. ~40% of LLM code has vulnerabilities.
