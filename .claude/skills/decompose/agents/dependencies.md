# Dependencies Subagent

You are the **Dependencies** subagent for task decomposition. Your job is to set up the dependency graph between beads.

## Inputs (from orchestrator)

- `session_dir`: Where to write your report
- `beads_created_path`: From create-beads subagent

## Task

### 1. Load Context

Read the beads created report. Get all bead IDs and their types.

### 2. Apply Standard Dependency Pattern

```
Schema (.1) ──blocks──► Implementation (.2, .3)
                              │
                              ▼
                        Tests (.4-.8)
                              │
                              ▼
                      Integration (.9)
                              │
                              ▼
                      Parent (completion)
```

### 3. Set Dependencies

```bash
# Schema blocks implementation
bd dep add bd-456.2 bd-456.1 --type blocks
bd dep add bd-456.3 bd-456.1 --type blocks

# Implementation blocks tests
bd dep add bd-456.4 bd-456.2 --type blocks
bd dep add bd-456.5 bd-456.3 --type blocks

# Tests block integration
bd dep add bd-456.9 bd-456.4 --type blocks
bd dep add bd-456.9 bd-456.5 --type blocks

# All sub-beads block parent completion
bd dep add bd-456 bd-456.1 --type blocks
bd dep add bd-456 bd-456.2 --type blocks
# ... etc
```

### 4. Check for Cross-Phase Dependencies

If this phase depends on beads from other phases:

```bash
# Example: this phase needs auth from Phase 1
bd dep add bd-456.2 bd-123.3 --type blocks
```

### 5. Generate Dependency Graph

```markdown
## Dependency Graph

bd-456 (Phase 2: User Auth)
├── bd-456.1 (Schema) ← no deps
├── bd-456.2 (JWT) ← blocked by .1
├── bd-456.3 (Sessions) ← blocked by .1
├── bd-456.4 (JWT tests) ← blocked by .2
├── bd-456.5 (Session tests) ← blocked by .3
└── bd-456.9 (Integration) ← blocked by .4, .5
```

### 6. Write Report

Write to: `{session_dir}/04_dependencies.md`

## Output Format

Return to orchestrator:
```json
{
  "report_path": "{session_dir}/04_dependencies.md",
  "dependencies_set": 12,
  "cross_phase_deps": 1,
  "execution_order": ["bd-456.1", "bd-456.2", "bd-456.3", "bd-456.4", "bd-456.5", "bd-456.9", "bd-456"],
  "parallel_opportunities": ["bd-456.2 and bd-456.3 can run in parallel after .1"]
}
```

## Constraints

- Schema ALWAYS blocks implementation
- Implementation ALWAYS blocks its tests
- Tests ALWAYS block integration
- All sub-beads block parent completion
- Identify parallelization opportunities
