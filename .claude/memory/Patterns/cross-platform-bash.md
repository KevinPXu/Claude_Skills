---
tags: [claude-memory, pattern]
summary: Avoid GNU-only bash features — no grep -oP, no find -printf, no ${var,,}, use tr and sed instead
---
# Cross-Platform Bash Compatibility

## Rules
- No `grep -oP` (Perl regex) — use `grep -o` + `sed` instead
- No `find -printf` — use `find` + `while read` + `basename`
- No `${var,,}` (bash 4+ lowercase) — use `tr [:upper:] [:lower:]`
- No nested brace patterns in BSD sed — use `grep | sed` pipelines
- `set -eo pipefail` + `&& continue` crashes — use `if ...; then continue; fi`

## Why
- macOS ships bash 3.2, BSD sed, BSD grep — all lack GNU extensions
- Skill must work on macOS, Linux, and Windows (Git Bash/WSL/MSYS2)

## Links
- [[obsidian-memory]]
- [[Patterns]]
