---
tags: [claude-memory, project]
summary: Graph-based persistent memory skill for Claude Code — bash scripts + hook + SKILL.md
---
# obsidian-memory

## Architecture
- **Hook** (context-loader.sh): UserPromptSubmit hook handles ALL reading — vault resolution, keyword search, context injection, write config injection, session tracking, save reminders
- **Skill** (SKILL.md): Handles writing only — what to save, how to structure notes, note format
- **Script** (obsidian-memory.sh): CLI for search, read, write, append, link, context, related, tags
- **Installer** (install.sh): Global install, update, init-vault commands

## Key Decisions
- Hook handles reading, skill handles writing — avoids duplication
- Hook injects "Obsidian Memory Config" block with resolved vault path and exact commands
- SKILL.md should NOT contain vault resolution, context loading, or hardcoded paths
- Notes must be atomic (~30 lines max), linked via [[wikilinks]], with summary: in frontmatter

## Links
- [[hook-design]]
- [[atomicity-approach]]
- [[cross-platform-fixes]]
- [[Projects]]
