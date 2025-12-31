---
description: Verify external libraries against current documentation
argument-hint: [question-or-library]
---

# /ground

Run the `ground` skill to verify external dependencies.

**Query:** $ARGUMENTS

Execute the direct protocol from `.claude/skills/ground/SKILL.md`:

1. Construct query: `{library} {feature} {version} 2024 2025`

2. Run appropriate search:
   - `web_search_exa("{query}")` — Documentation
   - `get_code_context_exa("{query}")` — Code examples

3. Verify: Source, Freshness, Version, Completeness, Status

4. Record grounding status:
   ```markdown
   | Pattern | Query | Source | Status |
   |---------|-------|--------|--------|
   | `{method}` | "{query}" | {url} | ✅/⚠️/❌/❓ |
   ```

**Key principle:** Ground just-in-time as you encounter external deps.
