---
tags: [claude-memory, project, feature]
summary: Auto-timestamps, staleness decay in context scoring, and prune command for vault maintenance
created: 2026-03-13
updated: 2026-03-13
---

# Staleness & Pruning

## Auto-timestamps (2026-03-12)
- cmd_write adds created/updated dates to frontmatter automatically
- cmd_append refreshes updated date on every append
- ensure_timestamps() creates frontmatter block if note lacks one

## Staleness Decay
- Context loading deprioritizes older notes: 0.5% score reduction per day since last update
- 30-day-old note keeps ~86% score, 180-day keeps ~41%
- Floor of 10% — old notes are never fully invisible

## Prune Command
- `prune <YYYY-MM-DD>` lists notes not updated since date
- `prune <YYYY-MM-DD> --confirm` deletes them and rebuilds index
- Hub notes (Index.md, Projects.md, etc.) excluded from pruning
- Falls back to file mtime if note has no timestamp

## Links
- [[obsidian-memory]]
- [[Projects]]
