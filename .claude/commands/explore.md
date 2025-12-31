---
description: Parallel codebase search for understanding how things work
argument-hint: [question about codebase]
---

# /explore

Run the `explore` skill for codebase discovery.

**Query:** $ARGUMENTS

Uses Warp-Grep MCP for parallel search (up to 8 searches per turn).

Good for:
- "How does X work?"
- Data flow analysis
- Cross-cutting concerns
- Architecture understanding

Not for:
- Specific function lookup → use Grep
- Known file path → use Read
- External APIs → use /ground
- Past sessions → use /recall
