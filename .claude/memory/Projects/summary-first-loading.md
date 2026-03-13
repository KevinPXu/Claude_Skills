---
tags: [claude-memory, project, feature]
summary: Summary-first context loading — two-pass approach to maximize relevance within line budget
created: 2026-03-13
updated: 2026-03-13
---

# Summary-First Context Loading

## Problem
- Old cmd_context loaded seed notes in full, blowing the 200-line budget on the first large note
- Linked notes only got summary/excerpt — important context was often cut

## Fix (2026-03-12)
- Pass 1: print compact summary line for every matched note (cheap, ~1 line each)
- Pass 2: expand highest-scoring notes with full content in remaining budget
- Caller always sees ALL relevant topics, gets deep detail on most important ones

## Links
- [[obsidian-memory]]
- [[Projects]]
