---
tags: [claude-memory, project]
summary: CLAUDE.md needs an explicit behavioral instruction for Claude to act on injected memory notes — descriptive text alone is not enough
created: 2026-03-16
---
# CLAUDE.md — Behavioral Instruction for Memory Notes

## Decision
CLAUDE.md must include an explicit instruction telling Claude what to DO when
the hook injects a `## Relevant Memory Notes` section, not just describing that
the hook exists.

Required line:
> When the hook injects a `## Relevant Memory Notes` section, always read the
> matched notes and surface relevant context before responding.

## Why
Discovered 2026-03-16: hook correctly found and injected a code review note, but
Claude led with "I don't have access to GitLab" and never mentioned the memory.
The install script only added descriptive text ("hook loads relevant memory..."),
which Claude read as background info rather than an instruction to act on.

## How to apply
- `install.sh` heredoc already includes this line for new installs
- `append_claude_md()` now patches existing CLAUDE.md files missing this line
- Running `./install.sh update` backfills existing projects

## Links
- [[install-update-command]]
- [[hook-visibility]]
- [[obsidian-memory]]
