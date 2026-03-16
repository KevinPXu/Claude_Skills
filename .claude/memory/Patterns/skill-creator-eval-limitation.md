---
tags: [claude-memory, pattern]
summary: skill-creator description optimization eval breaks when skill is already globally installed
created: 2026-03-16
updated: 2026-03-16
---

# Skill-Creator Eval Limitation — Installed Skills

## The Problem
run_eval.py creates a temp skill named `obsidian-memory-skill-{uuid}` in
.claude/commands/ and checks if Claude invokes it. But if the real skill is
already installed at ~/.claude/skills/, Claude ALWAYS calls the installed skill
(e.g. {"skill": "obsidian-memory"}) instead of the temp one.

Result: 0/N triggers for every should-trigger query — completely misleading.

## Why It Seems to Work Sometimes
If the skill is NOT globally installed (first-time use, pre-install test),
claude -p subprocesses only see the temp skill and results are valid.

## How to Fix
Temporarily uninstall the skill before running the optimization loop:
  rm -rf ~/.claude/skills/obsidian-memory
  python3 -m scripts.run_loop ...
  # reinstall after

## Second Issue: ANTHROPIC_API_KEY
improve_description.py uses anthropic.Anthropic() directly — needs ANTHROPIC_API_KEY.
Claude Code sessions using claude.ai OAuth don't set this. Crashes at iteration 1
with: TypeError: "Could not resolve authentication method..."
Workaround: set ANTHROPIC_API_KEY manually before running the loop.

## Links
- [[python-hook-audit]]
- [[obsidian-memory]]
- [[Patterns]]
