# Audit Report Template

Use this template when auditing another agent's decomposition work.

---

## Audit Criteria

1. **LOSSLESS** — No content was lost or summarized
2. **VERBATIM** — Content was copied exactly, not paraphrased
3. **COMPLETE** — All sections from original appear in sub-beads
4. **STANDALONE** — Each sub-bead makes sense independently
5. **CORRECT STRUCTURE** — Sub-beads follow the standard pattern

---

## Template

```markdown
## Audit Report: <bead-id>

**Auditor:** <agent-name>
**Date:** <YYYY-MM-DD>
**Decomposer:** <original-agent>

### Summary
- **Status:** PASS / FAIL
- **Original chars:** <count>
- **Sub-bead chars:** <count>
- **Difference:** <+/- chars> (<explanation>)

### Sub-Beads Reviewed
| ID | Title | Chars | Status |
|----|-------|-------|--------|
| .0 | Context Brief | 2,340 | ✅ OK |
| .1 | Schema | 1,892 | ✅ OK |
| .2 | Implementation | 4,210 | ⚠️ Missing error handling |

### Issues Found
<If FAIL, list specific problems with line references>

### Recommendation
<PASS: close decomp task / FAIL: create REDO task with specific fixes>
```

---

## When Audits Fail

1. Create a REDO task for the decomposer
2. List specific issues to fix
3. Decomposer re-does the work
4. Another audit cycle
