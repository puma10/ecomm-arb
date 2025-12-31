# Beads Rules

## Claiming
- Always claim parent AND all sub-beads together
- Always include `--assignee YOUR_NAME`
- Always send `[CLAIMED]` announcement before starting work

## Closing
- Close sub-beads FIRST, then parent
- Always send `[CLOSED]` announcement when done
- Always include `.beads/issues.jsonl` in commits

## Commands
- Use `bd ready --json` to find work
- Use `bv --robot-*` flags (never bare `bv` — hangs)
- Use `bd update {id} --status in_progress --assignee NAME` to claim

## Don't
- Don't claim only the parent (sub-beads appear "ready" to others)
- Don't skip announcements (causes duplicate work)
- Don't hoard tasks (one at a time)
