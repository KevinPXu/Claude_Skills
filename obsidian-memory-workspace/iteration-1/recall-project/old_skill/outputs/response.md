# Eval 2: Recall Project — Old Skill Response

Here's what I found about your Claude Skills project:

## Claude Skills Project
- Repo: ~/Claude_Skills (GitHub: KevinPXu/Claude_Skills)
- Building reusable skills for Claude Code

## Decisions
- Filesystem-based memory over Obsidian API
- grep-based search over REST API
- Standalone vault at ~/.claude/memory/
- Graph structure with [[wikilinks]]

## Architecture
- Helper script: bin/obsidian-memory.sh (bash + grep, no external deps)
- Hook: hooks/context-loader.sh (UserPromptSubmit event)
- Skill: SKILL.md (installed to ~/.claude/skills/obsidian-memory/)
