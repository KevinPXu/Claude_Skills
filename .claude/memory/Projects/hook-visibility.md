---
tags: [claude-memory, project]
summary: Hook stdout goes to Claude context only — stderr is silently captured, not shown to user
---
# Hook Output Visibility

## Finding
- Hook stdout: injected into Claude's conversation context (not visible to user)
- Hook stderr: silently captured by Claude Code, not displayed in terminal
- statusMessage in hooks.json: shown in status bar during execution (static only)
- No mechanism for hooks to print dynamic output to the user's terminal

## Implication
- Memory hook status is only visible to Claude, not the user
- User can only confirm hook is running via the status bar flash

## Links
- [[hook-design]]
- [[obsidian-memory]]
