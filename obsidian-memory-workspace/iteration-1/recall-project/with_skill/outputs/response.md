# Eval 2: Recall Project — New Skill Response

Here's what I know about your Claude Skills project, including decisions and reasoning:

## Claude Skills Project
- **Repo**: ~/Claude_Skills (GitHub: KevinPXu/Claude_Skills)
- **Purpose**: Building reusable skills for Claude Code

## Key Decisions (and why)

1. **Filesystem-based memory over Obsidian API** — Zero dependencies, generalizable to any machine
2. **grep-based search over REST API** — Faster for small vaults, no Obsidian required
3. **Standalone vault at ~/.claude/memory/** — Exportable, not tied to personal vault
4. **Graph structure with [[wikilinks]]** — Obsidian-compatible for visualization
5. **Config manager: filesystem over REST API** (2026-03-11) — Removes Obsidian dependency, improves portability

## Related Context (from linked notes)

These decisions follow a broader pattern you've established:
- **Filesystem Over API pattern**: When building generalizable tools, prefer direct filesystem operations. Zero external deps, works on any machine, easier to debug. (Exception: when you need fuzzy/NLP search or concurrent access.)
- **Your preferences**: You generally prefer filesystem-based tools over cloud APIs, and like to understand architecture before coding.

## Architecture
- Helper script: `bin/obsidian-memory.sh` (bash + grep)
- Hook: `hooks/context-loader.sh` (UserPromptSubmit)
- Skill: `SKILL.md` → installed to `~/.claude/skills/obsidian-memory/`
