# Project: ecom-arb

## Overview

E-commerce Arbitrage project. This is a **greenfield project** with no existing code.

## Project Status

- **State**: Initial setup complete
- **Tech Stack**: TBD - to be defined in North Star Card
- **Next Steps**: Complete planning documents in `PLAN/`

## Key Directories

```
.
├── .beads/          # Issue tracking database (commit with code)
├── .claude/         # Claude Code configuration
│   ├── commands/    # Slash commands (/prime, /advance, etc.)
│   ├── rules/       # Auto-loaded constraints
│   ├── skills/      # On-demand detailed guides
│   └── templates/   # Output templates
├── PLAN/            # Planning documents
│   ├── 00_north_star.md      # What success looks like
│   ├── 01_requirements.md    # Detailed requirements
│   ├── 02_requirements_qa.md # Q&A for requirements
│   ├── 03_decisions.md       # Architecture Decision Records
│   ├── 04_risks_and_spikes.md # Risks and research spikes
│   └── 05_traceability.md    # Requirement traceability
└── AGENTS.md        # Workflow instructions for agents
```

## Getting Started

1. **Start session**: `/prime`
2. **Define vision**: Fill out `PLAN/00_north_star.md`
3. **Capture requirements**: Complete `PLAN/01_requirements.md`
4. **Create tasks**: `bd create "Task description" -t task -p 2`
5. **Find work**: `bd ready` or `bv --robot-next`

## Tools Available

| Tool | Purpose |
|------|---------|
| `bd` | Task tracking (Beads) |
| `bv` | Task graph analysis |
| `ubs` | Security scanner |
| `cass` | Session search |
| `cm` | Pattern memory |

## Development Guidelines

- Follow TDD: Write tests before implementation
- Use beads for all task tracking
- Commit `.beads/` with every code change
- Run `ubs .` before commits
- Run `/calibrate` between phases

## CJ Crawl System Requirements

**CRITICAL: ngrok must be running for crawls to work.**

The crawl system uses SerpWatch to fetch CJ Dropshipping pages. SerpWatch sends results back via webhook, which requires a public URL.

### Before Starting Crawls

1. **Start ngrok** on port 8000:
   ```bash
   ngrok http 8000
   ```

2. **Update `.env`** with the ngrok URL:
   ```
   WEBHOOK_BASE_URL=https://xxxx-xxxx.ngrok-free.app
   ```

3. **Restart the API server** to pick up the new URL

### Crawl Flow
```
1. API submits URL to SerpWatch
2. SerpWatch fetches page with real browser
3. SerpWatch POSTs HTML to WEBHOOK_BASE_URL/api/crawl/webhook
4. API parses HTML and stores product data
```

**If crawls are stuck at "0/1 Searches"**: ngrok is not running or WEBHOOK_BASE_URL is wrong.
