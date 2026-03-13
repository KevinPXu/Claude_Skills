---
tags: [claude-memory, project]
summary: Skill-creator audit of hook efficiency — 6 fixes applied, all tests passing
created: 2026-03-13
updated: 2026-03-13
---

# Hook Efficiency Audit (2026-03-13)

## Issues Found & Fixed

### 1. FTS5 AND→OR + prefix matching
- Old: quoted AND queries ("`auth`" "`decision`" "`made`") required all terms → missed notes
- New: unquoted OR with prefix (auth* OR decision* OR made*) finds partial matches
- BM25 still ranks multi-match notes higher

### 2. LIKE fallback with root extraction
- SQLite porter stemmer doesn't stem "deployment" → "deploy"
- Added _extract_roots() that strips common suffixes (-ment, -tion, -ing, etc.)
- LIKE fallback now finds morphological variants FTS5 misses

### 3. Apostrophe tokenization
- Old: what's → what + s (single-char noise keyword broke search)
- New: tr -d "'" before tokenizing → whats (clean single token)
- Also added .{1,2} filter to block any 1-2 char keywords

### 4. Removed project-name fallback
- Old: if keywords matched nothing, fell back to project dir name → injected irrelevant notes
- New: no match = no context (correct behavior)

### 5. Conditional config block
- Old: ~665 char write-config block injected on EVERY prompt
- New: only injected when notes found or save reminder threshold reached
- Trivial prompt overhead: 825 chars → 158 chars (5.2x reduction)

### 6. Trimmed stop word list
- Removed coding terms: deploy, configure, build, fix, implement, update, refactor, debug, test, commit, push, merge, install, develop, create, file, check
- These are meaningful memory search keywords, not noise

## Test Results
- Efficiency tests: 20/24 → 26/26 (all pass)
- Regression tests: 44/44 (unchanged)
- Execution time: ~50ms (unchanged)
- Eval workspace: obsidian-memory-workspace/iteration-1/

## Status
- Fixes applied to context-loader.sh and memory_engine.py
- User testing in own environment before committing

## Links
- [[obsidian-memory]]
- [[hook-design]]
