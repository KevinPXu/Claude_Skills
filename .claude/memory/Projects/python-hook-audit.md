---
tags: [claude-memory, project]
summary: Skill-creator audit 2026-03-16 — 7 fixes to Python hook + SKILL.md recall regression fixed
created: 2026-03-16
updated: 2026-03-16
---



# Python Hook Audit (2026-03-16)

## Context
The installed hook (~/.claude/hooks/obsidian-memory) is a Python file, not the
bash context-loader.sh. This audit found and fixed 7 issues in it.

## Critical Bug
- `prompt = data.get("user_prompt", "")` — wrong field name
- Claude Code sends `"prompt"`, not `"user_prompt"`
- Result: hook NEVER extracted keywords or searched vault — just injected config block every time

## Fixes Applied
1. Field name: `user_prompt` → `prompt`
2. Search: naive regex scan → subprocess call to memory_engine.py (BM25 + graph)
3. Config injection: always → only when notes found or at save threshold
4. Session count: global `~/.claude/hooks/.obsidian-session-count` → per-vault `.session-count`
5. Save threshold: 25 → 5
6. Exit detection: added /clear, /exit, bye, etc.
7. Verbosity: full note bodies → summaries-only (strips ### Details, keeps ### Summaries bullets)

## Fix 7 Detail (verbosity)
- Old: injected full note content (~200 lines) visible in UI on every prompt
- New: parse context output, keep only bullet points from ### Summaries
- Claude calls `$MEM context "<query>"` explicitly when full content needed
- Result: ~6 lines injected instead of ~200

## SKILL.md Changes
- Updated "How It Works" to describe actual hook behavior
- Added Recall section: "$MEM context/search" with "standalone CLI, not hook-dependent" note
- The "standalone CLI" note was critical — see [[skill-over-explanation-pattern]]

## Source
- Installed hook: ~/.claude/hooks/obsidian-memory
- Source copy: Claude_Skills/obsidian-memory/hooks/obsidian-memory.py

## Links
- [[obsidian-memory]]
- [[hook-design]]
- [[skill-over-explanation-pattern]]

## Description Optimization (2026-03-16)

### SKILL.md Description Updated
Added 3 missing trigger patterns found via manual eval analysis:
- Save: "note for future reference", "keep this in mind", "I always want", "I prefer"
- Recall: "remind me what we settled on", "what context do you have about", "what was the conclusion"
- Trigger: "when the same issue comes up repeatedly"

### Automated Optimization Loop — Can't Work for Installed Skills
run_loop.py + run_eval.py (skill-creator) doesn't work when the skill is already
globally installed. The eval creates a temp skill named 
in .claude/commands/, but Claude always calls the INSTALLED skill ({"skill":
"obsidian-memory"}) instead. The eval checks for the temp name in the Skill tool JSON
and gets 0 triggers, making results meaningless.

To use the automated loop: temporarily uninstall the skill before running.

### ANTHROPIC_API_KEY Missing in OAuth Sessions
improve_description.py calls anthropic.Anthropic() which needs ANTHROPIC_API_KEY.
Claude Code sessions using claude.ai OAuth don't set this env var — only API key
auth sessions do. Loop crashes at the "Improving description" step.
