# Decomposition Output

Summary after decomposing a phase.

```markdown
## Decomposition Complete: <Phase>

**Parent Bead:** <id>
**Sub-Beads Created:** <count>

| ID | Title | Est. Time | Depends On |
|----|-------|-----------|------------|
| <id>.0 | Context Brief | 15 min | - |
| <id>.1 | Schema | 30 min | - |
| <id>.2 | Implementation | 90 min | .1 |
| ... | ... | ... | ... |

**Total Estimated Time:** X hours
**Ready to Start:** <id>.0, <id>.1 (no blockers)

### Verification
- [ ] Every manifest item assigned to a sub-bead
- [ ] No content summarized or lost
- [ ] Each sub-bead atomic (~500 lines, 30-120 min)
- [ ] Dependencies explicit
- [ ] North Star Card in every sub-bead

### Next Steps
1. Agent claims parent + all sub-beads together
2. Reserves relevant files
3. Announces [CLAIMED]
4. Executes in dependency order
```
