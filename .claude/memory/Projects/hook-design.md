---
tags: [claude-memory, project]
summary: Hook auto-reads memory and injects write commands so CLAUDE.md stays minimal
---
# Hook Design Decisions

## Decision
- The UserPromptSubmit hook handles everything automatic: vault resolution, search, context injection, write config, session tracking
- This keeps CLAUDE.md minimal (2 lines) and avoids bloat
- The hook injects exact commands with resolved paths so Claude never hardcodes

## Why
- CLAUDE.md is always in context — every byte costs tokens
- Other Claude sessions cant introspect hooks.json, so the hook must self-describe via its output
- Vault resolution must happen at hook time (knows cwd), not at skill time

## Links
- [[obsidian-memory]]
- [[Patterns]]
