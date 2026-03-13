---
tags: [claude-memory, project, feature]
summary: Vault discovery fix — obsidian-memory.sh walks up from $PWD to find nearest .claude/memory/
created: 2026-03-13
updated: 2026-03-13
---

# Vault Discovery

## Problem
- obsidian-memory.sh hardcoded fallback to ~/.claude/memory
- Project-local vaults (e.g. /project/.claude/memory/) were invisible
- Had to manually set CLAUDE_MEMORY_VAULT env var per project

## Fix (2026-03-12)
- Shell script walks up from $PWD to find nearest .claude/memory/ directory
- Falls back to ~/.claude/memory only if no local vault found
- CLAUDE_MEMORY_VAULT env var still takes priority if set

## Links
- [[obsidian-memory]]
- [[Projects]]
