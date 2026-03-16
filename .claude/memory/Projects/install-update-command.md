---
tags: [claude-memory, project]
summary: update command now registers hook + updates CLAUDE.md, not just syncing SKILL.md
created: 2026-03-16
updated: 2026-03-16
---

# install.sh — update Command Enhancement

## Decision
./install.sh update now does three things:
1. Re-syncs SKILL.md to ~/.claude/skills/
2. Ensures hook is registered in hooks.json (calls install_hook, idempotent merge)
3. Ensures CLAUDE.md has memory instructions (calls append_claude_md, idempotent)

## Why
Existing users who installed before auto-merge existed would still have missing hooks after a git pull. update should fix any missing pieces, not just the SKILL.md copy.

## Structural Change
HOOKS_FILE, CLAUDE_MD, HOOK_CMD derivation and install_hook() function were moved above both the update and main install blocks so both commands share the same logic.

## Links
- [[obsidian-memory]]
- [[install-auto-hook-registration]]
