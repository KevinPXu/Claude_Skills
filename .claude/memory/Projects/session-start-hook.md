---
tags: [claude-memory, project]
summary: Added SessionStart hook registration so vault config is injected at session boot, not just on UserPromptSubmit
created: 2026-03-16
---

# SessionStart Hook for /clear Fix

## Decision
Register the context-loader hook for **both** `SessionStart` and `UserPromptSubmit` (previously only `UserPromptSubmit`).

## Why
`/clear` wipes the conversation but does not start a new session, so `SessionStart` does not re-run after it.
The `UserPromptSubmit` hook does fire after `/clear`, but the injected `systemMessage` was being dropped or
ignored in the post-clear context — meaning the vault was not visible to Claude on the first post-clear prompt.

Adding `SessionStart` ensures that at fresh session boot the vault config is always injected before any
user message is processed, covering the most common case. The `UserPromptSubmit` hook continues to handle
per-prompt keyword search.

## How It Works
- `install_hook()` in install.sh now merges the hook into both `SessionStart` and `UserPromptSubmit`
- At `SessionStart`, context-loader detects empty prompt and outputs minimal vault config then exits
- `_ensure_vault_pointer` also runs at SessionStart (see [[auto-memory-vault-pointer]])

## Remaining Gap
`/clear` within a running session still does not trigger `SessionStart`, so the injected `systemMessage`
may not persist. The vault pointer in auto-memory (see [[auto-memory-vault-pointer]]) is the real fix for that case.

## Links
- [[obsidian-memory]]
- [[auto-memory-vault-pointer]]
- [[hook-design]]
