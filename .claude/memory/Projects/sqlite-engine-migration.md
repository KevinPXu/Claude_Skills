---
tags: [claude-memory, project]
summary: Migrated graph engine from bash/grep to Python/SQLite with FTS5 BM25 search and bidirectional link index
---
# SQLite Engine Migration

## Decision
- Replaced 517-line bash engine with Python/SQLite (memory_engine.py)
- bash shim (obsidian-memory.sh) delegates to python3 — same CLI interface
- SQLite .index.db is a disposable cache rebuilt from .md files by mtime

## Why
- Bash hit complexity ceiling: BSD vs GNU incompatibilities, set -e traps, string-based graph traversal
- FTS5 gives BM25 ranking with porter stemming and column weighting (title 5x, summary 3x)
- SQLite links table enables O(1) bidirectional lookups (forward + backlinks)
- Zero new dependencies — python3 + sqlite3 are stdlib

## Architecture
- notes table: path, title, summary, tags, content, mtime
- notes_fts: FTS5 virtual table with porter tokenizer
- links table: source/target with index on target for backlink queries
- Incremental sync: only reindexes files whose mtime changed

## Links
- [[obsidian-memory]]
- [[atomicity-approach]]
