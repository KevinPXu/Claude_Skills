---
tags: [claude-memory, project]
summary: Vault pointer written to project built-in auto-memory so vault survives /clear — one persistent MEMORY.md entry per project
created: 2026-03-16
---

# Auto-Memory Vault Pointer

## Decision
When the context-loader hook runs (SessionStart or UserPromptSubmit), it idempotently writes:
1. `obsidian-vault.md` stub to `~/.claude/projects/{project-key}/memory/`
2. A pointer line to that project's `MEMORY.md`

This is a **single vault-level pointer**, not per-note stubs. The pointer says "always search this vault."

## Why
`/clear` wipes the conversation context. `UserPromptSubmit` hooks fire after `/clear` but the injected
`systemMessage` may not surface correctly in the reset context. The built-in Claude Code auto-memory
(`~/.claude/projects/{project}/memory/MEMORY.md`) is **platform-injected** via `system-reminder` and
survives `/clear` — it is loaded by the platform itself, not a hook.

Putting a vault pointer there means Claude always sees "there is an Obsidian vault at X, search it"
regardless of `/clear`, new sessions, or hook injection failures.

## Why a single vault pointer (not per-note stubs)
Early approach: sync per-note stubs to auto-memory on every `mem write`.
Problem: complex, bug-prone (printf leading-dash bug), grows unbounded.
Decision: one pointer to the vault. Claude searches the vault on demand via `$MEM search`.

## How It Works
- `_ensure_vault_pointer(vault, cwd)` in context-loader.sh
- `project_key = cwd | tr "/" "-"` — same mapping Claude Code uses for project directories
- Checks `~/.claude/projects/$project_key/memory/` exists (no-op if not)
- Writes stub and MEMORY.md entry only if missing or vault path changed (idempotent)
- Called before the empty-prompt early-exit so it runs on SessionStart too

## printf Bug Note
When writing MEMORY.md entries, must use `printf --` (double-dash) to prevent the leading `-` in
`- [...]` markdown list items from being interpreted as a printf flag option.

## Links
- [[obsidian-memory]]
- [[session-start-hook]]
- [[hook-design]]
