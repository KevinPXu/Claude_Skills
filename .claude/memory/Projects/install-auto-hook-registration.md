---
tags: [claude-memory, project]
summary: install.sh now auto-merges hook into existing hooks.json using python3 instead of printing manual instructions
created: 2026-03-16
updated: 2026-03-16
---

# install.sh — Auto Hook Registration

## Decision
Use python3 stdlib json module to merge the hook entry into an existing hooks.json, rather than printing manual instructions and bailing out.

## Why
Previous behavior required manual editing when hooks.json already existed (common on systems with other hooks configured). Fully automatic is better UX for new system setup.

## How It Works
- install_hook() function: if hooks.json missing → create from scratch; if exists → merge via python3
- python3 parses JSON, checks for duplicate command (idempotent), appends new hook group to UserPromptSubmit array
- Falls back to manual instructions if python3 not available (rare on macOS/Linux)
- Idempotent: re-running install won't add duplicate entries

## Links
- [[obsidian-memory]]
- [[install-update-command]]
