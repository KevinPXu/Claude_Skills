---
tags: [claude-memory, project]
summary: Notes must be atomic with summary fields — hub notes skipped in traversal, linked notes show summaries only
---
# Atomicity Approach

## Decisions
- One decision/pattern/concept per note, max ~30 lines
- Hub notes (Index.md, Projects.md, etc.) skipped during link traversal to prevent loading everything
- Linked notes (1-hop from search hits) show summary: field only, not full content
- Seed notes (direct keyword matches) get full content
- Filename matches weighted 3x higher in search ranking
- Write command warns when notes exceed 30 lines

## Why
- Prevents context bloat — loading a massive note defeats the purpose of a graph
- Summaries keep linked context compact while still providing trail-following
- Hub notes link to everything and would poison traversal

## Links
- [[obsidian-memory]]
- [[Patterns]]
